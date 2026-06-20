from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import List
import secrets

from backend import repository
import schemas
import models
import services
import security
import audit
from dependencies import get_current_user, oauth2_scheme, get_current_admin, get_current_human
from database import get_db

router = APIRouter()


@router.get("/api/me")
def get_me(current_user: models.User = Depends(get_current_user)):
    branch_name = current_user.branch.name if current_user.branch else "N/A"
    company_name = current_user.company.name if current_user.company else "Mon Entreprise"
    return {
        "id": current_user.id,
        "email": current_user.email,
        "branch_id": current_user.branch_id,
        "branch_name": branch_name,
        "company_id": current_user.company_id,
        "company_name": company_name,
        "user_type": current_user.user_type,
    }


@router.post("/token", response_model=schemas.Token)
@router.post("/api/token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    try:
        return services.authenticate_user(db, form_data)
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e), headers={"WWW-Authenticate": "Bearer"})


@router.post("/api/signup")
@router.post("/register/enterprise")
@router.post("/api/register/enterprise")
def signup(data: schemas.UserSignUp, db: Session = Depends(get_db)):
    try:
        return services.create_user_service(db, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ----------------------------------------------------------------------------
# Émission d'identité agent IA — ADMIN uniquement, avec gouvernance.
# La clé API n'est renvoyée qu'UNE SEULE FOIS (création) ; elle n'est jamais
# re-listée en clair par la suite (best practice secrets).
# ----------------------------------------------------------------------------
@router.post("/api/agents", response_model=schemas.AgentAccessResponseV2)
def create_agent_route(
    data: schemas.AgentAccessCreateV2,
    request: Request,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    valid_levels = {lvl.value for lvl in models.AutonomyLevel}
    if data.autonomy_level not in valid_levels:
        raise HTTPException(status_code=400, detail=f"Niveau d'autonomie invalide. Valeurs: {sorted(valid_levels)}")

    api_key = secrets.token_urlsafe(32)
    email = f"agent_{secrets.token_hex(4)}@agent.local"
    expires_at = datetime.now(timezone.utc) + timedelta(days=max(1, data.api_key_ttl_days))

    agent = repository.create_agent(
        db,
        {
            "email": email,
            "api_key": api_key,
            "user_type": "AGENT",
            "hashed_password": None,
            "branch_id": data.branch_id if data.branch_id is not None else current_user.branch_id,
            "autonomy_level": data.autonomy_level,
            "agent_scopes": data.agent_scopes,
            "max_action_quantity": data.max_action_quantity,
            "api_key_expires_at": expires_at,
        },
        current_user.company_id,
    )
    corr = getattr(request.state, "correlation_id", None) or audit.new_correlation_id()
    audit.record(db, user_id=current_user.id, actor_type="ADMIN", action="AGENT_KEY_ISSUED",
                 company_id=current_user.company_id, entity_type="agent", entity_id=agent.id,
                 correlation_id=corr,
                 new_value={"autonomy_level": data.autonomy_level, "scopes": data.agent_scopes,
                            "max_qty": data.max_action_quantity, "expires_at": expires_at.isoformat()})
    return {
        "email": email, "api_key": api_key, "user_type": "AGENT",
        "autonomy_level": data.autonomy_level, "agent_scopes": data.agent_scopes,
        "api_key_expires_at": expires_at,
    }


@router.get("/api/agents")
def get_agents_route(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Liste les agents SANS exposer la clé API en clair (on renvoie un indicateur masqué)."""
    agents = repository.get_agents(db, current_user.company_id)
    return [
        {
            "id": a.id, "email": a.email, "user_type": a.user_type,
            "autonomy_level": a.autonomy_level, "agent_scopes": a.agent_scopes,
            "max_action_quantity": a.max_action_quantity,
            "api_key_masked": (a.api_key[:4] + "…" + a.api_key[-3:]) if a.api_key else None,
            "api_key_expires_at": a.api_key_expires_at,
        }
        for a in agents
    ]


@router.post("/api/agents/{agent_id}/rotate-key", response_model=schemas.AgentAccessResponseV2)
def rotate_agent_key(
    agent_id: int,
    request: Request,
    ttl_days: int = 90,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    agent = (
        db.query(models.User)
        .filter(models.User.id == agent_id, models.User.company_id == current_user.company_id,
                models.User.user_type == "AGENT")
        .first()
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent introuvable")
    new_key = secrets.token_urlsafe(32)
    agent.api_key = new_key
    agent.api_key_expires_at = datetime.now(timezone.utc) + timedelta(days=max(1, ttl_days))
    db.commit()
    corr = getattr(request.state, "correlation_id", None) or audit.new_correlation_id()
    audit.record(db, user_id=current_user.id, actor_type="ADMIN", action="AGENT_KEY_ROTATED",
                 company_id=current_user.company_id, entity_type="agent", entity_id=agent.id,
                 correlation_id=corr)
    return {
        "email": agent.email, "api_key": new_key, "user_type": "AGENT",
        "autonomy_level": agent.autonomy_level, "agent_scopes": agent.agent_scopes,
        "api_key_expires_at": agent.api_key_expires_at,
    }


@router.get("/api/auth/qr-code")
def generate_qr_code(
    token: str = Depends(oauth2_scheme),
    current_user: models.User = Depends(get_current_human),
):
    import qrcode, io, base64
    if not token:
        raise HTTPException(status_code=401, detail="Token requis")
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(token)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return JSONResponse({"qr_code": f"data:image/png;base64,{img_b64}"})
