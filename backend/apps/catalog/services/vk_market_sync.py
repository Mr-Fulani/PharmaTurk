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
from typing import Iterator, Optional

import requests
from PIL import Image

from ..utils.parser_media_handler import DEFAULT_MEDIA_USER_AGENT

logger = logging.getLogger(__name__)

# Адрес из официальной документации (dev.vk.ru, 31.10.2026).
VK_API_URL = "https://api.vk.ru/method"
VK_API_VERSION = "5.131"

# Паузы перед повторами запроса, секунды. 6 — слишком часто, 9 — флуд-контроль;
# 1 и 10 — сбой на стороне ВК.
RETRY_DELAYS = (2, 10, 30)
RATE_LIMIT_CODES = frozenset({6, 9})
RETRY_CODES = frozenset({1, 6, 9, 10})
ITEM_NOT_FOUND_CODE = 1403

# Требования ВК к фото товара (dev.vk.ru/en/api/upload/photo-in-market).
PHOTO_MIN_SIDE = 400
PHOTO_FORMATS = {"JPEG": "jpg", "PNG": "png", "GIF": "gif"}


class VKAPIError(Exception):
    """Ошибка при вызове VK API. Текст не содержит токен: его можно логировать."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class VKPhotoError(Exception):
    """Фото товара не скачалось или не подходит ВК. Дело в картинке, а не в API."""


class VKMarketSync:
    """
    Клиент для синхронизации фото/видео товаров ВК Маркет через API.

    Требует ОДИН пользовательский токен (VK_USER_TOKEN) с правами:
      market, photos, video, offline

    Получить токен: откройте от имени администратора группы:
    https://oauth.vk.com/authorize?client_id=APP_ID&display=page
    &redirect_uri=https://oauth.vk.com/blank.html
    &scope=market,photos,video,offline&response_type=token&v=5.131
    """

    REQUEST_DELAY = 0.4

    def __init__(self, token: str, group_id: int):
        self.token = token
        self.group_id = group_id
        self.owner_id = -abs(group_id)

    def _call(self, method: str, params: dict) -> dict | list:
        """
        Один запрос к API. Токен — в теле POST, а не в адресе: адрес попадает в текст
        исключений requests и в логи. Описание товара в адрес тоже не поместится.
        """
        try:
            resp = requests.post(
                f"{VK_API_URL}/{method}",
                data={
                    "access_token": self.token,
                    "v": VK_API_VERSION,
                    **params,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            raise VKAPIError(f"{method}: {type(e).__name__}") from None
        if "error" in data:
            err = data["error"]
            code = err.get("error_code")
            message = str(err.get("error_msg")).replace(self.token, "***")
            raise VKAPIError(f"{method}: [{code}] {message}", code=code)
        return data["response"]

    def _api(self, method: str, params: dict, *, repeatable: bool = True) -> dict | list:
        """
        VK API запрос с единым токеном: пауза под лимит частоты, повторы при сбоях.

        repeatable=False — запрос создаёт товар. После таймаута или сбоя ВК неизвестно,
        создан ли он, и повтор дал бы дубль; такой запрос повторяется, только если ВК
        явно отказал из-за частоты. Созданный товар увидит следующий запуск по артикулу.
        """
        retry_codes = RETRY_CODES if repeatable else RATE_LIMIT_CODES
        for delay in (*RETRY_DELAYS, None):
            time.sleep(self.REQUEST_DELAY)
            try:
                return self._call(method, params)
            except VKAPIError as e:
                transient = e.code in retry_codes or (e.code is None and repeatable)
                if delay is None or not transient:
                    raise
                logger.warning("VK API, повтор через %s с: %s", delay, e)
                time.sleep(delay)
        raise AssertionError("недостижимо: последний проход цикла возвращает или бросает")

    def _download_image(self, url: str) -> tuple[bytes, str]:
        """Скачивает изображение по URL. Возвращает (bytes, filename)."""
        # Без браузерного User-Agent CDN LC Waikiki и FLO отвечают 422.
        resp = requests.get(url, timeout=30, stream=True, headers={"User-Agent": DEFAULT_MEDIA_USER_AGENT})
        resp.raise_for_status()
        filename = url.split("/")[-1].split("?")[0] or "image.jpg"
        # Убедимся, что расширение есть
        if not any(filename.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
            filename += ".jpg"
        return resp.content, filename

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def iter_market_items(self, include_hidden: bool = False) -> Iterator[dict]:
        """
        Товары группы постранично, без накопления в памяти.

        include_hidden: ещё скрытые товары и варианты. В ответе они идут отдельным
        массивом variants (need_variants): без него вариант выглядел бы как новый товар.
        Неполный список — ошибка: по нему нельзя решать, что добавить и что удалить.
        """
        page_size = 200
        params: dict = {"owner_id": self.owner_id, "count": page_size, "extended": 1}
        if include_hidden:
            params.update({"with_disabled": 1, "need_variants": 1})

        offset = 0
        seen: set[int] = set()
        while True:
            response = self._api("market.get", {**params, "offset": offset})
            batch = response.get("items", [])
            for item in [*batch, *response.get("variants", [])]:
                if item["id"] not in seen:
                    seen.add(item["id"])
                    yield item
            offset += len(batch)
            total = response.get("count", 0)
            if not batch or offset >= total:
                break

        if offset < total:
            raise VKAPIError(f"market.get: получено {offset} товаров из {total}")
        logger.info(f"Total VK market items: {len(seen)} (group {self.group_id})")

    def get_all_market_items(self) -> list[dict]:
        """Загружает все товары из группы ВК постранично."""
        return list(self.iter_market_items())

    def add_item(self, *, name: str, description: str, category_id: int, price: str,
                 main_photo_id: int, sku: str) -> int:
        """Создаёт товар (market.add). Возвращает его ID в ВК."""
        response = self._api("market.add", {
            "owner_id": self.owner_id,
            "name": name,
            "description": description,
            "category_id": category_id,
            "price": price,
            "main_photo_id": main_photo_id,
            "sku": sku,
        }, repeatable=False)
        return response["market_item_id"]

    def edit_item(self, vk_item_id: int, fields: dict) -> None:
        """Меняет только переданные поля товара (market.edit)."""
        self._api("market.edit", {"owner_id": self.owner_id, "item_id": vk_item_id, **fields})

    def delete_item(self, vk_item_id: int) -> None:
        """Удаляет товар (market.delete). Уже удалённый — не ошибка."""
        try:
            self._api("market.delete", {"owner_id": self.owner_id, "item_id": vk_item_id})
        except VKAPIError as e:
            if e.code != ITEM_NOT_FOUND_CODE:
                raise

    def upload_main_photo(self, image_url: str) -> int:
        """
        Загружает обложку для market.add, возвращает её photo_id.

        market.getProductPhotoUploadServer → POST файла → market.saveProductPhoto.
        Эти методы есть в схеме API ВК, а photos.getMarketUploadServer из upload_photo —
        нет, хотя руководство по загрузке его ещё описывает (docs/VK_YML_FEED.md).
        """
        content, filename = self._prepare_photo(image_url)
        server = self._api("market.getProductPhotoUploadServer", {"group_id": self.group_id})
        time.sleep(self.REQUEST_DELAY)
        try:
            upload_resp = requests.post(
                server["upload_url"],
                files={"file": (filename, io.BytesIO(content))},
                timeout=60,
            )
            upload_resp.raise_for_status()
        except requests.RequestException as e:
            raise VKAPIError(f"загрузка фото: {type(e).__name__}") from None
        saved = self._api("market.saveProductPhoto", {"upload_response": upload_resp.text})
        return saved["photo_id"]

    def _prepare_photo(self, image_url: str) -> tuple[bytes, str]:
        """Скачивает фото и приводит к тому, что принимает ВК: JPG, PNG или GIF от 400×400."""
        try:
            content, _ = self._download_image(image_url)
            with Image.open(io.BytesIO(content)) as image:
                if min(image.size) < PHOTO_MIN_SIDE:
                    raise VKPhotoError(f"фото {image.width}×{image.height} меньше {PHOTO_MIN_SIDE}×{PHOTO_MIN_SIDE}")
                if image.format in PHOTO_FORMATS:
                    return content, f"photo.{PHOTO_FORMATS[image.format]}"
                converted = io.BytesIO()
                image.convert("RGB").save(converted, "JPEG", quality=90)
                return converted.getvalue(), "photo.jpg"
        except (requests.RequestException, OSError) as e:
            # Pillow бросает UnidentifiedImageError (OSError), если это не картинка.
            raise VKPhotoError(f"фото не скачалось: {type(e).__name__}") from None

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

    def upload_video(self, video_url: str, name: str = "Product Video") -> Optional[dict]:
        """
        Загружает видео в видеокаталог группы ВК.

        Flow:
          1. video.save → получаем upload_url
          2. POST видеофайл на upload_url
          3. Видео появляется в группе с id и owner_id

        Returns:
            dict с полями id, owner_id или None при ошибке.
        """
        try:
            # 1. Получаем URL для загрузки
            save_resp = self._api("video.save", {
                "group_id": self.group_id,
                "name": name[:255],
                "wallpost": 0,          # не публиковать на стене
                "is_private": 0,
            })
            upload_url = save_resp["upload_url"]
            video_id = save_resp["video_id"]
            owner_id = save_resp["owner_id"]

            # 2. Скачиваем видео (может быть большим!)
            logger.info(f"Downloading video: {video_url[:80]}")
            video_resp = requests.get(video_url, timeout=120, stream=True)
            video_resp.raise_for_status()

            filename = video_url.split("/")[-1].split("?")[0] or "video.mp4"
            if not any(filename.lower().endswith(ext) for ext in [".mp4", ".avi", ".mov", ".webm"]):
                filename += ".mp4"

            # 3. Загружаем в VK
            logger.info(f"Uploading video to VK: {filename}")
            time.sleep(self.REQUEST_DELAY)
            upload_resp = requests.post(
                upload_url,
                files={"file": (filename, io.BytesIO(video_resp.content), "video/mp4")},
                timeout=300,  # видео может быть большим
            )
            upload_resp.raise_for_status()

            logger.info(f"Video uploaded: owner_id={owner_id}, video_id={video_id}")
            return {"id": video_id, "owner_id": owner_id}

        except Exception as e:
            logger.warning(f"Failed to upload video {video_url!r}: {e}")
            return None

    def set_item_video(self, vk_item_id: int, video_owner_id: int, video_id: int) -> bool:
        """
        Привязывает видео из видеотеки группы к товару в ВК Маркете.
        Использует market.edit с параметром video_id.
        """
        video_id_str = f"{video_owner_id}_{video_id}"
        try:
            self._api("market.edit", {
                "owner_id": self.owner_id,
                "item_id": vk_item_id,
                "video_id": video_id_str,
            })
            logger.info(f"Set video {video_id_str} for item {vk_item_id}")
            return True
        except VKAPIError as e:
            logger.warning(f"Failed to set video for item {vk_item_id}: {e}")
            return False

    def sync_item_photos(
        self,
        vk_item_id: int,
        image_urls: list[str],
        video_url: Optional[str] = None,
    ) -> dict:
        """
        Загружает все картинки (и опционально видео) и устанавливает их на товар.

        Args:
            vk_item_id: ID товара в ВК.
            image_urls: Список URL картинок. Первый — главное фото.
            video_url: URL видео (опционально).

        Returns:
            {'uploaded': N, 'failed': N, 'video': True/False}
        """
        if not image_urls and not video_url:
            return {"uploaded": 0, "failed": 0, "video": False}

        uploaded = 0
        failed = 0
        main_photo: Optional[dict] = None
        video_synced = False

        # --- Фото ---
        for i, url in enumerate(image_urls):
            is_main = (i == 0)
            photo = self.upload_photo(url, is_main=is_main, vk_item_id=vk_item_id)

            if photo:
                uploaded += 1
                if is_main:
                    main_photo = photo
            else:
                failed += 1

        if main_photo:
            self.set_main_photo(
                vk_item_id=vk_item_id,
                photo_owner_id=main_photo["owner_id"],
                photo_id=main_photo["id"],
            )

        # --- Видео ---
        if video_url:
            video = self.upload_video(video_url)
            if video:
                video_synced = self.set_item_video(
                    vk_item_id=vk_item_id,
                    video_owner_id=video["owner_id"],
                    video_id=video["id"],
                )
            else:
                failed += 1

        return {"uploaded": uploaded, "failed": failed, "video": video_synced}
