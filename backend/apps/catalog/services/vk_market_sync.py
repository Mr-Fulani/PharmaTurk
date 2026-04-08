"""
Сервис синхронизации фото товаров с VK Маркетом через VK API.

Документация VK API:
  https://dev.vk.com/method/market.get
  https://dev.vk.com/method/photos.getMarketUploadServer
  https://dev.vk.com/method/photos.saveMarketPhoto
  https://dev.vk.com/method/market.edit
"""
from __future__ import annotations

import io
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

VK_API_URL = "https://api.vk.com/method"
VK_API_VERSION = "5.131"


class VKAPIError(Exception):
    """Ошибка при вызове VK API."""


class VKMarketSync:
    """
    Клиент для синхронизации фото товаров ВК Маркет через API.

    Алгоритм работы:
    1. Получаем все товары из группы ВК (market.get) с external_id.
    2. Для каждого товара с external_id, соответствующим нашему offer:
       - Загружаем все картинки через photos.getMarketUploadServer.
       - Первая картинка → главное фото (main_photo=1).
       - Остальные → доп. фото (main_photo=0).
       - Обновляем market.edit с id главного фото.
    """

    # VK личный кабинет разрешает ~3 запроса/сек для большинства методов
    REQUEST_DELAY = 0.4

    def __init__(self, token: str, group_id: int):
        self.token = token
        self.group_id = group_id
        self.owner_id = -abs(group_id)  # owner_id для группы — отрицательный

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _api(self, method: str, params: dict) -> dict | list:
        """Выполняет GET-запрос к VK API. Возвращает поле response."""
        time.sleep(self.REQUEST_DELAY)
        resp = requests.get(
            f"{VK_API_URL}/{method}",
            params={
                "access_token": self.token,
                "v": VK_API_VERSION,
                **params,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            err = data["error"]
            raise VKAPIError(
                f"[{err.get('error_code')}] {err.get('error_msg')}"
            )
        return data["response"]

    def _download_image(self, url: str) -> tuple[bytes, str]:
        """Скачивает изображение по URL. Возвращает (bytes, filename)."""
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        filename = url.split("/")[-1].split("?")[0] or "image.jpg"
        # Убедимся, что расширение есть
        if not any(filename.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
            filename += ".jpg"
        return resp.content, filename

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def get_all_market_items(self) -> list[dict]:
        """
        Загружает все товары из группы ВК постранично.
        Возвращает список словарей с полями: id, title, external_id, ...
        """
        items: list[dict] = []
        offset = 0
        page_size = 200  # максимум

        while True:
            response = self._api("market.get", {
                "owner_id": self.owner_id,
                "count": page_size,
                "offset": offset,
                "extended": 1,
            })
            batch = response.get("items", [])
            items.extend(batch)
            logger.debug(f"Loaded {len(batch)} items (offset={offset})")

            if len(batch) < page_size:
                break  # последняя страница
            offset += page_size

        logger.info(f"Total VK market items: {len(items)} (group {self.group_id})")
        return items

    def upload_photo(
        self,
        image_url: str,
        is_main: bool = True,
        vk_item_id: Optional[int] = None,
    ) -> Optional[dict]:
        """
        Загружает одно фото в VK.

        Args:
            image_url: URL исходного изображения.
            is_main: True — главное фото (main_photo=1), False — доп. фото.
            vk_item_id: ID товара в ВК (нужен для доп. фото к конкретному товару).

        Returns:
            dict с полями id, owner_id из VK, или None при ошибке.
        """
        try:
            # 1. Получаем URL загрузки
            upload_params: dict = {
                "group_id": self.group_id,
                "main_photo": 1 if is_main else 0,
            }
            if not is_main and vk_item_id:
                upload_params["product_id"] = vk_item_id

            upload_server = self._api("photos.getMarketUploadServer", upload_params)
            upload_url = upload_server["upload_url"]

            # 2. Скачиваем исходное изображение
            img_bytes, filename = self._download_image(image_url)

            # 3. Загружаем в VK
            time.sleep(self.REQUEST_DELAY)
            upload_resp = requests.post(
                upload_url,
                files={"file": (filename, io.BytesIO(img_bytes), "image/jpeg")},
                timeout=60,
            )
            upload_resp.raise_for_status()
            upload_result = upload_resp.json()

            # 4. Сохраняем в VK
            save_params: dict = {
                "group_id": self.group_id,
                "photo": upload_result.get("photo", ""),
                "server": upload_result.get("server", ""),
                "hash": upload_result.get("hash", ""),
            }
            # Главное фото требует crop-данные (передаём пустые если нет)
            if is_main:
                save_params["crop_data"] = upload_result.get("crop_data") or ""
                save_params["crop_hash"] = upload_result.get("crop_hash") or ""

            saved = self._api("photos.saveMarketPhoto", save_params)
            photo = saved[0] if isinstance(saved, list) else saved
            logger.debug(f"Saved photo id={photo.get('id')} owner={photo.get('owner_id')}")
            return photo

        except Exception as e:
            logger.warning(f"Failed to upload photo {image_url!r}: {e}")
            return None

    def set_main_photo(self, vk_item_id: int, photo_owner_id: int, photo_id: int) -> bool:
        """Устанавливает главное фото товара в ВК Маркете."""
        photo_id_str = f"{photo_owner_id}_{photo_id}"
        try:
            self._api("market.edit", {
                "owner_id": self.owner_id,
                "item_id": vk_item_id,
                "photo_id": photo_id_str,
            })
            logger.debug(f"Set main photo {photo_id_str} for item {vk_item_id}")
            return True
        except VKAPIError as e:
            logger.warning(f"Failed to set main photo for item {vk_item_id}: {e}")
            return False

    def sync_item_photos(
        self,
        vk_item_id: int,
        image_urls: list[str],
    ) -> dict:
        """
        Загружает все картинки и устанавливает их на товар в ВК Маркете.

        Args:
            vk_item_id: ID товара в ВК.
            image_urls: Список URL картинок. Первый — главное фото.

        Returns:
            {'uploaded': N, 'failed': N}
        """
        if not image_urls:
            return {"uploaded": 0, "failed": 0}

        uploaded = 0
        failed = 0
        main_photo: Optional[dict] = None

        for i, url in enumerate(image_urls):
            is_main = (i == 0)
            photo = self.upload_photo(url, is_main=is_main, vk_item_id=vk_item_id)

            if photo:
                uploaded += 1
                if is_main:
                    main_photo = photo
            else:
                failed += 1

        # Устанавливаем главное фото (если успешно загружено)
        if main_photo:
            self.set_main_photo(
                vk_item_id=vk_item_id,
                photo_owner_id=main_photo["owner_id"],
                photo_id=main_photo["id"],
            )

        return {"uploaded": uploaded, "failed": failed}
