from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from database import get_db
import models
import security
from typing import Optional
from jose import jwt, JWTError

oauth2_scheme = security.oauth2_scheme


def _check_active(user: models.User):
    if user is not None and getattr(user, "is_active", True) is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ce compte est actuellement désactivé.",
        )


def _user_from_jwt(token: str, db: Session) -> Optional[models.User]:
    """Décode le JWT et renvoie l'utilisateur. Lève seulement si le token existe mais est invalide."""
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
    except JWTError:
        # Token présent mais invalide / expiré : on échoue explicitement (plus de "except: pass").
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée ou invalide. Veuillez vous reconnecter.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    email = payload.get("sub")
    company_id = payload.get("company_id")
    if not email or company_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token incomplet.")
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable.")
    _check_active(user)
    return user


def _user_from_api_key(x_api_key: str, db: Session) -> Optional[models.User]:
    user = (
        db.query(models.User)
        .filter(models.User.api_key == x_api_key, models.User.is_active == True)  # noqa: E712
        .first()
    )
    if not user:
        return None
    # Expiration de la clé API agent (rotation/expiry obligatoire côté sécurité).
    exp = getattr(user, "api_key_expires_at", None)
    if exp is not None:
        exp_aware = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp_aware:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Clé API expirée. Veuillez la faire renouveler par un administrateur.",
            )
    _check_active(user)
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> models.User:
    """
    Authentification hybride : JWT Bearer (humains) OU X-API-Key (agents).
    L'absence totale d'identifiant => 401 (plus de fallback silencieux sur company_id=1).
    """
    if token:
        return _user_from_jwt(token, db)
    if x_api_key:
        user = _user_from_api_key(x_api_key, db)
        if user:
            return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.user_type != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès réservé aux administrateurs.")
    return current_user


def get_current_human(current_user: models.User = Depends(get_current_user)):
    """Humains uniquement (ADMIN ou HUMAIN). Les agents IA sont refusés."""
    if current_user.user_type not in ("ADMIN", "HUMAIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès réservé aux utilisateurs humains.")
    return current_user


# Alias rétrocompatible (ancien nom).
get_current_agent_human = get_current_human


def get_current_agent(current_user: models.User = Depends(get_current_user)):
    """Agents IA uniquement."""
    if current_user.user_type != "AGENT":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès réservé aux agents IA.")
    return current_user


def get_current_admin_or_agent(current_user: models.User = Depends(get_current_user)):
    if current_user.user_type not in ("ADMIN", "AGENT"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs et agents IA.",
        )
    return current_user


def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    """
    Renvoie l'utilisateur si une authentification valide est fournie, sinon None.
    IMPORTANT : ne renvoie JAMAIS un fallback company_id=1 (correction de la faille
    de bypass multi-tenant). Les routes qui utilisent cette dépendance DOIVENT
    refuser explicitement le cas None si elles touchent des données d'entreprise.
    """
    if token:
        return _user_from_jwt(token, db)
    if x_api_key:
        return _user_from_api_key(x_api_key, db)
    return None
