from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer

import config

# Outil pour récupérer le token dans les requêtes
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Configuration sensible : lue depuis l'environnement via config.py (plus de secret en dur)
SECRET_KEY = config.SECRET_KEY
ALGORITHM = config.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = config.ACCESS_TOKEN_EXPIRE_MINUTES

# Outil pour crypter les mots de passe
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    """Vérifie si le mot de passe saisi correspond au mot de passe crypté."""
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    """Transforme un mot de passe en texte clair en une version cryptée illisible."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Crée le badge JWT.
    On y insère l'email, le company_id et le rôle pour savoir qui est l'utilisateur.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
