from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from jose import JWTError, jwt
import os, pathlib
from datetime import datetime, timedelta

import models, schemas, security, database
from database import engine, get_db

# Initialisation
models.Base.metadata.create_all(bind=engine)

def auto_seed_if_empty():
    db = database.SessionLocal()
    try:
        # Vérifier les tables principales
        supplier_count = db.query(models.Supplier).count()
        product_count = db.query(models.Product).count()
        sale_count = db.query(models.Sale).count()
        movement_count = db.query(models.StockMovement).count()
        user_count = db.query(models.User).count()
        
        if user_count == 0 or supplier_count == 0:
            print("[AUTO-SEED] Base incomplète. Initialisation des comptes démo...")
            
            # 0. Entreprises et Branches
            c1 = db.query(models.Company).filter(models.Company.name == "SANTÉ PRO ALGERIE").first()
            if not c1:
                c1 = models.Company(name="SANTÉ PRO ALGERIE")
                db.add(c1)
                db.commit()
                db.refresh(c1)
                b1 = models.Branch(name="Dépôt Alger", city="Alger", company_id=c1.id)
                b2 = models.Branch(name="Dépôt Oran", city="Oran", company_id=c1.id)
                db.add_all([b1, b2])
                db.commit()
            
            c2 = db.query(models.Company).filter(models.Company.name == "ALIMENTATION DZ").first()
            if not c2:
                c2 = models.Company(name="ALIMENTATION DZ")
                db.add(c2)
                db.commit()
                db.refresh(c2)
                b3 = models.Branch(name="Dépôt Constantine", city="Constantine", company_id=c2.id)
                db.add(b3)
                db.commit()

            # 0.1 Utilisateurs
            if user_count == 0:
                h_pass = security.get_password_hash("password123")
                u1 = models.User(email="admin@test.com", hashed_password=h_pass, company_id=c1.id)
                u2 = models.User(email="food_admin@test.com", hashed_password=h_pass, company_id=c2.id)
                db.add_all([u1, u2])
                db.commit()
                print("OK: Utilisateurs admin créés.")
            
            # Utiliser c1 par défaut pour le reste du seeding
            company = c1
            branch = db.query(models.Branch).filter(models.Branch.company_id == company.id).first()

            # 1. Ajouter 5 fournisseurs
            if supplier_count == 0:
                suppliers = [
                    models.Supplier(name="Saidal Group", email="contact@saidal.dz", company_id=company.id),
                    models.Supplier(name="Biopharm", email="info@biopharm.com", company_id=company.id),
                    models.Supplier(name="Indusdz", email="sales@indusdz.dz", company_id=company.id),
                    models.Supplier(name="Hikma Pharma", email="contact@hikma.dz", company_id=company.id),
                    models.Supplier(name="Frater Razes", email="info@frater.com", company_id=company.id)
                ]
                db.add_all(suppliers)
                db.commit()
                print("OK: 5 fournisseurs ajoutés.")

            # 2. Ajouter des produits universels et leur inventaire
            if product_count == 0:
                s1 = db.query(models.Supplier).first()
                p_list = [
                    models.Product(name="Ordinateur Portable HP", sku="ELEC-HP-15", price=85000.0, quantity=25, min_threshold=5, company_id=company.id, supplier_id=s1.id),
                    models.Product(name="Doliprane 500mg", sku="PHA-DOL-500", price=250.0, quantity=500, min_threshold=100, company_id=company.id, supplier_id=s1.id),
                    models.Product(name="Café Robusta 250g", sku="FOOD-CAF-250", price=450.0, quantity=200, min_threshold=50, company_id=company.id, supplier_id=s1.id),
                    models.Product(name="Smartphone Galaxy", sku="ELEC-GAL-S21", price=65000.0, quantity=15, min_threshold=3, company_id=company.id, supplier_id=s1.id),
                    models.Product(name="Huile de Tournesol 5L", sku="FOOD-HUI-5L", price=1200.0, quantity=150, min_threshold=30, company_id=company.id, supplier_id=s1.id)
                ]
                db.add_all(p_list)
                db.commit()
                
                # Créer l'inventaire pour chaque produit dans chaque branche
                branches = db.query(models.Branch).filter(models.Branch.company_id == company.id).all()
                for p in p_list:
                    for b in branches:
                        inv = models.Inventory(
                            product_id=p.id,
                            branch_id=b.id,
                            quantity=p.quantity // len(branches) if len(branches) > 0 else p.quantity,
                            min_threshold=p.min_threshold
                        )
                        db.add(inv)
                db.commit()
                print("OK: Produits Universels ajoutés.")

            # 3. Ajouter des ventes si vide
            if sale_count == 0:
                p1 = db.query(models.Product).first()
                for i in range(3):
                    sale = models.Sale(total_amount=p1.price * 2, company_id=company.id, branch_id=branch.id)
                    db.add(sale)
                    db.commit()
                    db.refresh(sale)
                    item = models.SaleItem(sale_id=sale.id, product_id=p1.id, quantity=2, unit_price=p1.price)
                    db.add(item)
                db.commit()
                print("OK: 3 ventes de test ajoutées.")

            # 4. Mouvements de stock
            if movement_count == 0:
                product = db.query(models.Product).first()
                for i in range(10):
                    mov = models.StockMovement(
                        product_id=product.id,
                        branch_id=branch.id,
                        quantity=10,
                        reason=f"Ajustement auto #{i+1}",
                        movement_type="IN",
                        company_id=company.id
                    )
                    db.add(mov)
                db.commit()
                print("OK: 10 mouvements de stock ajoutés.")
                
    except Exception as e:
        print(f"ERR: Erreur lors de l'auto-seeding : {e}")
    finally:
        db.close()

# Exécuter l'auto-seed au démarrage
auto_seed_if_empty()

app = FastAPI(title="OMISTOCK - Système d'Inventaire")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification invalide",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
    except JWTError:
        raise credentials_exception
    email = payload.get("sub")
    company_id = payload.get("company_id")
    if email is None or company_id is None:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
    return user

# Isolation Middleware
class TenantIsolationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in ["PUT", "DELETE"]:
            path_parts = request.url.path.strip("/").split("/")
            if len(path_parts) >= 2 and path_parts[0] in ["products", "sales", "api"]:
                res_type = path_parts[1] if path_parts[0] == "api" else path_parts[0]
                idx = 2 if path_parts[0] == "api" else 1
                try:
                    resource_id = int(path_parts[idx])
                    auth_header = request.headers.get("Authorization")
                    if auth_header and "Bearer " in auth_header:
                        token = auth_header.split(" ")[1]
                        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
                        cid = payload.get("company_id")
                        db = database.SessionLocal()
                        try:
                            obj = db.query(models.Product).filter(models.Product.id == resource_id).first() if res_type == "products" else None
                            if obj and obj.company_id != cid:
                                return JSONResponse(status_code=403, content={"detail": "Accès refusé"})
                        finally:
                            db.close()
                except: pass
        return await call_next(request)

app.add_middleware(TenantIsolationMiddleware)

# --- ROUTES ---
@app.post("/token", response_model=schemas.Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Identifiants incorrects")
    access_token = security.create_access_token(data={"sub": user.email, "company_id": user.company_id})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/products", response_model=List[schemas.ProductResponse])
@app.get("/api/inventory", response_model=List[schemas.ProductResponse])
def get_products(
    branch_id: Optional[int] = None,
    sort: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        cid = current_user.company_id
        query = db.query(models.Product).filter(models.Product.company_id == cid)
        
        # Filter by Branch (Localisation) if provided
        if branch_id:
            query = query.join(models.Inventory).filter(models.Inventory.branch_id == branch_id)
        
        # Sort by Date d'ajout
        if sort == "date":
            query = query.order_by(models.Product.created_at.desc())
        
        return query.all()
    except Exception as e:
        print(f"ERR: Erreur lors de la récupération des produits : {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/products", response_model=schemas.ProductResponse)
@app.post("/api/products", response_model=schemas.ProductResponse)
def create_product(product: schemas.ProductCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_product = models.Product(**product.dict(), company_id=current_user.company_id)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@app.put("/products/{product_id}")
@app.put("/api/products/{product_id}")
def update_product(product_id: int, product: schemas.ProductUpdate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id, models.Product.company_id == current_user.company_id).first()
    if not db_product: raise HTTPException(status_code=404)
    update_data = product.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_product, key, value)
    db.commit()
    return {"status": "updated"}

@app.delete("/products/{product_id}")
@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id, models.Product.company_id == current_user.company_id).first()
    if not db_product: raise HTTPException(status_code=404)
    db.delete(db_product)
    db.commit()
    return {"status": "deleted"}

@app.post("/api/transfer")
def transfer_stock(data: schemas.TransferCreate, current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    
    # Récupérer l'inventaire des deux dépôts
    from_inv = db.query(models.Inventory).filter(models.Inventory.product_id == data.product_id, models.Inventory.branch_id == data.from_branch_id).first()
    to_inv = db.query(models.Inventory).filter(models.Inventory.product_id == data.product_id, models.Inventory.branch_id == data.to_branch_id).first()
    
    if from_inv:
        if from_inv.quantity < data.quantity:
            raise HTTPException(status_code=400, detail="Stock insuffisant dans le dépôt source")
        from_inv.quantity -= data.quantity
    
    if to_inv:
        to_inv.quantity += data.quantity
    else:
        # Créer l'entrée si elle n'existe pas dans le dépôt de destination
        to_inv = models.Inventory(product_id=data.product_id, branch_id=data.to_branch_id, quantity=data.quantity, min_threshold=5)
        db.add(to_inv)
        
    # Historiser le mouvement pour le dashboard
    movement = models.StockMovement(
        product_id=data.product_id, 
        branch_id=data.from_branch_id, 
        quantity=-data.quantity, 
        reason="Transfert vers dépôt", 
        company_id=cid, 
        movement_type="OUT"
    )
    db.add(movement)
    
    db.commit()
    return {"status": "success", "message": "Transfert réussi"}

@app.get("/products/{product_id}")
@app.get("/api/products/{product_id}")
def get_product(product_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id, models.Product.company_id == current_user.company_id).first()
    if not db_product: raise HTTPException(status_code=404)
    return db_product

@app.get("/api/alerts", response_model=List[schemas.ProductResponse])
def get_alerts(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id
    return db.query(models.Product).filter(
        models.Product.company_id == cid,
        models.Product.quantity <= models.Product.min_threshold
    ).all()

@app.get("/dashboard/stats")
@app.get("/api/stats")
def get_dashboard_stats(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        cid = current_user.company_id
        products = db.query(models.Product).filter(models.Product.company_id == cid).all()
        
        if not products:
            return {
                "summary": {"total_products": 0, "alerts_count": 0, "total_value": 0, "total_qty": 0},
                "alerts": [], "top_5": [], "top_sold": [], "movements": [], "trend": []
            }

        total_products = len(products)
        alerts = [p for p in products if (p.quantity or 0) <= (p.min_threshold or 0)]
        total_qty = sum((p.quantity or 0) for p in products)
        total_value = sum((p.price or 0) * (p.quantity or 0) for p in products)

        # Real trends from StockMovements
        today = datetime.now().date()
        start_date = today - timedelta(days=6)
        
        movements_db = db.query(models.StockMovement).filter(
            models.StockMovement.company_id == cid
        ).all()

        # Aggregate by day for IN and OUT
        trend_dict = { (start_date + timedelta(days=i)).strftime("%A"): {"in": 0, "out": 0} for i in range(7) }
        
        for mov in movements_db:
            mov_date = mov.created_at.date() if mov.created_at else today
            if start_date <= mov_date <= today:
                day_name = mov_date.strftime("%A")
                if day_name in trend_dict:
                    if mov.movement_type == "IN" or (mov.quantity and mov.quantity > 0):
                        trend_dict[day_name]["in"] += abs(mov.quantity or 0)
                    else:
                        trend_dict[day_name]["out"] += abs(mov.quantity or 0)
                    
        trend = [{"day": day, "in": data["in"], "out": data["out"]} for day, data in trend_dict.items()]

        # Top 5
        top_5 = sorted(products, key=lambda x: x.quantity, reverse=True)[:5]
        
        return {
            "summary": {
                "total_products": total_products,
                "alerts_count": len(alerts),
                "total_value": total_value,
                "total_qty": total_qty
            },
            "alerts": [{"id": p.id, "name": p.name, "quantity": p.quantity} for p in alerts],
            "top_5": [{"name": p.name, "quantity": p.quantity} for p in top_5],
            "top_sold": [],
            "movements": [],
            "trend": trend
        }
    except Exception as e:
        print(f"Erreur Stats: {e}")
        return {
            "summary": {"total_products": 0, "alerts_count": 0, "total_value": 0, "total_qty": 0},
            "alerts": [], "top_5": [], "top_sold": [], "movements": [], "trend": []
        }

@app.get("/products/{product_id}/analyze")
@app.get("/api/products/{product_id}/analyze")
def analyze_product_mcp(product_id: int, current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produit non trouvé")
    
    qty = product.quantity or 0
    thresh = product.min_threshold or 0
    
    # Simulation d'analyse IA "MCP"
    if qty <= thresh:
        advice = f"Stock de {product.name} faible ({qty} unités), prévoyez une commande."
    elif qty < thresh * 2:
        advice = f"Stock de {product.name} moyen ({qty} unités), surveillez les ventes."
    else:
        advice = f"Stock de {product.name} optimal ({qty} unités), aucune action requise."
        
    return {"analysis": advice}

@app.get("/scan/{barcode}")
def scan_product(barcode: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(
        (models.Product.barcode == barcode) | (models.Product.sku == barcode) | (models.Product.id.cast(models.String) == barcode),
        models.Product.company_id == current_user.company_id
    ).first()
    if not product: raise HTTPException(status_code=404)
    return product

@app.post("/scan/add")
def scan_add(data: dict, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.barcode == data.get('barcode'), models.Product.company_id == current_user.company_id).first()
    if not product: raise HTTPException(status_code=404)
    product.quantity += data.get('quantity', 1)
    db.commit()
    return {"new_quantity": product.quantity}

@app.post("/scan/sell")
def scan_sell(data: dict, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.barcode == data.get('barcode'), models.Product.company_id == current_user.company_id).first()
    if not product: raise HTTPException(status_code=404)
    if product.quantity > 0:
        product.quantity -= data.get('quantity', 1)
        db.commit()
        return {"new_quantity": product.quantity}
    raise HTTPException(status_code=400)

@app.get("/branches")
@app.get("/api/branches")
def get_branches(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.Branch).filter(models.Branch.company_id == cid).all()

@app.get("/api/suppliers", response_model=List[schemas.SupplierResponse])
def get_suppliers(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.Supplier).filter(models.Supplier.company_id == cid).all()

@app.get("/sales")
@app.get("/api/sales")
def get_sales(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.Sale).filter(models.Sale.company_id == cid).all()

@app.get("/sales/{sale_id}/invoice/html")
def get_invoice_html(sale_id: int, token: Optional[str] = None, db: Session = Depends(get_db)):
    # Authentification via token en query param (compatible avec window.open)
    if not token:
        raise HTTPException(status_code=401, detail="Authentification requise")
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        company_id = payload.get("company_id")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide")
    if company_id is None:
        raise HTTPException(status_code=401, detail="Token invalide")

    sale = db.query(models.Sale).filter(
        models.Sale.id == sale_id,
        models.Sale.company_id == company_id
    ).first()
    if not sale: raise HTTPException(status_code=404, detail="Vente non trouvée")
    
    items_html = "".join([f"<tr><td>{item.product.name}</td><td>{item.quantity}</td><td>{item.unit_price} DA</td><td>{item.quantity * item.unit_price} DA</td></tr>" for item in sale.items])
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: sans-serif; padding: 40px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .header {{ text-align: center; margin-bottom: 40px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>FACTURE OMISTOCK</h1>
            <p>Facture N° TR-{str(sale_id).zfill(4)}</p>
            <p>Date: {sale.date.strftime('%d/%m/%Y %H:%M')}</p>
        </div>
        <table>
            <thead><tr><th>Produit</th><th>Quantité</th><th>Prix Unit.</th><th>Total</th></tr></thead>
            <tbody>{items_html}</tbody>
        </table>
        <h2 style="text-align: right; margin-top: 30px;">Total: {sale.total_amount} DA</h2>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/movements", response_model=List[schemas.StockMovementResponse])
def get_movements(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.StockMovement).filter(models.StockMovement.company_id == cid).order_by(models.StockMovement.created_at.desc()).all()

frontend_path = pathlib.Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/app", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    auto_seed_if_empty()
    uvicorn.run(app, host="0.0.0.0", port=8000)
