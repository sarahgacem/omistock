from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import secrets

from backend import repository
import models
import schemas
import services
from dependencies import get_current_user
from database import get_db
from services import log_audit

router = APIRouter()


@router.get("/products", response_model=List[schemas.ProductResponse])
@router.get("/api/inventory", response_model=List[schemas.ProductResponse])
def get_products_route(
    branch_id: Optional[int] = None,
    sort: Optional[str] = None,
    current_user: Optional[models.User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        cid = current_user.company_id if current_user else 1
        products = repository.get_products(db, cid, branch_id=branch_id)
        if sort == "date":
            products = sorted(
                products,
                key=lambda p: p.created_at or "",
                reverse=True,
            )
        return products
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/products", response_model=schemas.ProductResponse)
def create_product_route(
    product: schemas.ProductCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return repository.create_product(db, product, current_user.company_id)


@router.get("/api/products/{product_id}", response_model=schemas.ProductResponse)
def get_product_route(
    product_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_product = repository.get_product_by_id_for_company(
        db, product_id, current_user.company_id
    )
    if not db_product:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    return db_product


@router.put("/api/products/{product_id}")
def update_product_route(
    product_id: int,
    product: schemas.ProductUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_product = repository.get_product_by_id_for_company(
        db, product_id, current_user.company_id
    )
    if not db_product:
        raise HTTPException(status_code=404, detail="Produit introuvable")

    update_data = product.dict(exclude_unset=True)
    if current_user.branch_id and "quantity" in update_data:
        update_data["branch_id"] = current_user.branch_id

    try:
        repository.update_product(db, product_id, update_data)
        return {"status": "updated"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/api/products/{product_id}")
def delete_product_route(
    product_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_product = repository.get_product_by_id_for_company(
        db, product_id, current_user.company_id
    )
    if not db_product:
        raise HTTPException(status_code=404, detail="Produit introuvable")

    try:
        repository.delete_product(db, product_id)
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/alerts", response_model=List[schemas.ProductResponse])
def get_alerts_route(
    current_user: Optional[models.User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id if current_user else 1
    return repository.get_alerts(db, cid)


@router.get("/api/dashboard/stats")
def get_dashboard_stats(
    branch_id: Optional[int] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return services.get_dashboard_stats_data(db, current_user.company_id, branch_id)


@router.post("/api/mcp/analyze")
def analyze_product_mcp_post(
    data: schemas.ProductAnalyzeRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    advice = services.analyze_product_mcp(
        db, data.product_id, current_user.company_id, current_user.id
    )

    agents = repository.get_agents(db, current_user.company_id)
    agent = agents[0] if agents else None
    if not agent:
        agent = repository.create_agent(
            db,
            {
                "email": f"mcp_agent_{secrets.token_hex(4)}@agent.local",
                "api_key": secrets.token_urlsafe(32),
                "user_type": "AGENT",
                "hashed_password": None,
                "branch_id": current_user.branch_id,
            },
            current_user.company_id,
        )

    log_audit(
        db,
        agent.id,
        f"ANALYSE_PREDICTIVE_{data.product_id}",
        "N/A",
        advice,
        current_user.company_id,
    )
    return {"analysis": advice}


@router.get("/api/branches", response_model=List[schemas.BranchResponse])
def get_branches_route(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id if current_user else 1
    return repository.get_branches(db, cid)


@router.get("/api/suppliers", response_model=List[schemas.SupplierResponse])
def get_suppliers_route(
    current_user: Optional[models.User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id if current_user else 1
    return repository.get_suppliers(db, cid)


@router.get("/api/sales", response_model=List[schemas.SaleResponse])
def get_sales_route(
    current_user: Optional[models.User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id if current_user else 1
    return repository.get_sales(db, cid)


@router.post("/api/sales", response_model=schemas.SaleResponse)
def create_sale_route(
    sale: schemas.SaleCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        db_sale = repository.create_sale(
            db, sale, current_user.company_id, current_user.id
        )
        log_audit(
            db,
            current_user.id,
            f"VENTE_WEB_CREEE_{db_sale.id}",
            "N/A",
            f"Montant: {db_sale.total_amount}",
            current_user.company_id,
        )
        return db_sale
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/movements", response_model=List[schemas.StockMovementResponse])
def get_movements_route(
    current_user: Optional[models.User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id if current_user else 1
    return repository.get_movements(db, cid)
