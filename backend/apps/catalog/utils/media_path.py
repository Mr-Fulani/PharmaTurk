"""Нормализация путей медиа (устранение дублирования из-за бага upload_to)."""

from __future__ import annotations


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


def expand_legacy_duplicated_storage_paths(path: str) -> list[str]:
    """
    Для старых записей: файл мог сохраниться по пути с дублированным префиксом.
    Возвращает кандидатов: path с префиксом, «раздутым» после 1, 2, 3, ... сегментов.
    """
    if not path or "/" not in path:
        return []
    parts = path.split("/")
    return ["/".join(parts[:i] + parts) for i in range(1, len(parts))]


def iter_storage_path_candidates(path: str) -> list[str]:
    """
    Все варианты относительного ключа в хранилище для одного логического файла.
    Должен совпадать с логикой proxy_media (R2_PREFIX dev/, media/, дубликаты пути).
    """
    from django.conf import settings

    if not path or path.startswith("/") or ".." in path:
        return []
    candidates: list[str] = [path]
    path_alt = normalize_duplicated_media_path(path)
    if path_alt != path:
        candidates.append(path_alt)
    candidates.extend(expand_legacy_duplicated_storage_paths(path))
    if path.startswith("media/"):
        candidates.append(path[len("media/") :])
    else:
        candidates.append(f"media/{path}")
    r2_prefix = (getattr(settings, "R2_PREFIX", "") or "").strip("/")
    if r2_prefix and path.startswith(f"{r2_prefix}/"):
        candidates.append(path[len(r2_prefix) + 1 :])
    elif r2_prefix and not path.startswith(r2_prefix):
        candidates.append(f"{r2_prefix}/{path}")
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def resolve_existing_media_storage_key(path: str) -> str | None:
    """Первый существующий в default_storage ключ из кандидатов iter_storage_path_candidates."""
    from django.core.files.storage import default_storage

    if not path:
        return None
    for candidate in iter_storage_path_candidates(path):
        try:
            if default_storage.exists(candidate):
                return candidate
        except Exception:
            continue
    return None
