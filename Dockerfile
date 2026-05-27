# OMISTOCK — Dockerfile Render (Poetry + SQLite)
FROM python:3.10-slim

WORKDIR /app

# Dépendances système utiles à cryptography/bcrypt/Pillow
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Installer Poetry
ENV POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMISTOCK_ROOT=/app \
    PORT=8000
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Copier d'abord les fichiers de dépendances Poetry (cache Docker)
COPY pyproject.toml poetry.lock* /app/

# Installer les dépendances du projet
RUN poetry install --no-root

# Copier tout le code (backend, frontend et base SQLite si présente)
COPY . /app

# On lance depuis /app/backend pour respecter "uvicorn main:app ..."
WORKDIR /app/backend

EXPOSE 8000

# Render injecte $PORT dynamiquement
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
