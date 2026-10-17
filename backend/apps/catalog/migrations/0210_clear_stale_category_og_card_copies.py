from django.db import migrations

# Category.save() раньше копировал адрес карточки категории в og_image_url. После перезаливки
# карточек под новыми именами (и перевода в WebP) 1303 категории ссылались на удалённые файлы,
# и превью при шаринге не показывало картинку. Копии карточек убираем — превью берётся из
# актуальной карточки (Category.get_effective_og_image_url); вручную заданные картинки не трогаем.
CARD_PATH = "/marketing/cards/categories/"


def clear_card_copies(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    Category.objects.filter(og_image_url__contains=CARD_PATH).update(og_image_url="")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0209_medicine_name_partial_index"),
    ]

    operations = [
        migrations.RunPython(clear_card_copies, migrations.RunPython.noop),
    ]
