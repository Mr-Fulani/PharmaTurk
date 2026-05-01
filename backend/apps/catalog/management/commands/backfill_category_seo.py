from django.core.management.base import BaseCommand

from apps.catalog.models import Category


class Command(BaseCommand):
    help = "Заполняет пустые SEO/OG поля категорий безопасными fallback-значениями."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать, что будет обновлено, без сохранения в базу.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        updated = 0

        for category in Category.objects.select_related("parent").all():
            changed_fields = []

            if not (category.meta_title or "").strip():
                category.meta_title = category.build_default_meta_title()
                changed_fields.append("meta_title")
            if not (category.meta_description or "").strip():
                category.meta_description = category.build_default_meta_description()
                changed_fields.append("meta_description")
            if not (category.meta_keywords or "").strip():
                category.meta_keywords = category.build_default_meta_keywords()
                changed_fields.append("meta_keywords")
            if not (category.og_title or "").strip():
                category.og_title = category.get_effective_og_title()
                changed_fields.append("og_title")
            if not (category.og_description or "").strip():
                category.og_description = category.get_effective_og_description()
                changed_fields.append("og_description")
            if not (category.og_image_url or "").strip():
                next_og_image = category.get_effective_og_image_url()
                if next_og_image:
                    category.og_image_url = next_og_image
                    changed_fields.append("og_image_url")

            if not changed_fields:
                continue

            updated += 1
            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] {category.id} {category.slug}: {', '.join(changed_fields)}"
                )
                continue

            category.save(update_fields=changed_fields)
            self.stdout.write(
                f"Updated {category.id} {category.slug}: {', '.join(changed_fields)}"
            )

        summary = f"{updated} categories {'would be updated' if dry_run else 'updated'}."
        self.stdout.write(self.style.SUCCESS(summary))
