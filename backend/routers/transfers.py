from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List

from backend import repository
import models
import schemas
import audit
from dependencies import get_current_user, get_current_human
from database import get_db
from services import log_audit

router = APIRouter()


def _corr(request: Request) -> str:
    return getattr(request.state, "correlation_id", None) or audit.new_correlation_id()


@router.get("/api/transfer/requests", response_model=List[schemas.TransferRequestResponse])
def get_transfer_requests_route(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return repository.get_transfer_requests(db, current_user.company_id)


@router.post("/api/transfer/request")
def request_transfer(
    data: schemas.TransferRequestCreate,
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Un agent peut DEMANDER un transfert (origine AGENT) mais ne pourra pas l'approuver.
    origin = "AGENT" if current_user.user_type == "AGENT" else "HUMAIN"
    corr = _corr(request)
    try:
        req = repository.create_transfer_request(
            db,
            {
                "product_id": data.product_id,
                "to_branch_id": data.to_branch_id,
                "quantity": data.quantity,
                "requester_id": current_user.id,
                "company_id": current_user.company_id,
                "origin": origin,
            },
            from_branch_id=data.from_branch_id,
        )
        log_audit(db, current_user.id, "TRANSFER_REQUESTED", None,
                  {"transfer_id": req.id, "qty": req.quantity, "origin": origin},
                  current_user.company_id, actor_type=current_user.user_type,
                  entity_type="transfer", entity_id=req.id, correlation_id=corr)
        return {"status": "success", "message": "Demande de transfert envoyée", "transfer_id": req.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/transfer/{req_id}/approve")
def approve_transfer(
    req_id: int,
    request: Request,
    current_user: models.User = Depends(get_current_human),  # SoD : humain uniquement
    db: Session = Depends(get_db),
):
    corr = _corr(request)
    try:
        if not repository.get_transfer_request_by_id(db, req_id, current_user.company_id):
            raise HTTPException(status_code=404, detail="Demande introuvable")
        repository.approve_transfer_request(db, req_id, current_user.id)
        log_audit(db, current_user.id, "TRANSFER_APPROVED", {"status": "PENDING"},
                  {"status": "APPROVED"}, current_user.company_id,
                  actor_type=current_user.user_type, entity_type="transfer",
                  entity_id=req_id, correlation_id=corr)
        return {"status": "success", "message": "Transfert approuvé, en attente de confirmation"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/transfer/{req_id}/confirm")
def confirm_transfer(
    req_id: int,
    request: Request,
    current_user: models.User = Depends(get_current_human),  # SoD : humain uniquement
    db: Session = Depends(get_db),
):
    corr = _corr(request)
    try:
        if not repository.get_transfer_request_by_id(db, req_id, current_user.company_id):
            raise HTTPException(status_code=404, detail="Demande introuvable")
        repository.confirm_transfer_request(db, req_id, current_user.id)
        log_audit(db, current_user.id, "TRANSFER_CONFIRMED", {"status": "APPROVED"},
                  {"status": "CONFIRMED"}, current_user.company_id,
                  actor_type=current_user.user_type, entity_type="transfer",
                  entity_id=req_id, correlation_id=corr)
        return {"status": "success", "message": "Transfert confirmé et stock mis à jour"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
