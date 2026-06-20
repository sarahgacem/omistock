from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from backend import repository
import models
import schemas
import services
import audit
from dependencies import get_current_user, get_current_human
from database import get_db
from services import log_audit

router = APIRouter()


def _corr(request: Request) -> str:
    return getattr(request.state, "correlation_id", None) or audit.new_correlation_id()


@router.get("/products", response_model=List[schemas.ProductResponse])
@router.get("/api/inventory", response_model=List[schemas.ProductResponse])
def get_products_route(
    branch_id: Optional[int] = None,
    sort: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Plus de fallback "company_id=1" : la dépendance garantit un utilisateur authentifié.
    products = repository.get_products(db, current_user.company_id, branch_id=branch_id)
    if sort == "date":
        products = sorted(products, key=lambda p: p.created_at or "", reverse=True)
    return products


@router.post("/api/products", response_model=schemas.ProductResponse)
def create_product_route(
    product: schemas.ProductCreate,
    request: Request,
    current_user: models.User = Depends(get_current_human),
    db: Session = Depends(get_db),
):
    new = repository.create_product(db, product, current_user.company_id)
    log_audit(db, current_user.id, "PRODUCT_CREATE", None,
              {"id": new.id, "name": new.name}, current_user.company_id,
              actor_type=current_user.user_type, entity_type="product",
              entity_id=new.id, correlation_id=_corr(request))
    return new


@router.get("/api/products/{product_id}", response_model=schemas.ProductResponse)
def get_product_route(
    product_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_product = repository.get_product_by_id_for_company(db, product_id, current_user.company_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    return db_product


@router.put("/api/products/{product_id}")
def update_product_route(
    product_id: int,
    product: schemas.ProductUpdate,
    request: Request,
    current_user: models.User = Depends(get_current_human),
    db: Session = Depends(get_db),
):
    db_product = repository.get_product_by_id_for_company(db, product_id, current_user.company_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Produit introuvable")

    old = {"name": db_product.name, "price": db_product.price, "quantity": db_product.total_quantity}
    update_data = product.dict(exclude_unset=True)
    if current_user.branch_id and "quantity" in update_data:
        update_data["branch_id"] = current_user.branch_id

    try:
        repository.update_product(db, product_id, update_data)
        log_audit(db, current_user.id, "PRODUCT_UPDATE", old, update_data,
                  current_user.company_id, actor_type=current_user.user_type,
                  entity_type="product", entity_id=product_id, correlation_id=_corr(request))
        return {"status": "updated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/products/{product_id}")
def delete_product_route(
    product_id: int,
    request: Request,
    current_user: models.User = Depends(get_current_human),
    db: Session = Depends(get_db),
):
    db_product = repository.get_product_by_id_for_company(db, product_id, current_user.company_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    try:
        repository.delete_product(db, product_id)
        log_audit(db, current_user.id, "PRODUCT_DELETE",
                  {"id": product_id, "name": db_product.name}, None,
                  current_user.company_id, actor_type=current_user.user_type,
                  entity_type="product", entity_id=product_id, correlation_id=_corr(request))
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/alerts", response_model=List[schemas.ProductResponse])
def get_alerts_route(
    branch_id: Optional[int] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return repository.get_alerts(db, current_user.company_id, branch_id)


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
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Analyse prédictive réelle. Trace l'action sous l'identité de l'appelant (humain ou agent),
    sans créer d'agent fantôme."""
    try:
        advice = services.analyze_product_mcp(
            db, data.product_id, current_user.company_id, current_user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    log_audit(db, current_user.id, "ANALYSE_PREDICTIVE", {"product_id": data.product_id},
              advice, current_user.company_id, actor_type=current_user.user_type,
              entity_type="product", entity_id=data.product_id, correlation_id=_corr(request))
    return {"analysis": advice}


@router.get("/api/branches", response_model=List[schemas.BranchResponse])
def get_branches_route(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return repository.get_branches(db, current_user.company_id)


@router.get("/api/suppliers", response_model=List[schemas.SupplierResponse])
def get_suppliers_route(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return repository.get_suppliers(db, current_user.company_id)


@router.get("/api/sales", response_model=List[schemas.SaleResponse])
def get_sales_route(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return repository.get_sales(db, current_user.company_id)


@router.post("/api/sales", response_model=schemas.SaleResponse)
def create_sale_route(
    sale: schemas.SaleCreate,
    request: Request,
    current_user: models.User = Depends(get_current_human),
    db: Session = Depends(get_db),
):
    corr = _corr(request)
    try:
        db_sale = repository.create_sale(
            db, sale, current_user.company_id, current_user.id, correlation_id=corr
        )
        log_audit(db, current_user.id, "SALE_CREATE", None,
                  {"sale_id": db_sale.id, "amount": db_sale.total_amount, "cost": db_sale.total_cost},
                  current_user.company_id, actor_type=current_user.user_type,
                  entity_type="sale", entity_id=db_sale.id, correlation_id=corr)
        return db_sale
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/sales/{sale_id}/reverse")
def reverse_sale_route(
    sale_id: int,
    request: Request,
    current_user: models.User = Depends(get_current_human),
    db: Session = Depends(get_db),
):
    """Rollback métier d'une vente : compensation stock + audit, sans suppression d'historique."""
    corr = _corr(request)
    try:
        sale = repository.reverse_sale(db, sale_id, current_user.company_id, current_user.id, correlation_id=corr)
        log_audit(db, current_user.id, "SALE_REVERSE", {"sale_id": sale_id}, {"status": "REVERSED"},
                  current_user.company_id, actor_type=current_user.user_type,
                  entity_type="sale", entity_id=sale_id, correlation_id=corr)
        return {"status": "reversed", "sale_id": sale.id}
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
        models.Sale.company_id == current_user.company_id,
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Vente introuvable")

    company = db.query(models.Company).filter(models.Company.id == current_user.company_id).first()
    branch = db.query(models.Branch).filter(models.Branch.id == sale.branch_id).first()
    user = current_user
    items = db.query(models.SaleItem).filter(models.SaleItem.sale_id == sale_id).all()

    rows = ""
    for item in items:
        product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
        rows += (
            f"<tr><td>{product.name if product else 'N/A'}</td>"
            f"<td>{item.quantity}</td><td>{item.unit_price} DA</td>"
            f"<td>{item.quantity * item.unit_price} DA</td></tr>"
        )

    html_template = f"""
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>Facture #{sale.id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
        .header {{ border-bottom: 2px solid #333; padding-bottom: 20px; margin-bottom: 30px; }}
        .company-name {{ font-size: 24px; font-weight: bold; color: #174092; }}
        .invoice-title {{ font-size: 28px; font-weight: bold; text-align: right; color: #333; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 30px; }}
        th {{ background: #174092; color: white; padding: 12px; text-align: left; }}
        td {{ border: 1px solid #ddd; padding: 12px; }}
        .total {{ font-size: 20px; font-weight: bold; text-align: right; margin-top: 30px; }}
        .footer {{ margin-top: 50px; text-align: center; color: #666; font-size: 12px; }}
    </style></head>
    <body>
        <div class="header">
            <div class="company-name">{company.name if company else 'OMISTOCK'}</div>
            <div class="invoice-title">FACTURE #{sale.id}</div>
        </div>
        <p><b>Date:</b> {sale.date.strftime('%d/%m/%Y %H:%M') if sale.date else 'N/A'} &nbsp;
           <b>Filiale:</b> {branch.name if branch else 'N/A'} &nbsp;
           <b>Vendeur:</b> {user.email if user else 'N/A'}</p>
        <table><thead><tr><th>Produit</th><th>Quantité</th><th>Prix unitaire</th><th>Total</th></tr></thead>
        <tbody>{rows}</tbody></table>
        <div class="total">Total: {sale.total_amount} DA</div>
        <div class="footer"><p>Document généré automatiquement par OMISTOCK</p></div>
    </body></html>
    """
    return HTMLResponse(content=html_template)


@router.get("/api/movements", response_model=List[schemas.StockMovementResponse])
def get_movements_route(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return repository.get_movements(db, current_user.company_id)
