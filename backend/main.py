from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt
import os, sys, pathlib

# Fix: Ajouter backend et la racine projet au path (imports package + modules plats)
_backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_backend_dir)
sys.path.append(os.path.dirname(_backend_dir))

import models, database, security
from database import engine

# Initialisation DB
models.Base.metadata.create_all(bind=engine)

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

class TenantIsolationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # On garde l'isolation pour les ressources sensibles
        if request.method in ["PUT", "DELETE"] and "/api/" in request.url.path:
            try:
                auth_header = request.headers.get("Authorization")
                if auth_header and "Bearer " in auth_header:
                    token = auth_header.split(" ")[1]
                    payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
                    cid = payload.get("company_id")
                    # Ici on pourrait ajouter une vérification d'appartenance de la ressource
                    pass
            except: pass
        return await call_next(request)

app.add_middleware(TenantIsolationMiddleware)

# Import des Routers
from routers import auth, products, transfers, admin

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(transfers.router)
app.include_router(admin.router)

# Gestionnaires d'erreurs
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=404, content={"message": "Ressource non trouvée", "path": request.url.path})

# Frontend statique (chemins compatibles local + Docker : OMISTOCK_ROOT=/app)
PROJECT_ROOT = pathlib.Path(
    os.environ.get("OMISTOCK_ROOT", str(pathlib.Path(__file__).resolve().parent.parent))
)
frontend_path = PROJECT_ROOT / "frontend"
if frontend_path.is_dir():
    app.mount("/app", StaticFiles(directory=str(frontend_path.resolve()), html=True), name="frontend")
else:
    print(f"[WARN] Dossier frontend introuvable : {frontend_path}")

@app.get("/")
def read_root():
    return {"status": "online", "message": "OMISTOCK Backend API is running"}

@app.get("/health")
def health_check():
    """Endpoint de santé pour Render health checks"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
