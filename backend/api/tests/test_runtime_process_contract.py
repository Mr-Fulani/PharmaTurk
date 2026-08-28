from pathlib import Path

from django.conf import settings


def test_gunicorn_defaults_fit_backend_memory_limit_and_recycle_workers():
    entrypoint = (Path(settings.BASE_DIR) / "docker-entrypoint.sh").read_text()

    assert 'WORKERS="${GUNICORN_WORKERS:-2}"' in entrypoint
    assert 'THREADS="${GUNICORN_THREADS:-8}"' in entrypoint
    assert 'MAX_REQUESTS="${GUNICORN_MAX_REQUESTS:-200}"' in entrypoint
    assert 'MAX_REQUESTS_JITTER="${GUNICORN_MAX_REQUESTS_JITTER:-40}"' in entrypoint
    assert "--max-requests $MAX_REQUESTS" in entrypoint
    assert "--max-requests-jitter $MAX_REQUESTS_JITTER" in entrypoint
