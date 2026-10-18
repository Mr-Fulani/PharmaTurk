"""Битые ссылки на медиа каталога (dry-run по умолчанию).

Ссылка битая, если файла нет в R2 или он нулевого размера. Для каждой пары
«файл + URL» (image_file/image_url, main_image_file/main_image, ...):

- repoint    — одна половина пары жива: вторая перенаправляется на неё;
- redownload — у записи есть внешний URL источника: файл скачивается заново;
- rescrape   — у товара есть страница источника (external_url): товар перескрейпивается;
- delete     — источника нет: строка галереи удаляется, поля товара очищаются.

То, что осталось битым после перекачки/перескрейпа, удаляется как delete.
Файлы без ссылок из БД команда не ищет — это cleanup_orphaned_media.

    manage.py repair_broken_media                  # отчёт CSV, без изменений
    manage.py repair_broken_media --apply          # исправить
    manage.py repair_broken_media --apply --no-rescrape
"""
import csv
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlparse

from django.apps import apps
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db.models import FileField, URLField
from django.utils import timezone

from apps.catalog.tasks import _normalize_media_path

PAIRS = (
    ("image_file", "image_url"),
    ("main_image_file", "main_image"),
    ("video_file", "video_url"),
    ("main_video_file", "video_url"),
)
NON_MEDIA_URL_FIELDS = {"external_url", "link_url", "website"}
MIN_STORAGE_OBJECTS = 1000
MAX_BROKEN_SHARE = 0.2


def list_storage_objects() -> dict:
    """Все ключи хранилища {key: size} одним листингом бакета."""
    location = (getattr(default_storage, "location", "") or "").strip("/")
    prefix = f"{location}/" if location else ""
    return {
        obj.key[len(prefix):]: obj.size
        for obj in default_storage.bucket.objects.filter(Prefix=prefix)
    }


def own_media_host() -> str:
    public_url = (getattr(settings, "R2_CONFIG", {}) or {}).get("public_url", "") or ""
    return urlparse(public_url).netloc or (getattr(default_storage, "custom_domain", "") or "")


@dataclass
class BrokenGroup:
    model: type
    pk: int
    fields: tuple  # поля группы, присутствующие у модели
    values: dict
    status: dict  # поле → ok / missing / zero / external / empty
    action: str = ""
    source_url: str = ""
    category_id: int | None = None
    notes: list = field(default_factory=list)


def _media_groups(model):
    names = {
        f.name for f in model._meta.get_fields()
        if isinstance(f, FileField) or (isinstance(f, URLField) and f.name not in NON_MEDIA_URL_FIELDS)
    }
    groups = []
    for file_name, url_name in PAIRS:
        if file_name in names:
            grouped_urls = {g[1] for g in groups if len(g) == 2}
            groups.append((file_name, url_name) if url_name in names - grouped_urls else (file_name,))
    grouped = {n for g in groups for n in g}
    groups.extend((n,) for n in sorted(names - grouped))
    return groups


def _is_gallery_row(model) -> bool:
    field_names = {f.name for f in model._meta.get_fields()}
    return model.__name__.endswith("Image") and bool(field_names & {"product", "variant"})


class Command(BaseCommand):
    help = "Битые ссылки на медиа каталога: перекачать по источнику или удалить (по умолчанию dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Исправить (иначе только отчёт).")
        parser.add_argument("--no-rescrape", action="store_true", help="Не перескрейпивать товары.")
        parser.add_argument("--report", default="", help="Путь CSV-отчёта (по умолчанию /tmp/...).")

    def handle(self, *args, **options):
        apply = options["apply"]
        report_path = options["report"] or f"/tmp/broken_media_{timezone.now():%Y%m%d_%H%M%S}.csv"
        self.host = own_media_host()

        self.objects = list_storage_objects()
        if len(self.objects) < MIN_STORAGE_OBJECTS or not any(k.startswith("products/") for k in self.objects):
            raise CommandError(
                f"Листинг хранилища подозрительно мал ({len(self.objects)} объектов) — остановка."
            )

        checked, groups = self._scan()
        if checked and len(groups) > checked * MAX_BROKEN_SHARE:
            raise CommandError(
                f"Битых {len(groups)} из {checked} ссылок (> {MAX_BROKEN_SHARE:.0%}) — "
                "похоже на сбой листинга или чужое хранилище, остановка."
            )
        for group in groups:
            self._classify(group)

        counts = defaultdict(int)
        for group in groups:
            counts[group.action] += 1
        rescrape_urls = {g.source_url for g in groups if g.action == "rescrape"}
        self.stdout.write(
            f"{'APPLY' if apply else 'DRY-RUN'}: объектов_в_хранилище={len(self.objects)} "
            f"ссылок={checked} битых={len(groups)} "
            + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            + f" товаров_к_перескрейпу={len(rescrape_urls)}"
        )

        if apply:
            self._apply(groups, rescrape=not options["no_rescrape"])
        self._write_report(report_path, groups)
        self.stdout.write(f"Отчёт: {report_path}")

    # ── сканирование ─────────────────────────────────────────────────────

    def _field_status(self, model, name, value, live_check=None):
        if not value:
            return "empty"
        if isinstance(model._meta.get_field(name), FileField):
            return self._file_status(value, live_check)
        return self._url_status(value, live_check)

    def _scan(self):
        checked = 0
        broken = []
        for model in apps.get_app_config("catalog").get_models():
            if model._meta.proxy:
                continue
            groups = _media_groups(model)
            if not groups:
                continue
            names = [n for g in groups for n in g]
            for row in model._base_manager.values("pk", *names).iterator(chunk_size=2000):
                for group_fields in groups:
                    status = {n: self._field_status(model, n, row[n] or "") for n in group_fields}
                    if any(s in ("ok", "missing", "zero") for s in status.values()):
                        checked += 1
                    if any(s in ("missing", "zero") for s in status.values()):
                        broken.append(BrokenGroup(
                            model=model, pk=row["pk"], fields=group_fields,
                            values={n: row[n] or "" for n in group_fields}, status=status,
                        ))
        return checked, broken

    def _file_status(self, name, live_check=None):
        path = _normalize_media_path(name)
        if live_check is not None:
            return "ok" if live_check(path) else "missing"
        if path not in self.objects:
            return "missing"
        return "zero" if self.objects[path] == 0 else "ok"

    def _url_status(self, value, live_check=None):
        parsed = urlparse(value)
        own = parsed.netloc == self.host if parsed.netloc else parsed.path.startswith(("/media/", "/products/"))
        if not own:
            return "external"
        return self._file_status(parsed.path, live_check)

    # ── классификация ────────────────────────────────────────────────────

    def _classify(self, group: BrokenGroup, download_failed=False):
        statuses = set(group.status.values())
        if "ok" in statuses:
            group.action = "repoint"
            return
        if "external" in statuses and not download_failed:
            group.action = "redownload"
            return
        source_url, category_id = self._owner_source(group.model, group.pk)
        group.category_id = category_id
        if source_url and self._scraper_for(source_url):
            group.action, group.source_url = "rescrape", source_url
        else:
            group.action = "delete"

    def _owner_source(self, model, pk):
        """Страница источника и категория владельца: картинка → вариант → товар."""
        chain = [model._base_manager.get(pk=pk)]
        for attr in ("variant", "product"):
            node = chain[-1]
            fk_names = {f.name for f in node._meta.get_fields() if f.many_to_one}
            parent = getattr(node, attr, None) if attr in fk_names else None
            if parent is not None:
                chain.append(parent)
        source_url = next((n.external_url for n in chain if getattr(n, "external_url", "")), "")
        category_id = next((n.category_id for n in reversed(chain) if getattr(n, "category_id", None)), None)
        return source_url, category_id

    def _scraper_for(self, url):
        from apps.scrapers.models import ScraperConfig

        if not hasattr(self, "_scrapers"):
            self._scrapers = {
                urlparse(cfg.base_url).netloc.removeprefix("www."): cfg
                for cfg in ScraperConfig.objects.filter(is_enabled=True)
            }
        return self._scrapers.get(urlparse(url).netloc.removeprefix("www."))

    # ── исправление ──────────────────────────────────────────────────────

    def _apply(self, groups, rescrape):
        for group in groups:
            if group.action == "repoint":
                self._repoint(group)
            elif group.action == "redownload" and not self._redownload(group):
                group.notes.append("redownload_failed")
                self._classify(group, download_failed=True)

        if rescrape:
            pending = [g for g in groups if g.action == "rescrape"]
            for url in sorted({g.source_url for g in pending}):
                category_id = next(g.category_id for g in pending if g.source_url == url)
                ok = self._rescrape(url, category_id)
                for g in pending:
                    if g.source_url == url:
                        g.notes.append("rescraped" if ok else "rescrape_failed")
            for g in pending:
                self._reclassify_after_rescrape(g)

        for group in groups:
            if group.action == "delete":
                self._delete(group)
                group.notes.append("deleted")

    def _zero_size_paths(self, group):
        paths = []
        for name, status in group.status.items():
            if status == "zero":
                value = group.values[name]
                paths.append(_normalize_media_path(urlparse(value).path if "://" in value else value))
        return paths

    def _drop_zero_size_files(self, group):
        from apps.catalog.signals import _delete_storage_key_if_unreferenced

        for path in self._zero_size_paths(group):
            _delete_storage_key_if_unreferenced(path)

    def _repoint(self, group):
        file_name, url_name = group.fields  # «ok» рядом с битым бывает только в паре
        updates = {}
        if group.status[file_name] == "ok":
            updates[url_name] = default_storage.url(_normalize_media_path(group.values[file_name]))
        else:
            updates[file_name] = _normalize_media_path(urlparse(group.values[url_name]).path)
        group.model._base_manager.filter(pk=group.pk).update(**updates)
        self._drop_zero_size_files(group)

    def _redownload(self, group) -> bool:
        from apps.catalog.signals import _auto_download_impl

        if len(group.fields) != 2:
            return False
        file_name, url_name = group.fields
        instance = group.model._base_manager.get(pk=group.pk)
        setattr(instance, file_name, None)
        try:
            _auto_download_impl(instance, field_name=file_name, url_field=url_name)
            downloaded = getattr(instance, file_name)
            if not downloaded or getattr(downloaded, "_committed", True):
                return False
            # Хелпер только присваивает ContentFile — в хранилище его кладёт save()
            instance.save(update_fields=[file_name])
        except Exception as exc:
            group.notes.append(f"error:{exc}")
            return False
        self._drop_zero_size_files(group)
        return True

    def _rescrape(self, url, category_id) -> bool:
        from apps.catalog.models import Category
        from apps.scrapers.services import ScraperIntegrationService

        config = self._scraper_for(url)
        category = Category.objects.filter(pk=category_id).first() if category_id else None
        try:
            session = ScraperIntegrationService().run_scraper(
                config, start_url=url, max_pages=1, max_products=1, target_category=category,
            )
        except Exception as exc:
            self.stderr.write(f"rescrape {url}: {exc}")
            return False
        return getattr(session, "status", "") == "completed"

    def _reclassify_after_rescrape(self, group):
        """Новые файлы в листинге ещё не видны — проверяем точечно через exists()."""
        row = group.model._base_manager.filter(pk=group.pk).values(*group.fields).first()
        if row is None:  # строку галереи заменил перескрейп
            group.action = "fixed_by_rescrape"
            return
        group.values = {n: row[n] or "" for n in group.fields}
        group.status = {
            n: self._field_status(group.model, n, group.values[n], default_storage.exists)
            for n in group.fields
        }
        statuses = set(group.status.values())
        if "missing" not in statuses:
            group.action = "fixed_by_rescrape"
        elif "ok" in statuses:
            group.action = "repoint"
            self._repoint(group)
        else:
            group.notes.append("still_broken")
            group.action = "delete"

    def _delete(self, group):
        if _is_gallery_row(group.model) and {"image_file", "image_url"} & set(group.fields):
            instance = group.model._base_manager.filter(pk=group.pk).first()
            if instance is not None:
                instance.delete()  # post_delete-сигналы уберут файлы без ссылок
            return
        group.model._base_manager.filter(pk=group.pk).update(**{name: "" for name in group.fields})
        self._drop_zero_size_files(group)

    def _write_report(self, path, groups):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["model", "pk", "action", "fields", "status", "values", "source_url", "notes"])
            for g in groups:
                writer.writerow([
                    g.model._meta.label, g.pk, g.action, "|".join(g.fields),
                    "|".join(f"{k}={v}" for k, v in g.status.items()),
                    " | ".join(str(g.values[n]) for n in g.fields), g.source_url, "|".join(g.notes),
                ])
