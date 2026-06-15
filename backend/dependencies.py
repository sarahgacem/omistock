from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from database import get_db
import models, security, schemas
from typing import Optional

oauth2_scheme = security.oauth2_scheme

def get_current_user(
    token: str = Depends(oauth2_scheme),
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Authentification hybride : accepte JWT Bearer token OU API Key (pour MCP)
    Priorité : JWT > API Key
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expirée ou invalide. Veuillez vous reconnecter.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Essayer d'abord JWT (méthode standard)
    if token:
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
            # Si JWT échoue, essayer API Key
            pass
    
    # Essayer l'authentification par API Key (pour MCP)
    if x_api_key:
        user = db.query(models.User).filter(
            models.User.api_key == x_api_key,
            models.User.is_active == True
        ).first()
        
        if user:
            # Vérifier que le compte n'est pas désactivé
            if hasattr(user, "is_active") and user.is_active == False:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Ce compte est actuellement désactivé."
                )
            return user
    
    # Aucune authentification valide
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

def get_current_agent_by_api_key(api_key: str = None, db: Session = Depends(get_db)):
    """
    Authentification des agents IA via API Key (pour MCP).
    Alternative à JWT pour les agents qui ne peuvent pas gérer les tokens JWT.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key manquante.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    user = db.query(models.User).filter(
        models.User.api_key == api_key,
        models.User.user_type == "AGENT",
        models.User.is_active == True
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key invalide ou agent inactif.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return user

def get_current_admin_or_agent(current_user: models.User = Depends(get_current_user)):
    """
    Permet aux admins ET aux agents IA d'accéder aux routes.
    Utilisé pour les routes MCP qui nécessitent un accès audit logs.
    """
    if current_user.user_type not in ("ADMIN", "AGENT"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs et agents IA."
        )
    return current_user
