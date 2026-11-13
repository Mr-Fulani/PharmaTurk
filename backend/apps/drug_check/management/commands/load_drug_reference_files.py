"""Загрузка справочных файлов проверки лекарств: SKRS E-Reçete TİTCK и прайс склада.

    manage.py load_drug_reference_files                 # все источники, только новые файлы
    manage.py load_drug_reference_files --source skrs --force
    manage.py load_drug_reference_files --source selcuk --file WEBLISTE-13-10-2026.xlsx

Сеть: страница источника и файл (2 запроса на источник), без прокси; файл на диск не пишется.
Каталог не меняется — см. docs/DRUG_CHECK.md.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.drug_check.models import DrugReferenceLoad
from apps.drug_check.sources import file_sources, get_source


class Command(BaseCommand):
    help = "Загрузить списки SKRS (TİTCK) и прайс склада для проверки лекарств."

    def add_arguments(self, parser):
        keys = [source.key for source in file_sources()]
        parser.add_argument("--source", choices=keys, help="Только этот источник.")
        parser.add_argument("--force", action="store_true", help="Загрузить, даже если файл тот же.")
        parser.add_argument("--file", help="Загрузить из локального файла вместо скачивания (нужен --source).")

    def handle(self, *args, **options):
        if options["file"]:
            if not options["source"]:
                raise CommandError("--file требует --source")
            path = Path(options["file"])
            if not path.is_file():
                raise CommandError(f"нет файла {path}")
            source = get_source(options["source"])
            try:  # дата — из имени файла, как на странице источника
                _url, _name, file_date = source.find_file_url(f'href="{path.name}"')
            except ValueError:
                file_date = None
            load = source.load_content(path.read_bytes(), file_name=path.name, file_date=file_date)
            self._report(options["source"], load)
            return
        sources = [get_source(options["source"])] if options["source"] else file_sources()
        failed = False
        for source in sources:
            load = source.download_and_load(force=options["force"])
            self._report(source.key, load)
            failed = failed or load.result == DrugReferenceLoad.Result.FAILED
        if failed:
            raise CommandError("часть файлов не загрузилась — см. «Загрузки справочных файлов» в админке")

    def _report(self, key, load):
        date = load.file_date.strftime("%d.%m.%Y") if load.file_date else "?"
        self.stdout.write(f"{key}: {load.get_result_display()} — {load.file_name or '-'} от {date}, строк {load.rows}. {load.message}")
