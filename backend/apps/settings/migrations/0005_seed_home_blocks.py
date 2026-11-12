from django.db import migrations

# Нынешний порядок блоков главной (frontend/src/pages/index.tsx): сайт после
# миграции выглядит так же, пока порядок и галочки не поменяют в админке.
HOME_BLOCKS = [
    "main_banner",
    "brands",
    "banner_after_brands",
    "categories",
    "banner_before_footer",
    "bestsellers",
    "sourcing",
    "recommendations",
    "banner_after_popular",
    "testimonials",
    "facts",
]


def seed_home_blocks(apps, schema_editor):
    HomeBlock = apps.get_model("settings", "HomeBlock")
    TestimonialSectionSettings = apps.get_model("feedback", "TestimonialSectionSettings")
    # Галочка «Показывать блок отзывов на главной» переезжает сюда со своим значением;
    # без записи настроек блок был скрыт (default=False).
    testimonials_shown = bool(
        TestimonialSectionSettings.objects.filter(pk=1).values_list("show_on_homepage", flat=True).first()
    )
    for position, key in enumerate(HOME_BLOCKS, start=1):
        HomeBlock.objects.get_or_create(
            key=key,
            defaults={
                "sort_order": position * 10,
                "is_enabled": testimonials_shown if key == "testimonials" else True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("settings", "0004_site_appearance_home_blocks"),
        ("feedback", "0014_feedback_translations"),
    ]

    operations = [
        migrations.RunPython(seed_home_blocks, migrations.RunPython.noop),
    ]
