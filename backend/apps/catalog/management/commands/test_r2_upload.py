"""Проверка загрузки и удаления файлов в R2/локальное хранилище."""
from io import BytesIO

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from PIL import Image


class Command(BaseCommand):
    help = "Тест загрузки и удаления файла в default_storage (R2 или локальный диск)"

    def handle(self, *args, **options):
        # Создаем минимальное тестовое изображение (1x1 пиксель)
        img = Image.new("RGB", (1, 1), color="red")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)

        test_path = "test/r2_test.jpg"
        try:
            path = default_storage.save(test_path, buf)
            url = default_storage.url(path)
            self.stdout.write(self.style.SUCCESS(f"Upload OK: {path} -> {url}"))
            default_storage.delete(path)
            self.stdout.write(self.style.SUCCESS("Delete OK"))
            self.stdout.write(self.style.SUCCESS("R2/storage test passed."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Test failed: {e}"))
