"""Recommendation services.

Heavy ML dependencies are imported lazily so request validation and health
checks do not require loading sentence-transformers/torch.
"""
from importlib import import_module

__all__ = [
    "QdrantRecommendationEngine",
    "TextEncoder",
    "CLIPEncoder",
    "BusinessReranker",
]


_EXPORTS = {
    "QdrantRecommendationEngine": (".vector_engine", "QdrantRecommendationEngine"),
    "TextEncoder": (".text_encoder", "TextEncoder"),
    "CLIPEncoder": (".image_encoder", "CLIPEncoder"),
    "BusinessReranker": (".reranker", "BusinessReranker"),
}


def __getattr__(name):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError:
        raise AttributeError(name) from None
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
