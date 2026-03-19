"""Одной командой: init_qdrant + sync_categories + import_templates (подготовка RAG)."""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Подготовить RAG: создать коллекции Qdrant и загрузить категории и шаблоны"

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-categories",
            action="store_true",
            help="Не запускать sync_categories",
        )
        parser.add_argument(
            "--skip-templates",
            action="store_true",
            help="Не запускать import_templates",
        )

    def handle(self, *args, **options):
        self.stdout.write("1/3 init_qdrant...")
        call_command("init_qdrant")
        if not options["skip_categories"]:
            self.stdout.write("2/3 sync_categories...")
            call_command("sync_categories")
        else:
            self.stdout.write("2/3 sync_categories skipped")
        if not options["skip_templates"]:
            self.stdout.write("3/3 import_templates...")
            call_command("import_templates")
        else:
            self.stdout.write("3/3 import_templates skipped")
        self.stdout.write(self.style.SUCCESS("RAG setup done."))
