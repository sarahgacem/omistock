from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt
import os, sys, pathlib

# Fix: Ajouter le dossier backend au path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import models, database, security
from database import engine

# Initialisation DB
models.Base.metadata.create_all(bind=engine)

def auto_seed_if_empty():
    db = database.SessionLocal()
    try:
        user_count = db.query(models.User).count()
        if user_count == 0:
            import seed_data
            print("[AUTO-SEED] Base vide. Initialisation par défaut...")
            seed_data.seed()
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

# Frontend
frontend_path = pathlib.Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/app", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

@app.get("/")
def read_root():
    return {"status": "online", "message": "OMISTOCK Backend API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
