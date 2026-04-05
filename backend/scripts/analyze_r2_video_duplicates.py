#!/usr/bin/env python3
"""
Разовый отчёт: признаки дублирования видео (parsed/ + main/videos/) у книг.

Запуск из каталога backend:
  poetry run python scripts/analyze_r2_video_duplicates.py

Не удаляет файлы — только печатает статистику и примеры id.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.catalog.models import BookProductImage, Product  # noqa: E402


def main() -> None:
    # Типичный след старого бага: внешний video_url и файл уже в products/.../main/videos/
    qs = (
        Product.objects.filter(product_type="books")
        .exclude(main_video_file="")
        .exclude(main_video_file__isnull=True)
    )
    legacy_dup = []
    for p in qs.iterator(chunk_size=200):
        vu = (p.video_url or "").strip()
        mf = (p.main_video_file.name or "").replace("\\", "/")
        if not vu or not mf:
            continue
        if "/main/videos/" in mf and vu.startswith("http") and "/products/parsed/" not in vu:
            legacy_dup.append(p.pk)

    book_videos_in_gallery = BookProductImage.objects.exclude(video_url="").exclude(
        video_url__isnull=True
    )
    parsed_in_gallery = book_videos_in_gallery.filter(video_url__contains="/products/parsed/").count()

    print("=== Анализ видео (книги) ===")
    print(f"Product (books) с main_video_file и внешним video_url (кандидаты на старый дубль): {len(legacy_dup)}")
    if legacy_dup[:15]:
        print(f"  примеры product id: {legacy_dup[:15]}")
    print(f"BookProductImage с непустым video_url: {book_videos_in_gallery.count()}")
    print(f"  из них ссылка на parsed/: {parsed_in_gallery}")


if __name__ == "__main__":
    main()
