"""Сервис анализа изображений товара через Vision API."""

from typing import Any, Dict, List


def analyze_product_images(
    images_data: List[Dict],
    prompt: str,
    llm_client: Any,
) -> Dict:
    """
    Вызывает LLM Vision API для анализа изображений товара.
    Возвращает словарь в формате для лога (например {"content": ...}).
    """
    if not images_data or not prompt or not llm_client:
        return {}

    result = llm_client.analyze_images(images=images_data, prompt=prompt)
    if not isinstance(result, dict):
        return {}
    # Сохраняем в том же формате, что ожидает лог (image_analysis)
    return result if "content" in result else {"content": result}
