from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
import models, schemas, database, seed_data
from dependencies import get_current_user
from database import get_db
import os, shutil, csv, io
from datetime import datetime
from typing import List

router = APIRouter()

@router.post("/api/admin/seed")
def seed_database_route(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.user_type != "ADMIN":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    seed_data.seed()
    return {"status": "success", "message": "Base de données initialisée avec succès."}

@router.post("/api/admin/clean")
def clean_database_route(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.user_type != "ADMIN":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    try:
        db.query(models.AuditLog).delete()
        db.query(models.StockMovement).delete()
        db.query(models.SaleItem).delete()
        db.query(models.Sale).delete()
        db.query(models.TransferRequest).delete()
        db.query(models.Customer).delete()
        db.query(models.Inventory).delete()
        db.query(models.Product).delete()
        db.query(models.Supplier).delete()
        db.commit()
        return {"status": "success", "message": "Base de données nettoyée."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/admin/backup")
def get_backup(current_user: models.User = Depends(get_current_user)):
    if current_user.user_type != "ADMIN":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    
    db_path = database.db_path
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Fichier base de données introuvable.")
    
    import zipfile
    date_str = datetime.now().strftime("%Y_%m_%d")
    zip_filename = f"backup_omistock_{date_str}.zip"
    zip_path = os.path.join(os.path.dirname(db_path), zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(db_path, arcname=f"omistock_backup_{date_str}.db")
    
    return FileResponse(
        path=zip_path,
        filename=zip_filename,
        media_type='application/zip'
    )

@router.get("/api/audit/export")
def export_logs(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.user_type != "ADMIN":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    
    logs = db.query(models.AuditLog).filter(models.AuditLog.company_id == current_user.company_id).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Timestamp", "User_ID", "Action", "Old Value", "New Value"])
    
    for log in logs:
        writer.writerow([log.id, log.timestamp, log.user_id, log.action, log.old_value, log.new_value])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=logs_activite.csv"}
    )

@router.get("/api/audit_logs", response_model=List[schemas.AuditLogResponse])
def get_audit_logs(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Re-implemented here for modularity
    logs = db.query(models.AuditLog).filter(models.AuditLog.company_id == current_user.company_id).order_by(models.AuditLog.timestamp.desc()).all()
    for log in logs:
        user = db.query(models.User).filter(models.User.id == log.user_id).first()
        if user:
            log.user_email = user.email
            log.user_type = user.user_type
    return logs

@router.post("/api/mcp/chat")
async def mcp_sandbox_chat(data: dict, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.user_type != "ADMIN":
         raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    
    user_msg = data.get("message", "").lower()
    
    # Simple logic to simulate MCP tools
    if "stock" in user_msg or "alerte" in user_msg:
        from routers.products import get_alerts
        alerts = get_alerts(current_user, db)
        if not alerts:
            reply = "L'analyse MCP indique que tout est en ordre. Aucun produit n'est en alerte de stock actuellement."
        else:
            reply = f"L'agent IA a détecté {len(alerts)} produits en alerte critique. Une commande de réapprovisionnement est suggérée pour : " + ", ".join([p.name for p in alerts[:3]])
    elif "ventes" in user_msg or "ca" in user_msg or "résumé" in user_msg:
        reply = "Résumé Business : Le CA est stable. On observe une hausse de 12% sur les produits de la catégorie Pharma cette semaine. L'agent suggère d'augmenter le stock d'Amoxicilline."
    else:
        reply = f"Message reçu par l'Agent IA Omistock : '{user_msg}'. Je suis connecté à la base de données et prêt à analyser vos stocks ou vos ventes. Que puis-je faire pour vous ?"
    
    return {"response": reply, "agent": "Omistock-MCP-Agent-v1"}

from typing import List
