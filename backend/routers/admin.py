from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from typing import List
import os
import csv
import io
import zipfile
from datetime import datetime

from backend import repository
import models
import schemas
import database
import seed_data
from dependencies import get_current_user
from database import get_db

router = APIRouter()


@router.post("/api/admin/seed")
def seed_database_route(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.user_type != "ADMIN":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    seed_data.seed()
    return {"status": "success", "message": "Base de données initialisée avec succès."}


@router.post("/api/admin/clean")
def clean_database_route(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.user_type != "ADMIN":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")
    try:
        repository.clean_database(db)
        return {"status": "success", "message": "Base de données nettoyée."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/admin/backup")
def get_backup(current_user: models.User = Depends(get_current_user)):
    if current_user.user_type != "ADMIN":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")

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


@router.get("/api/audit/export")
def export_logs(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.user_type != "ADMIN":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")

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
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return repository.get_audit_logs(db, current_user.company_id)


@router.post("/api/mcp/chat")
async def mcp_sandbox_chat(
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.user_type != "ADMIN":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs.")

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
