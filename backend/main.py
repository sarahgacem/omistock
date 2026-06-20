from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import os, sys, pathlib, uuid

# Ajouter backend + racine projet au path (imports package + modules plats)
_backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_backend_dir)
sys.path.append(os.path.dirname(_backend_dir))

import config
import models, database, security  # noqa: E402
from database import engine  # noqa: E402

# Initialisation DB
models.Base.metadata.create_all(bind=engine)


def run_db_migrations():
    """
    Migrations additives best-effort pour SQLite (en attendant Alembic).
    N'ajoute que des colonnes manquantes ; n'altère jamais de données.
    Pour une vraie migration versionnée, voir docs/migrations.md.
    """
    from sqlalchemy import text, inspect
    additive = {
        "companies": [("commercial_register_number", "VARCHAR"), ("activity_sector", "VARCHAR"),
                      ("nif", "VARCHAR"), ("address", "VARCHAR"), ("email", "VARCHAR"), ("phone", "VARCHAR")],
        "users": [("is_active", "BOOLEAN DEFAULT 1"), ("deletion_deadline", "DATETIME"),
                  ("api_key", "VARCHAR"), ("autonomy_level", "VARCHAR DEFAULT 'read_only'"),
                  ("agent_scopes", "VARCHAR"), ("api_key_expires_at", "DATETIME"),
                  ("max_action_quantity", "INTEGER DEFAULT 0"), ("created_at", "DATETIME")],
        "suppliers": [("lead_time_days", "INTEGER DEFAULT 7")],
        "products": [("cost_price", "FLOAT DEFAULT 0"), ("safety_stock", "INTEGER DEFAULT 0"),
                     ("avg_daily_demand", "FLOAT DEFAULT 0"), ("lead_time_days", "INTEGER DEFAULT 0")],
        "stock_movements": [("actor_id", "INTEGER"), ("correlation_id", "VARCHAR"),
                            ("reverses_movement_id", "INTEGER"), ("reversed", "BOOLEAN DEFAULT 0")],
        "sales": [("total_cost", "FLOAT DEFAULT 0"), ("status", "VARCHAR DEFAULT 'CONFIRMED'"),
                  ("actor_id", "INTEGER")],
        "sale_items": [("unit_cost", "FLOAT DEFAULT 0")],
        "audit_logs": [("actor_type", "VARCHAR"), ("entity_type", "VARCHAR"), ("entity_id", "INTEGER"),
                       ("correlation_id", "VARCHAR"), ("prev_hash", "VARCHAR"), ("entry_hash", "VARCHAR"),
                       ("hash_ts", "VARCHAR")],
        "transfer_requests": [("origin", "VARCHAR DEFAULT 'HUMAIN'")],
        "purchase_orders": [("branch_id", "INTEGER"), ("received_at", "DATETIME")],
    }
    try:
        insp = inspect(engine)
        existing_tables = set(insp.get_table_names())
        with engine.connect() as conn:
            for table, cols in additive.items():
                if table not in existing_tables:
                    continue
                present = {c["name"] for c in insp.get_columns(table)}
                for col, ddl in cols:
                    if col not in present:
                        try:
                            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
                        except Exception as e:  # colonne déjà créée par create_all
                            print(f"[MIGRATIONS] skip {table}.{col}: {e}")
            conn.commit()
        print("[MIGRATIONS] DB migrations appliquées.")
    except Exception as e:
        print(f"[MIGRATIONS] Warning: {e}")


run_db_migrations()


def auto_seed_if_empty():
    # Seed automatique UNIQUEMENT hors production (évite les comptes démo en prod).
    if config.IS_PROD:
        return
    db = database.SessionLocal()
    try:
        if db.query(models.User).count() == 0:
            import seed_data
            print("[AUTO-SEED] Base vide (dev). Initialisation par défaut...")
            seed_data.seed(admin_only=False)
    except Exception as e:
        print(f"ERR Auto-seed: {e}")
    finally:
        db.close()


auto_seed_if_empty()

app = FastAPI(title="OMISTOCK ERP - API")

# CORS : liste d'origines explicite (plus de wildcard avec credentials).
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Correlation-Id"],
)


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Ajoute un identifiant de corrélation à chaque requête (traçabilité bout-en-bout).
    NOTE : l'isolation multi-tenant est appliquée dans la couche DAL/dépendances
    (chaque requête filtre par company_id), pas ici. Ce middleware ne fait donc
    plus de "fausse" sécurité no-op.
    """
    async def dispatch(self, request: Request, call_next):
        corr = request.headers.get("X-Correlation-Id") or uuid.uuid4().hex
        request.state.correlation_id = corr
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = corr
        return response


app.add_middleware(CorrelationMiddleware)

# Routers
from routers import auth, products, transfers, admin, agent  # noqa: E402

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(transfers.router)
app.include_router(admin.router)
app.include_router(agent.router)


@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=404, content={"message": "Ressource non trouvée", "path": request.url.path})


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
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
