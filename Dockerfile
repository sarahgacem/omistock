# OMISTOCK — Dockerfile simple et fixe pour Render
FROM python:3.10-slim

WORKDIR /app

# Dépendances système nécessaires à certaines libs Python
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMISTOCK_ROOT=/app

# Chemin FIXE des dépendances
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

# Copier tout le code
COPY . /app

EXPOSE 8000

# Render injecte $PORT (on met 8000 en valeur par défaut si absent pour éviter un crash)
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
