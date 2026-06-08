from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
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


@router.get("/api/sales/{sale_id}/invoice/html")
def get_invoice_html(
    sale_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sale = db.query(models.Sale).filter(
        models.Sale.id == sale_id,
        models.Sale.company_id == current_user.company_id
    ).first()
    
    if not sale:
        raise HTTPException(status_code=404, detail="Vente introuvable")
    
    company = db.query(models.Company).filter(models.Company.id == current_user.company_id).first()
    branch = db.query(models.Branch).filter(models.Branch.id == sale.branch_id).first()
    user = current_user  # Use current_user instead of sale.user_id
    
    items = db.query(models.SaleItem).filter(models.SaleItem.sale_id == sale_id).all()
    
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Facture #{sale.id}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
            .header {{ border-bottom: 2px solid #333; padding-bottom: 20px; margin-bottom: 30px; }}
            .company-name {{ font-size: 24px; font-weight: bold; color: #174092; }}
            .invoice-title {{ font-size: 28px; font-weight: bold; text-align: right; color: #333; }}
            .info-row {{ display: flex; justify-content: space-between; margin: 10px 0; }}
            .info-label {{ font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 30px; }}
            th {{ background: #174092; color: white; padding: 12px; text-align: left; }}
            td {{ border: 1px solid #ddd; padding: 12px; }}
            .total {{ font-size: 20px; font-weight: bold; text-align: right; margin-top: 30px; }}
            .footer {{ margin-top: 50px; text-align: center; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="company-name">{company.name if company else 'OMISTOCK'}</div>
            <div class="invoice-title">FACTURE #{sale.id}</div>
        </div>
        
        <div class="info-row">
            <div>
                <div class="info-label">Date:</div>
                <div>{sale.date.strftime('%d/%m/%Y %H:%M') if sale.date else 'N/A'}</div>
            </div>
            <div>
                <div class="info-label">Filiale:</div>
                <div>{branch.name if branch else 'N/A'}</div>
            </div>
        </div>
        
        <div class="info-row">
            <div>
                <div class="info-label">Vendeur:</div>
                <div>{user.email if user else 'N/A'}</div>
            </div>
            <div>
                <div class="info-label">Transaction #:</div>
                <div>{sale.id}</div>
            </div>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>Produit</th>
                    <th>Quantité</th>
                    <th>Prix unitaire</th>
                    <th>Total</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for item in items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        html_template += f"""
                <tr>
                    <td>{product.name if product else 'N/A'}</td>
                    <td>{item.quantity}</td>
                    <td>{item.unit_price} DA</td>
                    <td>{item.quantity * item.unit_price} DA</td>
                </tr>
        """
    
    html_template += f"""
            </tbody>
        </table>
        
        <div class="total">Total: {sale.total_amount} DA</div>
        
        <div class="footer">
            <p>Document généré automatiquement par OMISTOCK</p>
            <p>Date d'émission: {sale.date.strftime('%d/%m/%Y %H:%M') if sale.date else 'N/A'}</p>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_template)


@router.get("/api/movements", response_model=List[schemas.StockMovementResponse])
def get_movements_route(
    current_user: Optional[models.User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id if current_user else 1
    return repository.get_movements(db, cid)
