# syntax=docker/dockerfile:1

FROM python:3.12.13-slim-bookworm AS application

ARG DEPENDENCY_LOCK_HASH=unknown
ARG VCS_REF=unknown
LABEL com.mudaroba.poetry-lock-hash=$DEPENDENCY_LOCK_HASH
LABEL org.opencontainers.image.revision=$VCS_REF

ENV POETRY_VERSION=2.4.1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_INSTALLER_PARALLEL=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    POETRY_HTTP_TIMEOUT=120 \
    POETRY_HTTP_RETRY=5 \
    HF_HOME=/home/app/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    gettext \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
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

RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app && \
    mkdir -p /app /home/app/.cache/huggingface && \
    chown -R app:app /app /home/app/.cache

WORKDIR /app

# Манифесты и lock для воспроизводимой установки зависимостей
COPY --chown=app:app pyproject.toml poetry.toml poetry.lock ./

USER app

RUN --mount=type=cache,target=/home/app/.cache/pypoetry,uid=10001,gid=10001,sharing=locked \
    poetry install --only main --no-root --no-interaction --no-ansi

# Copy app source
COPY --chown=app:app . .

# Make entrypoint script executable
RUN chmod +x /app/docker-entrypoint.sh

# Compile translations and collect static at build-time
RUN export DJANGO_DEBUG=0 \
    DJANGO_SECRET_KEY=build-only-key-7f2bc6c348c545cd9cc8fa02fbac1102 \
    DJANGO_ALLOWED_HOSTS=localhost \
    DATABASE_URL=postgresql://build:build-only-db-password@localhost:5432/build \
    REDIS_URL=redis://localhost:6379/0 \
    REDIS_CACHE_URL=redis://localhost:6379/1 \
    CELERY_RESULT_BACKEND_URL=redis://localhost:6379/2 \
 && poetry run python manage.py compilemessages \
 && poetry run python manage.py collectstatic --noinput

# Backend, Celery workers and Beat inherit this non-root runtime user.
USER app

EXPOSE 8000

CMD ["bash", "/app/docker-entrypoint.sh"]

# CI/predeploy-only stage. Production remains the final stage and contains only
# runtime dependencies; the test stage adds pytest/linters from Poetry's dev group.
FROM application AS test
RUN --mount=type=cache,target=/home/app/.cache/pypoetry,uid=10001,gid=10001,sharing=locked \
    poetry install --with dev --no-root --no-interaction --no-ansi

FROM application AS production
