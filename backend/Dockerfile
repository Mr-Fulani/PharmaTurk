FROM python:3.12-slim

ENV POETRY_VERSION=1.8.3 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    POETRY_HTTP_TIMEOUT=120 \
    POETRY_HTTP_RETRY=5

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    gettext \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libgobject-2.0-0 \
    libffi-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    shared-mime-info \
    libcairo2 \
    libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*

# Force IPv4 priority over IPv6 to fix "Network is unreachable" issues with SMTP/APIs
RUN echo "precedence ::ffff:0:0/96 100" >> /etc/gai.conf && \
    echo "label ::ffff:0:0/96 4" >> /etc/gai.conf && \
    echo "precedence ::/0 1" >> /etc/gai.conf && \
    echo "label ::/0 1" >> /etc/gai.conf

# Install Poetry (через pip, чтобы избежать отсутствия бинаря)
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"
ENV PATH="/usr/local/bin:$PATH"

WORKDIR /app

# Манифесты и lock для воспроизводимой установки зависимостей
COPY pyproject.toml poetry.toml poetry.lock ./

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
