from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List
import secrets

from backend import repository
import schemas
import models
import services
import security
from dependencies import get_current_user, oauth2_scheme, get_current_agent_human
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
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/api/signup")
@router.post("/register/enterprise")
@router.post("/api/register/enterprise")
def signup(data: schemas.UserSignUp, db: Session = Depends(get_db)):
    try:
        return services.create_user_service(db, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/agents", response_model=schemas.AgentAccessResponse)
def create_agent_route(
    data: schemas.AgentAccessCreate,
    current_user: models.User = Depends(get_current_agent_human),
    db: Session = Depends(get_db),
):
    api_key = secrets.token_urlsafe(32)
    email = f"agent_{secrets.token_hex(4)}@agent.local"

    repository.create_agent(
        db,
        {
            "email": email,
            "api_key": api_key,
            "user_type": "AGENT",
            "hashed_password": None,
            "branch_id": current_user.branch_id,
        },
        current_user.company_id,
    )

    return {"email": email, "api_key": api_key, "user_type": "AGENT"}


@router.get("/api/agents", response_model=List[schemas.AgentAccessResponse])
def get_agents_route(
    current_user: models.User = Depends(get_current_agent_human),
    db: Session = Depends(get_db),
):
    agents = repository.get_agents(db, current_user.company_id)
    return [
        {"email": a.email, "api_key": a.api_key, "user_type": a.user_type}
        for a in agents
    ]


@router.get("/api/auth/qr-code")
def generate_qr_code(
    token: str = Depends(oauth2_scheme),
    current_user: models.User = Depends(get_current_agent_human),
):
    import qrcode
    import io
    import base64

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(token)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return JSONResponse({"qr_code": f"data:image/png;base64,{img_b64}"})
