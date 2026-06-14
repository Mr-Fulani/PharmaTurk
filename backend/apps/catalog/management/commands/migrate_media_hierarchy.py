"""Переносит медиа из плоских leaf-папок R2 в иерархию products/{root}/.../{leaf}/.

Причина: пути строились по leaf-слагу категории (products/antibiotics/...),
без вложения под корень. Эта команда приводит существующие объекты к иерархии
products/{root}/.../{leaf}/..., совпадающей с деревом категорий.

Безопасный порядок на каждую запись: copy_object (old->new) -> head (проверка)
-> UPDATE поля в БД (минуя сигналы) -> delete старого объекта. Прерывание не
ломает сайт: БД всегда указывает на существующий объект. Идемпотентно.

    python manage.py migrate_media_hierarchy --dry-run
    python manage.py migrate_media_hierarchy
"""
import logging

from django.apps import apps
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db.models import FileField

from apps.catalog.models import Category
from apps.catalog.utils.storage_paths import _category_chain
from apps.catalog.utils.r2_utils import get_r2_client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Перенос медиа из плоских leaf-папок в иерархию products/{root}/.../{leaf}/"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Только показать, ничего не двигать")
        parser.add_argument("--limit", type=int, default=0, help="Ограничить число переносов (0 = без лимита)")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        limit = opts["limit"]

        # remap: leaf_slug -> chain (root/.../leaf), только для категорий с родителем.
        # При коллизии слага (один leaf у разных родителей) — помечаем ambiguous и пропускаем.
        chains_by_leaf: dict[str, set[str]] = {}
        for cat in Category.objects.all():
            chain = _category_chain(cat)
            leaf = (cat.slug or "").strip("/").lower()
            if leaf and "/" in chain:
                chains_by_leaf.setdefault(leaf, set()).add(chain.lower())
        remap = {leaf: next(iter(chains)) for leaf, chains in chains_by_leaf.items() if len(chains) == 1}
        ambiguous = {leaf for leaf, chains in chains_by_leaf.items() if len(chains) > 1}

        self.stdout.write(f"Категорий для вложения: {len(remap)} (ambiguous пропущены: {sorted(ambiguous)})")
        for k, v in sorted(remap.items()):
            self.stdout.write(f"  products/{k}/ -> products/{v}/")

        bucket = settings.R2_CONFIG["bucket_name"]
        client = get_r2_client()

        def remap_path(path: str):
            if not path or not path.startswith("products/"):
                return None
            parts = path.split("/", 2)  # ['products', leaf, rest]
            if len(parts) < 3:
                return None
            leaf = parts[1].lower()
            if leaf not in remap:
                return None
            new = f"products/{remap[leaf]}/{parts[2]}"
            return new if new != path else None

        targets = []
        for M in apps.get_app_config("catalog").get_models():
            for f in M._meta.get_fields():
                if isinstance(f, FileField):
                    targets.append((M, f.name))

        moved = errors = 0
        per_leaf: dict[str, int] = {}
        for M, fname in targets:
            qs = M.objects.filter(**{f"{fname}__startswith": "products/"}).exclude(**{fname: ""})
            for obj in qs.iterator(chunk_size=200):
                if limit and moved >= limit:
                    break
                fileobj = getattr(obj, fname, None)
                old_path = fileobj.name if fileobj else ""
                new_path = remap_path(old_path)
                if not new_path:
                    continue
                leaf = old_path.split("/", 2)[1].lower()
                per_leaf[leaf] = per_leaf.get(leaf, 0) + 1
                if dry:
                    if moved < 25:
                        self.stdout.write(f"  [{M.__name__}.{fname}#{obj.pk}] {old_path} -> {new_path}")
                    moved += 1
                    continue
                try:
                    client.copy_object(
                        Bucket=bucket,
                        CopySource={"Bucket": bucket, "Key": old_path},
                        Key=new_path,
                    )
                    client.head_object(Bucket=bucket, Key=new_path)  # verify
                    M.objects.filter(pk=obj.pk).update(**{fname: new_path})  # без сигналов
                    client.delete_object(Bucket=bucket, Key=old_path)
                    moved += 1
                except Exception as e:
                    # shadow Product и доменная модель делят один путь: первый перенёс
                    # и удалил old. Если new уже на месте — просто чиним ссылку в БД.
                    try:
                        client.head_object(Bucket=bucket, Key=new_path)
                        M.objects.filter(pk=obj.pk).update(**{fname: new_path})
                        try:
                            client.delete_object(Bucket=bucket, Key=old_path)
                        except Exception:
                            pass
                        moved += 1
                        continue
                    except Exception:
                        pass
                    errors += 1
                    self.stderr.write(f"  ERR {M.__name__}.{fname}#{obj.pk} {old_path}: {e}")

        self.stdout.write("--- по leaf-папкам ---")
        for leaf, n in sorted(per_leaf.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {leaf}: {n}")
        self.stdout.write(f"=== {'DRY-RUN ' if dry else ''}перенесено={moved} ошибок={errors} ===")
