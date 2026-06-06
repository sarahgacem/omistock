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
app = FastAPI(title="OMISTOCK - Système d'Inventaire")

def run_db_migrations():
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            for col in ["commercial_register_number", "activity_sector", "nif", "address", "email", "phone"]:
                try:
                    conn.execute(text(f"ALTER TABLE companies ADD COLUMN {col} VARCHAR"))
                except Exception:
                    pass
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
            except Exception:
                pass
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN deletion_deadline DATETIME"))
            except Exception:
                pass
            conn.commit()
        print("[MIGRATIONS] DB migrations applied successfully.")
    except Exception as e:
        print(f"[MIGRATIONS] Warning: {e}")

run_db_migrations()

def auto_seed_if_empty():
    db = database.SessionLocal()
    try:
        user_count = db.query(models.User).count()
        if user_count == 0:
            import seed_data
            print("[AUTO-SEED] Base vide. Initialisation par défaut...")
            seed_data.seed(admin_only=True)
    except Exception as e:
        print(f"ERR Auto-seed: {e}")
    finally:
        db.close()

auto_seed_if_empty()

app = FastAPI(title="OMISTOCK ERP - API")

# Middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        email: str = payload.get("sub")
        company_id: int = payload.get("company_id")
        if email is None or company_id is None:
            return None
        user = db.query(models.User).filter(models.User.email == email).first()
        return user
    except:
        return None

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
def get_products(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    return db.query(models.Product).filter(models.Product.company_id == cid).all()

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

@app.get("/health")
def health_check():
    """Endpoint de santé pour Render health checks"""
    return {"status": "healthy"}
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

@app.get("/dashboard/stats")
@app.get("/api/stats")
def get_dashboard_stats(current_user: Optional[models.User] = Depends(get_current_user), db: Session = Depends(get_db)):
    cid = current_user.company_id if current_user else 1
    products = db.query(models.Product).filter(models.Product.company_id == cid).all()
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
def get_branches(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Branch).filter(models.Branch.company_id == current_user.company_id).all()

frontend_path = pathlib.Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/app", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
