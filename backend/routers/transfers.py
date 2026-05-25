from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from backend import repository
import models
import schemas
from dependencies import get_current_user
from database import get_db
from services import log_audit

router = APIRouter()


@router.get("/api/transfer/requests", response_model=List[schemas.TransferRequestResponse])
def get_transfer_requests_route(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return repository.get_transfer_requests(db, current_user.company_id)


@router.post("/api/transfer/request")
def request_transfer(
    data: schemas.TransferRequestCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        req = repository.create_transfer_request(
            db,
            {
                "product_id": data.product_id,
                "to_branch_id": data.to_branch_id,
                "quantity": data.quantity,
                "requester_id": current_user.id,
                "company_id": current_user.company_id,
            },
            from_branch_id=data.from_branch_id,
        )
        log_audit(
            db,
            current_user.id,
            f"TRANSFER_REQUESTED_{req.id}",
            "N/A",
            f"Qty:{req.quantity}",
            current_user.company_id,
        )
        return {"status": "success", "message": "Demande de transfert envoyée"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/transfer/{req_id}/approve")
def approve_transfer(
    req_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        if not repository.get_transfer_request_by_id(db, req_id, current_user.company_id):
            raise HTTPException(status_code=404, detail="Demande introuvable")

        repository.approve_transfer_request(db, req_id, current_user.id)
        log_audit(
            db,
            current_user.id,
            f"TRANSFER_APPROVED_{req_id}",
            "N/A",
            "En transit",
            current_user.company_id,
        )
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
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        if not repository.get_transfer_request_by_id(db, req_id, current_user.company_id):
            raise HTTPException(status_code=404, detail="Demande introuvable")

        repository.confirm_transfer_request(db, req_id, current_user.id)
        log_audit(
            db,
            current_user.id,
            f"TRANSFER_CONFIRMED_{req_id}",
            "En transit",
            "Stock destination mis à jour",
            current_user.company_id,
        )
        return {"status": "success", "message": "Transfert confirmé et stock mis à jour"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
