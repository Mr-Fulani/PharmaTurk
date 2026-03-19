"""Инициализация коллекций Qdrant для AI (categories, templates)."""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Создать коллекции Qdrant (categories, templates) если их нет"

    def handle(self, *args, **options):
        try:
            from apps.ai.services.vector_store import QdrantManager
            mgr = QdrantManager()
            mgr._ensure_collections()
            self.stdout.write(self.style.SUCCESS("Qdrant collections ready."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed: {e}"))
