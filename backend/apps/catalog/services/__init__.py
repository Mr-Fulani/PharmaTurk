from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_services_path = Path(__file__).resolve().parent.parent / "services.py"
_spec = spec_from_file_location("apps.catalog._services_file", _services_path)
_module = module_from_spec(_spec)
_spec.loader.exec_module(_module)

CatalogNormalizer = _module.CatalogNormalizer
CatalogService = _module.CatalogService
from .medicine_media_enricher import MedicineMediaEnricher
from .ikea_service import IkeaService

__all__ = [
    "CatalogNormalizer",
    "CatalogService",
    "MedicineMediaEnricher",
    "IkeaService",
]
