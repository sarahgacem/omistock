from fastapi import FastAPI, Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from jose import JWTError, jwt
import os, sys, pathlib
from datetime import datetime, timedelta

# Fix: Ajouter le dossier backend au path pour permettre les imports quand on lance depuis la racine
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import secrets

import models, schemas, security, database, services
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
            c1 = db.query(models.Company).filter(models.Company.name == "OMISTOCK BUSINESS SOLUTIONS").first()
            if not c1:
                c1 = models.Company(name="OMISTOCK BUSINESS SOLUTIONS")
                db.add(c1)
                db.commit()
                db.refresh(c1)
                b1 = models.Branch(name="Dépôt Alger - Logistique", city="Alger", company_id=c1.id)
                b2 = models.Branch(name="Dépôt Oran - Distribution", city="Oran", company_id=c1.id)
                db.add_all([b1, b2])
                db.commit()
            
            c2 = db.query(models.Company).filter(models.Company.name == "AGRO-INDUSTRIE DZ").first()
            if not c2:
                c2 = models.Company(name="AGRO-INDUSTRIE DZ")
                db.add(c2)
                db.commit()
                db.refresh(c2)
                b3 = models.Branch(name="Unité Constantine", city="Constantine", company_id=c2.id)
                db.add(b3)
                db.commit()

            # 0.1 Utilisateurs
            if user_count == 0:
                h_pass = security.get_password_hash("password123")
                u1 = models.User(email="admin@test.com", hashed_password=h_pass, company_id=c1.id, branch_id=b1.id, user_type="ADMIN")
                u2 = models.User(email="oran@test.com", hashed_password=h_pass, company_id=c1.id, branch_id=b2.id, user_type="ADMIN")
                u3 = models.User(email="agro_admin@test.com", hashed_password=h_pass, company_id=c2.id, branch_id=b3.id, user_type="ADMIN")
                db.add_all([u1, u2, u3])
                db.commit()
                print("OK: Utilisateurs admin (Alger, Oran, Constantine) créés.")
            
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

            # 2. Ajouter des produits universels (IT, Santé, Agro)
            if product_count == 0:
                s1 = db.query(models.Supplier).first()
                p_list = [
                    # IT / Tech
                    models.Product(name="Ordinateur Portable HP Victus", sku="IT-HP-VCT", price=145000.0, quantity=25, min_threshold=5, company_id=company.id, supplier_id=s1.id),
                    models.Product(name="Serveur Dell PowerEdge", sku="IT-DEL-SRV", price=450000.0, quantity=5, min_threshold=2, company_id=company.id, supplier_id=s1.id),
                    
                    # Santé / Pharma
                    models.Product(name="Doliprane 500mg (Boîte 16)", sku="PHA-DOL-500", price=250.0, quantity=500, min_threshold=100, company_id=company.id, supplier_id=s1.id),
                    models.Product(name="Lecteur Glycémie Accu-Chek", sku="MED-ACC-GLY", price=3500.0, quantity=50, min_threshold=10, company_id=company.id, supplier_id=s1.id),
                    
                    # Agro / Alimentation
                    models.Product(name="Huile de Tournesol 5L", sku="AGR-HUI-5L", price=1200.0, quantity=150, min_threshold=30, company_id=company.id, supplier_id=s1.id),
                    models.Product(name="Café Robusta 250g", sku="AGR-CAF-250", price=450.0, quantity=200, min_threshold=50, company_id=company.id, supplier_id=s1.id),
                    
                    # Cosmétique
                    models.Product(name="Écran Solaire SPF50", sku="COS-SUN-50", price=1800.0, quantity=60, min_threshold=15, company_id=company.id, supplier_id=s1.id)
                ]
                db.add_all(p_list)
                db.commit()
                
                # Créer l'inventaire pour chaque produit dans chaque branche (Distribution Inégale pour la Démo)
                branches = db.query(models.Branch).filter(models.Branch.company_id == company.id).all()
                for i, p in enumerate(p_list):
                    for j, b in enumerate(branches):
                        # Distribution inégale : le premier dépôt (Alger) reçoit plus que le deuxième (Oran)
                        # Pour certains produits, Oran recevra 0 pour montrer la rupture de stock
                        qty = 0
                        if j == 0: # Alger
                            qty = p.quantity
                        elif i % 2 == 0: # Oran reçoit seulement les produits pairs
                            qty = p.quantity // 4
                            p.quantity += qty # On ajuste le total global du produit
                        
                        inv = models.Inventory(
                            product_id=p.id,
                            branch_id=b.id,
                            quantity=qty,
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

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=404,
        content={"message": "Ressource non trouvée. L'URL n'existe pas ou la ressource a été supprimée.", "path": request.url.path}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Professional error handling logging can go here
    return JSONResponse(
        status_code=500,
        content={"message": "Une erreur inattendue s'est produite sur le serveur.", "details": str(exc)}
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

def log_audit(db: Session, user_id: int, action: str, old_val: str, new_val: str, company_id: int):
    log = models.AuditLog(
        user_id=user_id,
        action=action,
        old_value=old_val,
        new_value=new_val,
        company_id=company_id
    )
    db.add(log)
    db.commit()

def get_current_user(token: Optional[str] = Depends(oauth2_scheme), x_api_key: Optional[str] = Header(None), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expirée ou invalide. Veuillez vous reconnecter.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if x_api_key:
        user = db.query(models.User).filter(models.User.api_key == x_api_key).first()
        if user:
            return user
        raise credentials_exception

    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        email: str = payload.get("sub")
        company_id: int = payload.get("company_id")
        if email is None or company_id is None:
            raise credentials_exception
        user = db.query(models.User).filter(models.User.email == email).first()
        if user is None:
            raise credentials_exception
        return user
    except JWTError:
        raise credentials_exception

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
@app.get("/api/me")
def get_me(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    branch_name = current_user.branch.name if current_user.branch else "N/A"
    return {
        "id": current_user.id,
        "email": current_user.email,
        "branch_id": current_user.branch_id,
        "branch_name": branch_name,
        "company_id": current_user.company_id,
        "user_type": current_user.user_type
    }

@app.post("/token", response_model=schemas.Token)
@app.post("/api/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    try:
        return services.authenticate_user(db, form_data)
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e), headers={"WWW-Authenticate": "Bearer"})

@app.post("/api/signup")
def signup(data: schemas.UserSignUp, db: Session = Depends(get_db)):
    try:
        return services.create_user_service(db, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/products", response_model=List[schemas.ProductResponse])
@app.get("/api/inventory", response_model=List[schemas.ProductResponse])
def get_products(
    branch_id: Optional[int] = None, 
    sort: Optional[str] = None,
    current_user: Optional[models.User] = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    try:
        cid = current_user.company_id if current_user else 1
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

@app.get("/api/transfer/requests", response_model=List[schemas.TransferRequestResponse])
def get_transfer_requests(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.TransferRequest).filter(models.TransferRequest.company_id == current_user.company_id).order_by(models.TransferRequest.created_at.desc()).all()

@app.post("/api/transfer/request")
def request_transfer(data: schemas.TransferRequestCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id
    req = models.TransferRequest(
        product_id=data.product_id,
        from_branch_id=data.from_branch_id,
        to_branch_id=data.to_branch_id,
        quantity=data.quantity,
        requester_id=current_user.id,
        company_id=cid
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    log_audit(db, current_user.id, f"TRANSFER_REQUESTED_{req.id}", "N/A", f"Qty:{req.quantity}", current_user.company_id)
    return {"status": "success", "message": "Demande de transfert envoyée"}

@app.post("/api/transfer/{req_id}/approve")
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
    db.commit()
    
    log_audit(db, current_user.id, f"TRANSFER_APPROVED_{req_id}", f"Source:{old_from}->{from_inv.quantity}", "En transit", current_user.company_id)
    
    return {"status": "success", "message": "Transfert approuvé, en attente de confirmation"}

@app.post("/api/transfer/{req_id}/confirm")
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
    db.commit()
    
    log_audit(db, current_user.id, f"TRANSFER_CONFIRMED_{req_id}", "En transit", f"Dest:{old_to}->{to_inv.quantity}", current_user.company_id)
    
    return {"status": "success", "message": "Transfert confirmé et stock mis à jour"}

@app.get("/products/{product_id}", response_model=schemas.ProductResponse)
@app.get("/api/products/{product_id}", response_model=schemas.ProductResponse)
def get_product(product_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id, models.Product.company_id == current_user.company_id).first()
    if not db_product: raise HTTPException(status_code=404)
    return db_product

@app.get("/api/alerts", response_model=List[schemas.ProductResponse])
def get_alerts(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.Product).filter(
        models.Product.company_id == cid,
        models.Product.quantity <= models.Product.min_threshold
    ).all()

@app.get("/dashboard/stats")
@app.get("/api/stats")
@app.get("/api/dashboard/stats")
def get_dashboard_stats(branch_id: Optional[int] = None, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return services.get_dashboard_stats_data(db, current_user.company_id, branch_id)
    except Exception as e:
        import traceback
        print(f"Erreur Stats: {e}")
        traceback.print_exc()
        return {
            "summary": {"total_products": 0, "alerts_count": 0, "total_value": 0, "total_qty": 0},
            "alerts": [], "top_5": [], "top_sold": [], "movements": [], "trend": []
        }

@app.post("/api/mcp/analyze")
def analyze_product_mcp_post(data: schemas.ProductAnalyzeRequest, current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        advice = services.analyze_product_mcp(db, data.product_id, current_user.company_id, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
        
    # Get or create an AGENT user for logging
    agent = db.query(models.User).filter(models.User.company_id == current_user.company_id, models.User.user_type == "AGENT").first()
    if not agent:
        import secrets
        agent = models.User(email=f"mcp_agent_{secrets.token_hex(4)}@agent.local", user_type="AGENT", company_id=current_user.company_id)
        db.add(agent)
        db.commit()
        db.refresh(agent)
        
    # Log the analysis as AGENT
    log_audit(db, agent.id, f"ANALYSE_PREDICTIVE_{data.product_id}", "N/A", advice, current_user.company_id)
        
    return {"analysis": advice}

@app.get("/scan/{barcode}", response_model=schemas.ProductResponse)
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
    old_qty = product.quantity
    product.quantity += data.get('quantity', 1)
    db.commit()
    log_audit(db, current_user.id, "SCAN_ADD_STOCK", str(old_qty), str(product.quantity), current_user.company_id)
    return {"new_quantity": product.quantity}

@app.post("/scan/sell")
def scan_sell(data: dict, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.barcode == data.get('barcode'), models.Product.company_id == current_user.company_id).first()
    if not product: raise HTTPException(status_code=404)
    if product.quantity > 0:
        old_qty = product.quantity
        product.quantity -= data.get('quantity', 1)
        db.commit()
        log_audit(db, current_user.id, "SCAN_SELL_STOCK", str(old_qty), str(product.quantity), current_user.company_id)
        return {"new_quantity": product.quantity}
    raise HTTPException(status_code=400)

@app.get("/branches", response_model=List[schemas.BranchResponse])
@app.get("/api/branches", response_model=List[schemas.BranchResponse])
def get_branches(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.Branch).filter(models.Branch.company_id == cid).all()

@app.get("/api/suppliers", response_model=List[schemas.SupplierResponse])
def get_suppliers(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.Supplier).filter(models.Supplier.company_id == cid).all()

@app.get("/sales", response_model=List[schemas.SaleResponse])
@app.get("/api/sales", response_model=List[schemas.SaleResponse])
def get_sales(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.Sale).filter(models.Sale.company_id == cid).all()

@app.get("/sales/{sale_id}/invoice/html")
def get_invoice_html(sale_id: int, db: Session = Depends(get_db)):
    sale = db.query(models.Sale).filter(models.Sale.id == sale_id).first()
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

@app.get("/api/audit_logs", response_model=List[schemas.AuditLogResponse])
def get_audit_logs(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    logs = db.query(models.AuditLog).filter(models.AuditLog.company_id == current_user.company_id).order_by(models.AuditLog.timestamp.desc()).all()
    for log in logs:
        user = db.query(models.User).filter(models.User.id == log.user_id).first()
        if user:
            log.user_email = user.email
            log.user_type = user.user_type
    return logs

@app.post("/api/agents", response_model=schemas.AgentAccessResponse)
def create_agent(data: schemas.AgentAccessCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.user_type != "HUMAIN":
        raise HTTPException(status_code=403, detail="Seuls les humains peuvent créer des agents")
        
    api_key = secrets.token_urlsafe(32)
    email = f"agent_{secrets.token_hex(4)}@agent.local"
    
    new_user = models.User(
        email=email,
        hashed_password=None,
        user_type="AGENT",
        api_key=api_key,
        company_id=current_user.company_id,
        branch_id=current_user.branch_id
    )
    db.add(new_user)
    db.commit()
    
    return {"email": email, "api_key": api_key, "user_type": "AGENT"}

@app.get("/api/agents", response_model=List[schemas.AgentAccessResponse])
def get_agents(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.User).filter(models.User.company_id == current_user.company_id, models.User.user_type == "AGENT").all()

# --- ROUTES DE MAINTENANCE (ADMIN SEULEMENT) ---
import seed_data

@app.post("/api/admin/seed")
def seed_database_route(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.user_type != "ADMIN":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    seed_data.seed()
    return {"status": "success", "message": "Base de données initialisée avec succès."}

@app.post("/api/admin/clean")
def clean_database_route(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.user_type != "ADMIN":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    try:
        db.query(models.ActivityLog).delete()
        db.query(models.AuditLog).delete()
        db.query(models.StockMovement).delete()
        db.query(models.SaleItem).delete()
        db.query(models.Sale).delete()
        db.query(models.TransferRequest).delete()
        db.query(models.Customer).delete()
        db.query(models.Inventory).delete()
        db.query(models.Product).delete()
        db.query(models.Supplier).delete()
        # Ne pas supprimer les utilisateurs pour garder l'accès admin
        # Ne pas supprimer les entreprises et branches
        db.commit()
        return {"status": "success", "message": "Base de données nettoyée avec succès (structure et utilisateurs conservés)."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors du nettoyage : {e}")

frontend_path = pathlib.Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/app", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    auto_seed_if_empty()
    uvicorn.run(app, host="0.0.0.0", port=8000)
