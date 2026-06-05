from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
import os
import csv
import io
import zipfile
import json
from datetime import datetime, timedelta

from backend import repository
import models
import schemas
import database
import seed_data
from dependencies import get_current_user, get_current_admin, get_current_agent_human
from database import get_db

router = APIRouter()


@router.post("/api/admin/seed")
def seed_database_route(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    seed_data.seed()
    return {"status": "success", "message": "Base de données initialisée avec succès."}


@router.post("/api/admin/clean")
def clean_database_route(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        repository.clean_database(db)
        return {"status": "success", "message": "Base de données nettoyée."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/backup")
def get_backup(current_user: models.User = Depends(get_current_admin)):
    db_path = database.db_path
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Fichier base de données introuvable.")

    date_str = datetime.now().strftime("%Y_%m_%d")
    zip_filename = f"backup_omistock_{date_str}.zip"
    zip_path = os.path.join(os.path.dirname(db_path), zip_filename)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(db_path, arcname=f"omistock_backup_{date_str}.db")

    return FileResponse(
        path=zip_path,
        filename=zip_filename,
        media_type="application/zip",
    )


@router.get("/api/admin/backup/json")
def get_backup_json(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    try:
        tables = [
            models.Company,
            models.Branch,
            models.User,
            models.Supplier,
            models.Product,
            models.Inventory,
            models.StockMovement,
            models.PurchaseOrder,
            models.PurchaseOrderItem,
            models.Customer,
            models.Sale,
            models.SaleItem,
            models.ActivityLog,
            models.AuditLog,
            models.TransferRequest
        ]
        data = {}
        for table in tables:
            rows = db.query(table).all()
            data[table.__tablename__] = []
            for row in rows:
                row_dict = {}
                for col in table.__table__.columns:
                    val = getattr(row, col.name)
                    if val is not None:
                        if isinstance(val, datetime):
                            row_dict[col.name] = val.isoformat()
                        else:
                            row_dict[col.name] = val
                data[table.__tablename__].append(row_dict)
        
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/restore")
async def restore_database(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    try:
        content = await file.read()
        filename = file.filename.lower()
        
        if filename.endswith(".json"):
            data = json.loads(content.decode("utf-8"))
            
            db.execute(text("PRAGMA foreign_keys = OFF"))
            tables_to_delete = [
                models.AuditLog,
                models.ActivityLog,
                models.TransferRequest,
                models.SaleItem,
                models.Sale,
                models.PurchaseOrderItem,
                models.PurchaseOrder,
                models.StockMovement,
                models.Inventory,
                models.Product,
                models.Supplier,
                models.User,
                models.Branch,
                models.Company
            ]
            for t in tables_to_delete:
                db.query(t).delete()
            db.commit()
            
            insert_order = [
                (models.Company, "companies"),
                (models.Branch, "branches"),
                (models.User, "users"),
                (models.Supplier, "suppliers"),
                (models.Product, "products"),
                (models.Inventory, "inventory"),
                (models.StockMovement, "stock_movements"),
                (models.PurchaseOrder, "purchase_orders"),
                (models.PurchaseOrderItem, "purchase_order_items"),
                (models.Customer, "customers"),
                (models.Sale, "sales"),
                (models.SaleItem, "sale_items"),
                (models.ActivityLog, "activity_logs"),
                (models.AuditLog, "audit_logs"),
                (models.TransferRequest, "transfer_requests")
            ]
            
            for model, tablename in insert_order:
                rows = data.get(tablename, [])
                for r in rows:
                    for col in model.__table__.columns:
                        if col.name in r and r[col.name] is not None:
                            if col.type.__class__.__name__ == 'DateTime':
                                try:
                                    r[col.name] = datetime.fromisoformat(r[col.name])
                                except Exception:
                                    pass
                    db_row = model(**r)
                    db.add(db_row)
            db.commit()
            db.execute(text("PRAGMA foreign_keys = ON"))
            return {"status": "success", "message": "Base de données restaurée avec succès depuis JSON."}
            
        elif filename.endswith(".sql") or filename.endswith(".db") or filename.endswith(".sqlite"):
            # If it's a raw SQL script
            if filename.endswith(".sql"):
                sql_script = content.decode("utf-8")
                db.execute(text("PRAGMA foreign_keys = OFF"))
                db.commit()
                raw_conn = db.connection().connection
                raw_conn.executescript(sql_script)
                db.commit()
                db.execute(text("PRAGMA foreign_keys = ON"))
                return {"status": "success", "message": "Base de données restaurée avec succès depuis SQL."}
            else:
                # If they upload a raw .db file, overwrite the active SQLite file
                db_path = database.db_path
                # Close sessions first
                db.close()
                database.engine.dispose()
                with open(db_path, "wb") as f:
                    f.write(content)
                # Re-open database
                database.SessionLocal = database.sessionmaker(autocommit=False, autoflush=False, bind=database.engine)
                return {"status": "success", "message": "Fichier de base de données SQLite écrasé avec succès."}
            
        else:
            raise HTTPException(status_code=400, detail="Format de fichier non supporté. Utilisez .json, .sql ou .db.")
            
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la restauration: {str(e)}")


@router.post("/api/admin/deactivate")
def deactivate_admin_account(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    try:
        current_user.is_active = False
        current_user.deletion_deadline = datetime.now() + timedelta(days=30)
        db.commit()
        return {"status": "success", "message": "Votre compte a été désactivé. Vous disposez de 30 jours pour le réactiver avant suppression définitive."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/users", response_model=List[schemas.UserResponse])
def get_company_users(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    return db.query(models.User).filter(models.User.company_id == current_user.company_id).all()


@router.delete("/api/admin/users/{user_id}")
def delete_company_user(
    user_id: int,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte admin via cette route. Utilisez la désactivation.")
        
    user = db.query(models.User).filter(
        models.User.id == user_id, 
        models.User.company_id == current_user.company_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
        
    try:
        db.delete(user)
        db.commit()
        return {"status": "success", "message": "Utilisateur supprimé avec succès."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/company", response_model=schemas.CompanyResponse)
def get_company(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    company = db.query(models.Company).filter(models.Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    return company


@router.put("/api/company", response_model=schemas.CompanyResponse)
def update_company(
    data: schemas.CompanyUpdate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    company = db.query(models.Company).filter(models.Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    
    update_dict = data.dict(exclude_unset=True)
    for k, v in update_dict.items():
        setattr(company, k, v)
    
    db.commit()
    db.refresh(company)
    return company


@router.get("/api/audit/export")
def export_logs(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    logs = repository.get_audit_logs(db, current_user.company_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Timestamp", "User_ID", "Action", "Old Value", "New Value"])

    for log in logs:
        writer.writerow([log.id, log.timestamp, log.user_id, log.action, log.old_value, log.new_value])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=logs_activite.csv"},
    )


@router.get("/api/audit_logs", response_model=List[schemas.AuditLogResponse])
def get_audit_logs_route(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return repository.get_audit_logs(db, current_user.company_id)


@router.post("/api/mcp/chat")
async def mcp_sandbox_chat(
    data: dict,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user_msg = data.get("message", "").lower()

    if "stock" in user_msg or "alerte" in user_msg:
        alerts = repository.get_alerts(db, current_user.company_id)
        if not alerts:
            reply = (
                "L'analyse MCP indique que tout est en ordre. "
                "Aucun produit n'est en alerte de stock actuellement."
            )
        else:
            reply = (
                f"L'agent IA a détecté {len(alerts)} produits en alerte critique. "
                "Une commande de réapprovisionnement est suggérée pour : "
                + ", ".join([p.name for p in alerts[:3]])
            )
    elif "ventes" in user_msg or "ca" in user_msg or "résumé" in user_msg:
        reply = (
            "Résumé Business : Le CA est stable. On observe une hausse de 12% sur les produits "
            "de la catégorie Pharma cette semaine. L'agent suggère d'augmenter le stock d'Amoxicilline."
        )
    else:
        reply = (
            f"Message reçu par l'Agent IA Omistock : '{user_msg}'. Je suis connecté à la base de "
            "données et prêt à analyser vos stocks ou vos ventes. Que puis-je faire pour vous ?"
        )

    return {"response": reply, "agent": "Omistock-MCP-Agent-v1"}
