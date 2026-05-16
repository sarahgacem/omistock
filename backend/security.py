from datetime import datetime, timedelta
from typing import Optional
from jose import jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer

# Outil pour récupérer le token dans les requêtes
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Configuration de base (À mettre dans un fichier .env plus tard pour plus de sécurité)
SECRET_KEY = "SUPER_SECRET_POUR_OMISTOCK_2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # Le badge reste valide 24 heures

# Outil pour crypter les mots de passe
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    """Vérifie si le mot de passe saisi correspond au mot de passe crypté."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """Transforme un mot de passe en texte clair en une version cryptée illisible."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Crée le badge JWT. 
    On y insère l'email et le company_id pour savoir qui est l'utilisateur.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
