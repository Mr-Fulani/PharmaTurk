"""Text encoder for recommendations (sentence-transformers, 384-dim)."""
import logging
from sentence_transformers import SentenceTransformer
import numpy as np

logger = logging.getLogger(__name__)

TEXT_VECTOR_SIZE = 384


class TextEncoder:
    """Encode text to vectors. Multilingual model (Russian, Turkish)."""
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if TextEncoder._model is None:
            self._load_model()

    def _load_model(self):
        logger.info("Loading text encoder model...")
        model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        TextEncoder._model = SentenceTransformer(model_name)
        logger.info("Text encoder loaded: %s", model_name)

    @property
    def model(self):
        return TextEncoder._model

    def encode(self, text: str) -> np.ndarray:
        """Encode text to 384-dim vector."""
        if not text or not str(text).strip():
            return np.zeros(TEXT_VECTOR_SIZE, dtype=np.float32)
        text = str(text)[:2000]
        embedding = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return np.asarray(embedding, dtype=np.float32)

    def encode_batch(self, texts: list) -> np.ndarray:
        """Encode a batch of texts."""
        texts = [ (t[:2000] if t else "") for t in texts ]
        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return np.asarray(embeddings, dtype=np.float32)
