"""
OMISTOCK — Configuration centralisée.

Toutes les valeurs sensibles ou dépendantes de l'environnement sont lues ici
depuis les variables d'environnement (12-factor), avec des valeurs par défaut
sûres pour le développement local UNIQUEMENT.

Variables supportées :
- OMISTOCK_SECRET_KEY      : clé de signature JWT (OBLIGATOIRE en production)
- OMISTOCK_ACCESS_TOKEN_MINUTES : durée de vie du token (défaut 120 min)
- OMISTOCK_CORS_ORIGINS    : liste d'origines autorisées séparées par des virgules
- OMISTOCK_ENV             : "dev" (défaut) ou "prod"
- OMISTOCK_ALLOW_DESTRUCTIVE_RESTORE : "1" pour autoriser le restore brut (défaut 0)
"""
import os
import secrets
import sys

ENV = os.environ.get("OMISTOCK_ENV", "dev").lower()
IS_PROD = ENV in ("prod", "production")

# --- Secret JWT ---------------------------------------------------------------
_secret = os.environ.get("OMISTOCK_SECRET_KEY")
if not _secret:
    if IS_PROD:
        # En production on refuse de démarrer sans secret explicite.
        sys.stderr.write(
            "[CONFIG][FATAL] OMISTOCK_SECRET_KEY est obligatoire en production.\n"
        )
        raise RuntimeError("OMISTOCK_SECRET_KEY manquante en production")
    # Dev : on génère une clé éphémère et on prévient clairement.
    _secret = "DEV_ONLY_" + secrets.token_urlsafe(32)
    sys.stderr.write(
        "[CONFIG][WARN] OMISTOCK_SECRET_KEY non définie : clé de dev éphémère générée. "
        "NE PAS utiliser en production.\n"
    )

SECRET_KEY = _secret
ALGORITHM = "HS256"

# Durée de vie du token : 2h par défaut (au lieu de 24h) pour limiter l'exposition.
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.environ.get("OMISTOCK_ACCESS_TOKEN_MINUTES", str(60 * 2))
)

# --- CORS ---------------------------------------------------------------------
_origins = os.environ.get("OMISTOCK_CORS_ORIGINS", "").strip()
if _origins:
    CORS_ORIGINS = [o.strip() for o in _origins.split(",") if o.strip()]
else:
    # Défaut dev : front local servi par le backend lui-même.
    CORS_ORIGINS = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

# Le restore destructif (.db brut / .sql executescript) est désactivé par défaut.
ALLOW_DESTRUCTIVE_RESTORE = os.environ.get(
    "OMISTOCK_ALLOW_DESTRUCTIVE_RESTORE", "0"
) == "1"
