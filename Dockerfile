# OMISTOCK — Dockerfile Render (Poetry auto-detect + fallback requirements)
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

# Copier tout le code (backend, frontend et base SQLite si présente)
COPY . /app

# Installer les dépendances :
# 1) Poetry root (/app)
# 2) Poetry backend (/app/backend)
# 3) Fallback requirements backend
RUN if [ -f "/app/pyproject.toml" ]; then \
      poetry install --no-root; \
    elif [ -f "/app/backend/pyproject.toml" ]; then \
      cd /app/backend && poetry install --no-root; \
    elif [ -f "/app/backend/requirements.txt" ]; then \
      pip install --no-cache-dir --upgrade pip && \
      pip install --no-cache-dir -r /app/backend/requirements.txt; \
    else \
      echo "ERREUR: Aucun fichier de dépendances trouvé (pyproject.toml / requirements.txt)." && exit 1; \
    fi

EXPOSE 8000

# Render injecte $PORT dynamiquement
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
