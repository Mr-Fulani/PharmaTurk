import json

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.services.category_landing_seo import (
    apply_texts,
    collect_facts,
    generate_checked,
    select_categories,
    validate_texts,
)


def _csv(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


class Command(BaseCommand):
    help = (
        "SEO посадочных страниц разделов через Claude. generate — пишет черновик в JSON "
        "(база не меняется), apply — записывает проверенный черновик в пустые поля переводов."
    )

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)

        generate = sub.add_parser("generate", help="Черновик текстов в JSON, без записи в базу.")
        generate.add_argument("--slugs", default="", help="Разделы через запятую.")
        generate.add_argument("--roots", default="", help="Корни целиком через запятую (supplements,clothing…).")
        generate.add_argument("--include-filled", action="store_true", help="Не пропускать разделы с SEO-текстом.")
        generate.add_argument("--limit", type=int, default=0, help="Не больше N разделов (пилот).")
        generate.add_argument("--min-products", type=int, default=1, help="Пропускать разделы, где товаров меньше.")
        generate.add_argument("--out", required=True, help="Куда записать JSON черновика.")
        generate.add_argument(
            "--model", default="",
            help="Модель Claude (по умолчанию AI_ANTHROPIC_MODEL). Тексты разделов 27.10.2026 — claude-sonnet-5-5.",
        )

        apply = sub.add_parser("apply", help="Записать черновик в CategoryTranslation.")
        apply.add_argument("--file", required=True, help="JSON от generate.")
        apply.add_argument("--slugs", default="", help="Только эти разделы из файла.")
        apply.add_argument("--backup", required=True, help="Куда записать прежние значения полей.")
        apply.add_argument("--overwrite", action="store_true", help="Перезаписывать непустые поля.")
        apply.add_argument("--dry-run", action="store_true", help="Показать изменения без записи.")

    def handle(self, *args, **options):
        if options["action"] == "generate":
            self._generate(options)
        else:
            self._apply(options)

    def _generate(self, options):
        slugs, roots = _csv(options["slugs"]), _csv(options["roots"])
        if not slugs and not roots:
            raise CommandError("Укажите --slugs или --roots.")
        categories = select_categories(
            slugs=slugs, roots=roots, include_filled=options["include_filled"], min_products=options["min_products"],
        )
        if options["limit"]:
            categories = categories[: options["limit"]]
        if not categories:
            self.stdout.write("Разделов для текстов нет.")
            return

        from apps.ai.services.claude_client import ClaudeClient, claude_usage

        client = ClaudeClient(model=options["model"] or None)
        entries, tokens_in, tokens_out = [], 0, 0
        for category in categories:
            facts = collect_facts(category)
            texts, problems, raw, usages = generate_checked(facts, client)
            for usage in usages:
                used_in, _, used_out = claude_usage(usage)
                tokens_in += used_in
                tokens_out += used_out
            entry = {
                "slug": category.slug,
                "name_en": facts["name_en"],
                "facts": facts,
                "texts": texts,
                "problems": problems,
            }
            if problems:
                # Сырой ответ — чтобы разобрать сбой формата без повторного платного запроса.
                entry["raw"] = raw
            entries.append(entry)
            status = "ок" if not problems else "; ".join(problems)
            self.stdout.write(f"{category.slug}: {status}")

        with open(options["out"], "w", encoding="utf-8") as fh:
            json.dump(entries, fh, ensure_ascii=False, indent=1)
        clean = sum(1 for entry in entries if not entry["problems"])
        self.stdout.write(self.style.SUCCESS(
            f"Готово: {len(entries)} разделов, без замечаний {clean}; "
            f"токены: вход {tokens_in}, выход {tokens_out}. Черновик: {options['out']}"
        ))

    def _apply(self, options):
        with open(options["file"], encoding="utf-8") as fh:
            entries = json.load(fh)
        only = set(_csv(options["slugs"]))
        if only:
            entries = [entry for entry in entries if entry["slug"] in only]
        with_problems = [entry["slug"] for entry in entries if validate_texts(entry["texts"])]
        if with_problems:
            raise CommandError(f"Есть замечания проверки, исправьте файл: {', '.join(with_problems)}")

        changes, backup = apply_texts(entries, overwrite=options["overwrite"], dry_run=options["dry_run"])
        if not options["dry_run"]:
            with open(options["backup"], "w", encoding="utf-8") as fh:
                json.dump(backup, fh, ensure_ascii=False, indent=1)
        for change in changes:
            self.stdout.write(json.dumps(change, ensure_ascii=False))
        written = sum(1 for change in changes if change.get("fields"))
        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Будет записано: {written} переводов (dry-run)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Записано: {written} переводов. Бэкап: {options['backup']}"))
