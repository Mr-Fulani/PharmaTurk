FROM python:3.12-slim

ENV POETRY_VERSION=1.8.3 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    gettext \
  && rm -rf /var/lib/apt/lists/*

# Install Poetry (через pip, чтобы избежать отсутствия бинаря)
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"
ENV PATH="/usr/local/bin:$PATH"

WORKDIR /app

# Copy dependency manifests first for better caching
COPY pyproject.toml poetry.toml ./

RUN poetry install --no-root --no-interaction --no-ansi

# Copy app source
COPY . .

# Copy and make entrypoint script executable
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Compile translations and collect static at build-time
RUN poetry run django-admin compilemessages || true \
 && poetry run python manage.py collectstatic --noinput || true

EXPOSE 8000

CMD ["bash", "/app/docker-entrypoint.sh"]

