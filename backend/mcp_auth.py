"""
Fichier d'authentification spécifique pour les agents MCP
Permet l'authentification via API Key pour les agents IA
"""
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from database import get_db
import models

def get_mcp_agent(
    x_api_key: str = Header(None, description="API Key pour authentification MCP"),
    authorization: str = Header(None, description="JWT Bearer token (alternative)"),
    db: Session = Depends(get_db)
):
    """
    Authentification hybride pour MCP : accepte soit API Key soit JWT
    Priorité : API Key > JWT
    """
    # Essayer d'abord l'authentification par API Key
    if x_api_key:
        user = db.query(models.User).filter(
            models.User.api_key == x_api_key,
            models.User.user_type == "AGENT",
            models.User.is_active == True
        ).first()
        
        if user:
            return user
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key invalide ou agent inactif.",
            )
    
    # Si pas d'API Key, essayer JWT
    if authorization and authorization.startswith("Bearer "):
        try:
            from jose import jwt
            import security
            token = authorization.replace("Bearer ", "")
            payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
            email: str = payload.get("sub")
            
            user = db.query(models.User).filter(models.User.email == email).first()
            if user and user.user_type == "AGENT" and user.is_active:
                return user
        except:
            pass  # Continue vers l'erreur
    
    # Aucune authentification valide
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise. Utilisez X-API-Key ou Authorization Bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )