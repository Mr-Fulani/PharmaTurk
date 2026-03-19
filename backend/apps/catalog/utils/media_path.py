"""Нормализация путей медиа (устранение дублирования из-за бага upload_to)."""


def normalize_duplicated_media_path(path):
    """
    Убрать дублирование префикса в пути.
    До фикса basename в сигнале путь в БД мог быть:
    products/clothing/gallery/products/clothing/gallery/xxx.jpg
    Возвращает: products/clothing/gallery/xxx.jpg
    """
    if not path or "/" not in path:
        return path
    parts = path.split("/")
    n = len(parts)
    for i in range(1, (n // 2) + 1):
        if parts[:i] == parts[i : 2 * i]:
            return "/".join(parts[:i] + parts[2 * i :])
    return path
