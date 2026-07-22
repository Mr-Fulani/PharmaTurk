import os
import sys

import django


sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.catalog.models import Service
from apps.catalog.serializers import ServiceSerializer


service = Service.objects.get(slug="myte-okon")
data = ServiceSerializer(service).data
print(
    {
        "id": data["id"],
        "name": data["name"],
        "slug": data["slug"],
        "active": data["is_active"],
        "category": data["category"]["slug"] if data["category"] else None,
        "price": data["price"],
        "main_image_url": data["main_image_url"],
        "og_image_url": data["og_image_url"],
        "attributes": len(data["service_attributes"]),
        "portfolio_items": len(data["portfolio_items"]),
    }
)
