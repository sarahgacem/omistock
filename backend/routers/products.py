from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional
import models, schemas, services
from dependencies import get_current_user
from database import get_db

router = APIRouter()

@router.get("/products", response_model=List[schemas.ProductResponse])
@router.get("/api/inventory", response_model=List[schemas.ProductResponse])
def get_products(
    branch_id: Optional[int] = None, 
    sort: Optional[str] = None,
    current_user: Optional[models.User] = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    try:
        cid = current_user.company_id if current_user else 1
        query = db.query(models.Product).filter(models.Product.company_id == cid)
        if branch_id:
            query = query.join(models.Inventory).filter(models.Inventory.branch_id == branch_id)
        if sort == "date":
            query = query.order_by(models.Product.created_at.desc())
        return query.all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/products", response_model=schemas.ProductResponse)
def create_product(product: schemas.ProductCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_product = models.Product(**product.dict(), company_id=current_user.company_id)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@router.get("/api/products/{product_id}", response_model=schemas.ProductResponse)
def get_product(product_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id, models.Product.company_id == current_user.company_id).first()
    if not db_product: raise HTTPException(status_code=404)
    return db_product

@router.put("/api/products/{product_id}")
def update_product(product_id: int, product: schemas.ProductUpdate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id, models.Product.company_id == current_user.company_id).first()
    if not db_product: raise HTTPException(status_code=404)
    update_data = product.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_product, key, value)
    db.commit()
    return {"status": "updated"}

@router.delete("/api/products/{product_id}")
def delete_product(product_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id, models.Product.company_id == current_user.company_id).first()
    if not db_product: raise HTTPException(status_code=404)
    db.delete(db_product)
    db.commit()
    return {"status": "deleted"}

@router.get("/api/alerts", response_model=List[schemas.ProductResponse])
def get_alerts(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.Product).filter(
        models.Product.company_id == cid,
        models.Product.quantity <= models.Product.min_threshold
    ).all()

@router.get("/api/dashboard/stats")
def get_dashboard_stats(branch_id: Optional[int] = None, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services.get_dashboard_stats_data(db, current_user.company_id, branch_id)

@router.post("/api/mcp/analyze")
def analyze_product_mcp_post(data: schemas.ProductAnalyzeRequest, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    advice = services.analyze_product_mcp(db, data.product_id, current_user.company_id, current_user.id)
    agent = db.query(models.User).filter(models.User.company_id == current_user.company_id, models.User.user_type == "AGENT").first()
    if not agent:
        import secrets
        agent = models.User(email=f"mcp_agent_{secrets.token_hex(4)}@agent.local", user_type="AGENT", company_id=current_user.company_id)
        db.add(agent)
        db.commit()
        db.refresh(agent)
    
    from services import log_audit
    log_audit(db, agent.id, f"ANALYSE_PREDICTIVE_{data.product_id}", "N/A", advice, current_user.company_id)
    return {"analysis": advice}

@router.get("/api/branches", response_model=List[schemas.BranchResponse])
def get_branches(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.Branch).filter(models.Branch.company_id == cid).all()

@router.get("/api/suppliers", response_model=List[schemas.SupplierResponse])
def get_suppliers(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.Supplier).filter(models.Supplier.company_id == cid).all()

@router.get("/api/sales", response_model=List[schemas.SaleResponse])
def get_sales(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.Sale).filter(models.Sale.company_id == cid).all()

@router.get("/api/movements", response_model=List[schemas.StockMovementResponse])
def get_movements(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.StockMovement).filter(models.StockMovement.company_id == cid).order_by(models.StockMovement.created_at.desc()).all()
