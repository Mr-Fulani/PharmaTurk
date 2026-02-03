"""Оптимизация изображений перед загрузкой в R2/локальное хранилище."""
from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image


class ImageOptimizer:
    """Сжатие и изменение размера изображений."""

    THUMBNAIL_SIZES = {
        "small": (150, 150),
        "medium": (600, 600),
        "large": (1200, 1200),
    }

    def optimize_image(
        self,
        image_file,
        quality=85,
        max_size=(2000, 2000),
        output_format="JPEG",
    ):
        """
        Сжатие и изменение размера изображения.

        Args:
            image_file: file-like объект или путь (открытый для чтения)
            quality: качество JPEG (1-100)
            max_size: максимальные (width, height)
            output_format: 'JPEG' или 'PNG'

        Returns:
            InMemoryUploadedFile: оптимизированное изображение
        """
        if hasattr(image_file, "seek"):
            image_file.seek(0)
        img = Image.open(image_file)

        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        output = BytesIO()
        img.save(output, format=output_format, quality=quality, optimize=True)
        output.seek(0)

        name = "image.jpg"
        if hasattr(image_file, "name"):
            base = (image_file.name or "image").rsplit(".", 1)[0]
            name = f"{base}.jpg"

        return InMemoryUploadedFile(
            output,
            "ImageField",
            name,
            "image/jpeg",
            output.getbuffer().nbytes,
            None,
        )

    def create_thumbnails(self, image_file):
        """
        Создание thumbnails разных размеров.

        Args:
            image_file: file-like объект

        Returns:
            dict: {size_name: InMemoryUploadedFile}
        """
        if hasattr(image_file, "seek"):
            image_file.seek(0)
        img = Image.open(image_file)

        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        result = {}
        base_name = "image"
        if hasattr(image_file, "name"):
            base_name = (image_file.name or "image").rsplit(".", 1)[0]

        for size_name, dimensions in self.THUMBNAIL_SIZES.items():
            thumb = img.copy()
            thumb.thumbnail(dimensions, Image.Resampling.LANCZOS)
            output = BytesIO()
            thumb.save(output, format="JPEG", quality=85, optimize=True)
            output.seek(0)
            result[size_name] = InMemoryUploadedFile(
                output,
                "ImageField",
                f"{base_name}_{size_name}.jpg",
                "image/jpeg",
                output.getbuffer().nbytes,
                None,
            )
        return result
