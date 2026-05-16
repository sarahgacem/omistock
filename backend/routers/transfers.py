from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import models, schemas
from dependencies import get_current_user
from database import get_db

router = APIRouter()

@router.get("/api/transfer/requests", response_model=List[schemas.TransferRequestResponse])
def get_transfer_requests(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.TransferRequest).filter(models.TransferRequest.company_id == current_user.company_id).order_by(models.TransferRequest.created_at.desc()).all()

@router.post("/api/transfer/request")
def request_transfer(data: schemas.TransferRequestCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = models.TransferRequest(
        product_id=data.product_id,
        from_branch_id=data.from_branch_id,
        to_branch_id=data.to_branch_id,
        quantity=data.quantity,
        requester_id=current_user.id,
        company_id=current_user.company_id
    )
    db.add(req)
    from services import log_audit
    log_audit(db, current_user.id, f"TRANSFER_REQUESTED_{req.id}", "N/A", f"Qty:{req.quantity}", current_user.company_id)
    return {"status": "success", "message": "Demande de transfert envoyée"}

@router.post("/api/transfer/{req_id}/approve")
def approve_transfer(req_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = db.query(models.TransferRequest).filter(models.TransferRequest.id == req_id, models.TransferRequest.company_id == current_user.company_id).first()
    if not req: raise HTTPException(status_code=404)
    if req.status != models.TransferStatus.PENDING: raise HTTPException(status_code=400, detail="Statut invalide")
    
    from_inv = db.query(models.Inventory).filter(models.Inventory.product_id == req.product_id, models.Inventory.branch_id == req.from_branch_id).first()
    if not from_inv or from_inv.quantity < req.quantity:
        raise HTTPException(status_code=400, detail="Stock insuffisant dans le dépôt source")
        
    old_from = from_inv.quantity
    from_inv.quantity -= req.quantity
    req.status = models.TransferStatus.APPROVED
    req.approver_id = current_user.id
    
    movement = models.StockMovement(
        product_id=req.product_id, 
        branch_id=req.from_branch_id, 
        quantity=-req.quantity, 
        reason="Transfert approuvé (sortie)", 
        company_id=current_user.company_id, 
        movement_type="OUT"
    )
    db.add(movement)
    from services import log_audit
    log_audit(db, current_user.id, f"TRANSFER_APPROVED_{req_id}", f"Source:{old_from}->{from_inv.quantity}", "En transit", current_user.company_id)
    return {"status": "success", "message": "Transfert approuvé, en attente de confirmation"}

@router.post("/api/transfer/{req_id}/confirm")
def confirm_transfer(req_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = db.query(models.TransferRequest).filter(models.TransferRequest.id == req_id, models.TransferRequest.company_id == current_user.company_id).first()
    if not req: raise HTTPException(status_code=404)
    if req.status != models.TransferStatus.APPROVED: raise HTTPException(status_code=400, detail="Statut invalide")
    
    to_inv = db.query(models.Inventory).filter(models.Inventory.product_id == req.product_id, models.Inventory.branch_id == req.to_branch_id).first()
    old_to = to_inv.quantity if to_inv else 0
    if to_inv:
        to_inv.quantity += req.quantity
    else:
        to_inv = models.Inventory(product_id=req.product_id, branch_id=req.to_branch_id, quantity=req.quantity, min_threshold=5)
        db.add(to_inv)
    
    req.status = models.TransferStatus.CONFIRMED
    movement = models.StockMovement(
        product_id=req.product_id, 
        branch_id=req.to_branch_id, 
        quantity=req.quantity, 
        reason="Transfert confirmé (entrée)", 
        company_id=current_user.company_id, 
        movement_type="IN"
    )
    db.add(movement)
    from services import log_audit
    log_audit(db, current_user.id, f"TRANSFER_CONFIRMED_{req_id}", "En transit", f"Dest:{old_to}->{to_inv.quantity}", current_user.company_id)
    return {"status": "success", "message": "Transfert confirmé et stock mis à jour"}
