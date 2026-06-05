from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
import models, security, schemas
from typing import Optional

oauth2_scheme = security.oauth2_scheme

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expirée ou invalide. Veuillez vous reconnecter.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    try:
        from jose import jwt
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        email: str = payload.get("sub")
        company_id: int = payload.get("company_id")
        if email is None or company_id is None:
            raise credentials_exception
        
        user = db.query(models.User).filter(models.User.email == email).first()
        if user is None:
            raise credentials_exception
            
        # Freeze database access for deactivated accounts (Instagram style)
        if hasattr(user, "is_active") and user.is_active == False:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ce compte est actuellement désactivé."
            )
            
        return user
    except HTTPException:
        raise
    except Exception:
        raise credentials_exception

def get_current_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.user_type != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs."
        )
    return current_user

def get_current_agent_human(current_user: models.User = Depends(get_current_user)):
    if current_user.user_type not in ("ADMIN", "HUMAIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux agents humains."
        )
    return current_user

def get_current_agent_ai(current_user: models.User = Depends(get_current_user)):
    if current_user.user_type != "AGENT":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux agents IA."
        )
    return current_user
