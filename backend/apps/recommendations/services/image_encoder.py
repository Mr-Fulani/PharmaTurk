"""Image encoder for recommendations (CLIP, 512-dim)."""
import logging
from typing import Optional, Union
import numpy as np
from PIL import Image

from .safe_image_fetcher import ImageFetchError, fetch_search_image, validate_image_bytes

logger = logging.getLogger(__name__)

IMAGE_VECTOR_SIZE = 512


class CLIPEncoder:
    """Encode images to vectors with CLIP."""
    _instance = None
    _model = None
    _processor = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Model loading is intentionally lazy: an invalid public image must be
        # rejected before it can trigger a large model initialization.
        pass

    def _load_model(self):
        try:
            import torch
            from transformers import CLIPProcessor, CLIPModel
        except ImportError as e:
            logger.warning("CLIP dependencies not available: %s", e)
            CLIPEncoder._model = "unavailable"
            return
        logger.info("Loading CLIP model...")
        model_name = "openai/clip-vit-base-patch32"
        CLIPEncoder._model = CLIPModel.from_pretrained(
            model_name,
            trust_remote_code=False,
            use_safetensors=True,
        )
        CLIPEncoder._processor = CLIPProcessor.from_pretrained(
            model_name,
            trust_remote_code=False,
        )
        CLIPEncoder._model.eval()
        if torch.cuda.is_available():
            CLIPEncoder._model = CLIPEncoder._model.cuda()
            logger.info("CLIP loaded on GPU")
        else:
            logger.info("CLIP loaded on CPU")

    @property
    def model(self):
        return CLIPEncoder._model

    @property
    def processor(self):
        return CLIPEncoder._processor

    def _encode_image_impl(self, image: Image.Image) -> Optional[np.ndarray]:
        if CLIPEncoder._model is None:
            self._load_model()
        if self.model == "unavailable" or self.model is None:
            return None
        import torch
        inputs = self.processor(
            images=image,
            return_tensors="pt",
            padding=True,
        )
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}
        with torch.no_grad():
            image_features = self.model.get_image_features(**inputs)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        return image_features.cpu().numpy().flatten().astype(np.float32)

    def encode_image(
        self,
        image_input: Union[str, Image.Image, bytes],
    ) -> Optional[np.ndarray]:
        """Encode image. image_input: PIL Image, file path, or URL."""
        if isinstance(image_input, str):
            if image_input.startswith("http://") or image_input.startswith("https://"):
                return self.encode_image_from_url(image_input)
            try:
                image = Image.open(image_input).convert("RGB")
            except Exception as e:
                logger.warning("Failed to open image path %s: %s", image_input, e)
                return None
        elif isinstance(image_input, bytes):
            try:
                image = validate_image_bytes(image_input).image
            except ImageFetchError as e:
                logger.warning("Failed to open image bytes: %s", e)
                return None
        elif isinstance(image_input, Image.Image):
            image = image_input.convert("RGB")
        else:
            return None
        return self._encode_image_impl(image)

    def encode_image_from_url(self, url: str) -> Optional[np.ndarray]:
        """Load an external image through the SSRF-safe fetcher and encode it."""
        try:
            image = fetch_search_image(url)
            return self._encode_image_impl(image)
        except ImageFetchError as e:
            logger.warning("Image URL rejected before encoding: %s", e.code)
            return None
