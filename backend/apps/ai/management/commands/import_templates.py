"""Импорт шаблонов AITemplate в Qdrant (эмбеддинги для RAG)."""
from django.core.management.base import BaseCommand
from apps.ai.models import AITemplate
from apps.ai.services.vector_store import QdrantManager
from apps.ai.services.llm_client import LLMClient


class Command(BaseCommand):
    help = "Загрузить AI шаблоны в Qdrant с эмбеддингами"

    def handle(self, *args, **options):
        try:
            vs = QdrantManager()
            llm = LLMClient()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Init failed: {e}"))
            return
        templates = AITemplate.objects.filter(is_active=True).select_related("category")
        total = 0
        for tpl in templates:
            try:
                text = (tpl.content or tpl.name)[:8000].strip()
                if not text:
                    continue
                embedding = llm.get_embedding(text)
                payload = {
                    "content": tpl.content,
                    "name": tpl.name,
                    "template_type": tpl.template_type,
                    "category_name": tpl.category.name if tpl.category else "",
                }
                vs.upsert_template(tpl.id, embedding, payload)
                total += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Skip template {tpl.id}: {e}"))
        self.stdout.write(self.style.SUCCESS(f"Imported {total} templates to Qdrant."))
