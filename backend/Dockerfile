FROM python:3.12-slim

ENV POETRY_VERSION=1.8.3 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - --version ${POETRY_VERSION}
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy dependency manifests first for better caching
COPY pyproject.toml poetry.toml ./

RUN poetry install --no-root --no-interaction --no-ansi

# Copy app source
COPY . .

EXPOSE 8000

CMD ["bash", "-lc", "poetry run python manage.py runserver 0.0.0.0:8000"]

