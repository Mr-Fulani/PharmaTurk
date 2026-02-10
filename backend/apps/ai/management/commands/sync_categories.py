"""Синхронизация категорий из БД в Qdrant (эмбеддинги для RAG)."""
from django.core.management.base import BaseCommand
from apps.catalog.models import Category
from apps.ai.services.vector_store import QdrantManager
from apps.ai.services.llm_client import LLMClient


class Command(BaseCommand):
    help = "Загрузить категории в Qdrant с эмбеддингами для поиска"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch",
            type=int,
            default=50,
            help="Размер батча (по умолчанию 50)",
        )

    def handle(self, *args, **options):
        batch_size = options["batch"]
        try:
            vs = QdrantManager()
            llm = LLMClient()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Init failed: {e}"))
            return
        categories = Category.objects.select_related("parent", "category_type").all()
        total = 0
        for cat in categories:
            try:
                text = f"{cat.name} {cat.description or ''} {cat.parent.name if cat.parent else ''} {cat.category_type.name if cat.category_type else ''}"
                text = (text or cat.slug or str(cat.id))[:8000].strip()
                embedding = llm.get_embedding(text)
                payload = {
                    "category_name": cat.name,
                    "parent": cat.parent.name if cat.parent else "",
                    "slug": cat.slug or "",
                    "examples": cat.description or "",
                }
                vs.upsert_category(cat.id, embedding, payload)
                total += 1
                if total % batch_size == 0:
                    self.stdout.write(f"Synced {total} categories...")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Skip category {cat.id}: {e}"))
        self.stdout.write(self.style.SUCCESS(f"Synced {total} categories to Qdrant."))
