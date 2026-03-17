import boto3
from django.conf import settings

def get_r2_client():
    """Возвращает настроенный boto3 клиент для работы с R2."""
    config = settings.R2_CONFIG
    return boto3.client(
        's3',
        endpoint_url=config['endpoint_url'],
        aws_access_key_id=config['aws_access_key_id'],
        aws_secret_access_key=config['aws_secret_access_key'],
        region_name=config.get('region_name', 'auto')
    )

def get_r2_path(path: str) -> str:
    """Возвращает путь с учетом префикса окружения (dev/prod)."""
    if not path:
        return ""
    prefix = (getattr(settings, "R2_CONFIG", {}).get("prefix", "") or "").strip("/")
    path = path.lstrip("/")
    if prefix and not path.startswith(prefix + "/"):
        return f"{prefix}/{path}"
    return path

def get_r2_public_url(path: str) -> str:
    """Возвращает полный публичный URL с учетом префикса."""
    if not path:
        return ""
    r2_public = (getattr(settings, "R2_CONFIG", {}).get("public_url", "") or "").rstrip("/")
    if not r2_public:
        return path
    
    r2_path = get_r2_path(path)
    return f"{r2_public}/{r2_path.lstrip('/')}"

def join_r2_path(*parts) -> str:
    """Умное соединение частей пути с учетом префикса."""
    path = "/".join(str(p).strip("/") for p in parts if p)
    return get_r2_path(path)
