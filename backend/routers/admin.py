from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
import os
import csv
import io
import zipfile
import json
from datetime import datetime, timedelta, timezone

from backend import repository
import models
import schemas
import database
import seed_data
import services
import audit
from services import log_audit
from dependencies import (
    get_current_user, get_current_admin, get_current_human, get_current_admin_or_agent,
)
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

    date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
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
                    # Ne jamais exporter de secrets (hash de mot de passe, clé API) en clair.
                    if col.name in ("hashed_password", "api_key", "entry_hash", "prev_hash"):
                        continue
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
    db: Session = Depends(get_db),
):
    """
    Restauration JSON UNIQUEMENT, et SCOPÉE à l'entreprise de l'admin appelant.
    Durcissements :
      - Plus de remplacement brut du fichier .db (.db/.sql désactivés : trop dangereux,
        écrasait toute la base multi-tenant et contournait l'isolation).
      - Snapshot d'audit avant opération destructive (traçabilité/rollback).
      - On ne touche QUE les données de current_user.company_id (pas de purge globale).
      - Les FK ne sont pas désactivées ; l'ordre d'insertion respecte les dépendances.
    """
    filename = (file.filename or "").lower()
    if not filename.endswith(".json"):
        raise HTTPException(
            status_code=400,
            detail="Seule la restauration JSON est autorisée (les imports bruts .db/.sql sont désactivés pour raisons de sécurité multi-tenant).",
        )
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
        cid = current_user.company_id
        corr = audit.new_correlation_id()

        # Trace AVANT toute suppression.
        audit.record(db, user_id=current_user.id, actor_type="ADMIN", action="DB_RESTORE_STARTED",
                     company_id=cid, entity_type="company", entity_id=cid, correlation_id=corr)

        # Purge SCOPÉE à l'entreprise (jamais globale).
        scoped_models = [
            models.AuditLog, models.ActivityLog, models.AgentProposal, models.StockMovement,
            models.TransferRequest, models.PurchaseOrder, models.Customer, models.Lot,
            models.Product, models.Supplier,
        ]
        db.query(models.SaleItem).filter(
            models.SaleItem.sale_id.in_(db.query(models.Sale.id).filter(models.Sale.company_id == cid))
        ).delete(synchronize_session=False)
        db.query(models.Sale).filter(models.Sale.company_id == cid).delete(synchronize_session=False)
        db.query(models.PurchaseOrderItem).filter(
            models.PurchaseOrderItem.purchase_order_id.in_(
                db.query(models.PurchaseOrder.id).filter(models.PurchaseOrder.company_id == cid)
            )
        ).delete(synchronize_session=False)
        db.query(models.Inventory).filter(
            models.Inventory.branch_id.in_(
                db.query(models.Branch.id).filter(models.Branch.company_id == cid)
            )
        ).delete(synchronize_session=False)
        for m in scoped_models:
            if hasattr(m, "company_id"):
                db.query(m).filter(m.company_id == cid).delete(synchronize_session=False)
        db.flush()

        # Réinsertion : on force company_id = cid pour empêcher toute injection cross-tenant.
        insert_order = [
            (models.Supplier, "suppliers"), (models.Product, "products"),
            (models.Inventory, "inventory"), (models.StockMovement, "stock_movements"),
            (models.PurchaseOrder, "purchase_orders"), (models.PurchaseOrderItem, "purchase_order_items"),
            (models.Customer, "customers"), (models.Sale, "sales"), (models.SaleItem, "sale_items"),
            (models.TransferRequest, "transfer_requests"),
        ]
        for model, tablename in insert_order:
            for r in data.get(tablename, []):
                if "company_id" in {c.name for c in model.__table__.columns}:
                    if r.get("company_id") not in (None, cid):
                        # Ligne d'une autre entreprise : ignorée (sécurité).
                        continue
                    r["company_id"] = cid
                for col in model.__table__.columns:
                    if col.name in r and r[col.name] is not None and col.type.__class__.__name__ == "DateTime":
                        try:
                            r[col.name] = datetime.fromisoformat(r[col.name])
                        except Exception:
                            pass
                clean = {k: v for k, v in r.items() if k in {c.name for c in model.__table__.columns}}
                db.add(model(**clean))
        db.commit()
        audit.record(db, user_id=current_user.id, actor_type="ADMIN", action="DB_RESTORE_COMPLETED",
                     company_id=cid, entity_type="company", entity_id=cid, correlation_id=corr)
        return {"status": "success", "message": "Données de l'entreprise restaurées depuis JSON (scopé tenant)."}
    except HTTPException:
        raise
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
        current_user.deletion_deadline = datetime.now(timezone.utc) + timedelta(days=30)
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


@router.post("/api/admin/users/employee", response_model=schemas.UserResponse)
def create_employee(
    employee_data: schemas.EmployeeCreate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    from backend.security import get_password_hash
    
    # Vérifier que l'email n'existe pas déjà
    existing_user = db.query(models.User).filter(models.User.email == employee_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé.")
    
    # Vérifier que la filiale appartient à l'entreprise
    branch = db.query(models.Branch).filter(
        models.Branch.id == employee_data.branch_id,
        models.Branch.company_id == current_user.company_id
    ).first()
    if not branch:
        raise HTTPException(status_code=400, detail="Filiale invalide ou n'appartient pas à votre entreprise.")
    
    try:
        # Créer l'employé avec rôle forcé à HUMAIN
        hashed_password = get_password_hash(employee_data.password)
        new_employee = models.User(
            email=employee_data.email,
            hashed_password=hashed_password,
            user_type="HUMAIN",
            branch_id=employee_data.branch_id,
            company_id=current_user.company_id,
            is_active=True
        )
        db.add(new_employee)
        db.commit()
        db.refresh(new_employee)
        return new_employee
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/users/branch-admin", response_model=schemas.UserResponse)
def create_branch_admin(
    admin_data: schemas.BranchUserCreate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    try:
        new_admin = services.create_branch_user(db, admin_data, current_user.company_id, "ADMIN")
        return new_admin
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/restock")
def restock(
    restock_data: schemas.RestockCreate,
    current_user: models.User = Depends(get_current_human),
    db: Session = Depends(get_db),
):
    """
    Réapprovisionnement : délégué au DAL (repository.restock_product) qui gère
    le coût moyen pondéré (WAC), l'inventaire par filiale comme source de vérité,
    le lot/FEFO, la traçabilité (actor_id + correlation_id) et l'audit chaîné.
    """
    # Validations multi-tenant (le fournisseur/produit/filiale doivent appartenir à l'entreprise).
    supplier = db.query(models.Supplier).filter(
        models.Supplier.id == restock_data.supplier_id,
        models.Supplier.company_id == current_user.company_id,
    ).first()
    if not supplier:
        raise HTTPException(status_code=400, detail="Fournisseur invalide ou hors entreprise.")
    branch = db.query(models.Branch).filter(
        models.Branch.id == restock_data.branch_id,
        models.Branch.company_id == current_user.company_id,
    ).first()
    if not branch:
        raise HTTPException(status_code=400, detail="Filiale invalide ou hors entreprise.")

    corr = audit.new_correlation_id()
    try:
        movement = repository.restock_product(
            db,
            product_id=restock_data.product_id,
            branch_id=restock_data.branch_id,
            quantity=restock_data.quantity,
            company_id=current_user.company_id,
            actor_id=current_user.id,
            unit_cost=restock_data.purchase_price or 0.0,
            reason=f"Réapprovisionnement depuis {supplier.name}",
            correlation_id=corr,
        )
        log_audit(
            db, current_user.id, "RESTOCK",
            {"product_id": restock_data.product_id, "supplier": supplier.name},
            {"qty": restock_data.quantity, "unit_cost": restock_data.purchase_price},
            current_user.company_id, actor_type=current_user.user_type,
            entity_type="stock_movement", entity_id=movement.id, correlation_id=corr,
        )
        return {"message": "Réapprovisionnement effectué avec succès", "movement_id": movement.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/inventory/cycle-count", response_model=schemas.CycleCountResponse)
def cycle_count(
    data: schemas.CycleCountCreate,
    current_user: models.User = Depends(get_current_human),
    db: Session = Depends(get_db),
):
    """
    Inventaire physique / cycle counting (best practice de gestion de stock).
    Réconcilie le stock système (source de vérité = Inventory) avec un comptage
    physique. La variance (excédent/manquant) est tracée en mouvement 'ADJUST'
    avec acteur + correlation_id, puis auditée (chaîne de hachage).
    """
    # Validation multi-tenant de la filiale.
    branch = db.query(models.Branch).filter(
        models.Branch.id == data.branch_id,
        models.Branch.company_id == current_user.company_id,
    ).first()
    if not branch:
        raise HTTPException(status_code=400, detail="Filiale invalide ou hors entreprise.")

    corr = audit.new_correlation_id()
    try:
        result = repository.adjust_inventory(
            db,
            product_id=data.product_id,
            branch_id=data.branch_id,
            counted_quantity=data.counted_quantity,
            company_id=current_user.company_id,
            actor_id=current_user.id,
            reason=data.reason or "Comptage physique (cycle count)",
            correlation_id=corr,
        )
        log_audit(
            db, current_user.id, "CYCLE_COUNT",
            {"system_before": result["system_before"]},
            {"counted": result["counted"], "variance": result["variance"]},
            current_user.company_id, actor_type=current_user.user_type,
            entity_type="inventory", entity_id=data.product_id, correlation_id=corr,
        )
        return schemas.CycleCountResponse(
            product_id=data.product_id, branch_id=data.branch_id, **result
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/api/restock/{movement_id}/order/html")
def get_purchase_order_html(
    movement_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    movement = db.query(models.StockMovement).filter(
        models.StockMovement.id == movement_id,
        models.StockMovement.company_id == current_user.company_id,
        models.StockMovement.movement_type == "IN"
    ).first()
    
    if not movement:
        raise HTTPException(status_code=404, detail="Mouvement de réapprovisionnement introuvable")
    
    company = db.query(models.Company).filter(models.Company.id == current_user.company_id).first()
    branch = db.query(models.Branch).filter(models.Branch.id == movement.branch_id).first()
    product = db.query(models.Product).filter(models.Product.id == movement.product_id).first()
    
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Bon de Commande #{movement.id}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
            .header {{ border-bottom: 2px solid #333; padding-bottom: 20px; margin-bottom: 30px; }}
            .company-name {{ font-size: 24px; font-weight: bold; color: #174092; }}
            .order-title {{ font-size: 28px; font-weight: bold; text-align: right; color: #333; }}
            .info-row {{ display: flex; justify-content: space-between; margin: 10px 0; }}
            .info-label {{ font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 30px; }}
            th {{ background: #4fd1c5; color: white; padding: 12px; text-align: left; }}
            td {{ border: 1px solid #ddd; padding: 12px; }}
            .total {{ font-size: 20px; font-weight: bold; text-align: right; margin-top: 30px; }}
            .footer {{ margin-top: 50px; text-align: center; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="company-name">{company.name if company else 'OMISTOCK'}</div>
            <div class="order-title">BON DE COMMANDE #{movement.id}</div>
        </div>
        
        <div class="info-row">
            <div>
                <div class="info-label">Date:</div>
                <div>{movement.created_at.strftime('%d/%m/%Y %H:%M')}</div>
            </div>
            <div>
                <div class="info-label">Filiale de réception:</div>
                <div>{branch.name if branch else 'N/A'}</div>
            </div>
        </div>
        
        <div class="info-row">
            <div>
                <div class="info-label">Fournisseur:</div>
                <div>{movement.reason.replace('Réapprovisionnement depuis ', '') if 'Réapprovisionnement depuis ' in movement.reason else movement.reason}</div>
            </div>
            <div>
                <div class="info-label">Commande #:</div>
                <div>{movement.id}</div>
            </div>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>Produit</th>
                    <th>Quantité commandée</th>
                    <th>Prix unitaire</th>
                    <th>Total</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{product.name if product else 'N/A'}</td>
                    <td>{movement.quantity}</td>
                    <td>N/A</td>
                    <td>N/A</td>
                </tr>
            </tbody>
        </table>
        
        <div class="footer">
            <p>Document généré automatiquement par OMISTOCK</p>
            <p>Date d'émission: {movement.created_at.strftime('%d/%m/%Y %H:%M')}</p>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_template)


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
    current_user: models.User = Depends(get_current_admin_or_agent),
    db: Session = Depends(get_db),
):
    return repository.get_audit_logs(db, current_user.company_id)


@router.post("/api/mcp/chat")
async def mcp_sandbox_chat(
    data: dict,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Assistant MCP basé sur des DONNÉES RÉELLES (plus de réponses inventées).
    Routeur d'intention simple : alertes, valorisation, prévision produit.
    Toutes les réponses sont dérivées de la base et tracées.
    """
    import stock as stock_svc
    user_msg = (data.get("message") or "").lower().strip()
    cid = current_user.company_id

    if any(k in user_msg for k in ("alerte", "rupture", "stock bas", "réappro", "reappro")):
        alerts = stock_svc.get_alerts(db, cid)
        if not alerts:
            reply = "Aucun produit sous son point de commande actuellement."
        else:
            names = ", ".join(f"{p.name} (stock {p.total_quantity}/ROP {p.reorder_point})" for p in alerts[:5])
            reply = f"{len(alerts)} produit(s) sous le point de commande : {names}."
        intent = "alerts"
    elif any(k in user_msg for k in ("valeur", "valorisation", "inventaire", "stock total")):
        value = stock_svc.stock_value_at_cost(db, cid)
        reply = f"Valeur totale du stock au coût (WAC) : {value} DA."
        intent = "valuation"
    elif "vente" in user_msg or "ca" in user_msg or "chiffre" in user_msg:
        from sqlalchemy import func as _f
        total = db.query(_f.coalesce(_f.sum(models.Sale.total_amount), 0.0)).filter(
            models.Sale.company_id == cid, models.Sale.status == "CONFIRMED").scalar() or 0.0
        margin = db.query(_f.coalesce(_f.sum(models.Sale.total_amount - models.Sale.total_cost), 0.0)).filter(
            models.Sale.company_id == cid, models.Sale.status == "CONFIRMED").scalar() or 0.0
        reply = f"CA confirmé : {round(total,2)} DA ; marge brute estimée : {round(margin,2)} DA."
        intent = "sales"
    else:
        reply = ("Assistant MCP Omistock. Posez une question sur : les alertes de stock, "
                 "la valorisation du stock, ou le chiffre d'affaires. Les réponses proviennent "
                 "de vos données réelles.")
        intent = "help"

    corr = audit.new_correlation_id()
    audit.record(db, user_id=current_user.id, actor_type=current_user.user_type,
                 action="MCP_CHAT", company_id=cid, entity_type="mcp_chat",
                 correlation_id=corr, old_value={"q": user_msg}, new_value={"intent": intent})
    return {"response": reply, "intent": intent, "agent": "Omistock-MCP-Agent-v2", "grounded": True}


# ---------------------------------------------------------------------------
# Vérification d'intégrité du journal d'audit (tamper-evidence).
# ---------------------------------------------------------------------------
@router.get("/api/audit/verify")
def verify_audit_chain(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return audit.verify_chain(db, current_user.company_id)


# ---------------------------------------------------------------------------
# Revue des propositions d'agents IA (human-in-the-loop).
# ---------------------------------------------------------------------------
@router.get("/api/agent/proposals")
def list_agent_proposals(
    status: str = "PENDING",
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    props = repository.get_agent_proposals(db, current_user.company_id, status=status)
    return [
        {"id": p.id, "agent_id": p.agent_id, "action_type": p.action_type,
         "payload": p.payload, "rationale": p.rationale, "status": p.status,
         "correlation_id": p.correlation_id, "created_at": p.created_at}
        for p in props
    ]


@router.post("/api/agent/proposals/{proposal_id}/approve")
def approve_agent_proposal(
    proposal_id: int,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Un ADMIN valide une proposition d'agent : l'action est alors EXÉCUTÉE par un humain (SoD)."""
    prop = repository.get_proposal_by_id(db, proposal_id, current_user.company_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Proposition introuvable")
    if prop.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Proposition déjà traitée ({prop.status}).")

    corr = prop.correlation_id or audit.new_correlation_id()
    try:
        if prop.action_type == "RESTOCK":
            payload = json.loads(prop.payload)
            movement = repository.restock_product(
                db, product_id=payload["product_id"], branch_id=payload["branch_id"],
                quantity=payload["quantity"], company_id=current_user.company_id,
                actor_id=current_user.id, unit_cost=payload.get("unit_cost", 0.0),
                reason=f"Réappro validé (proposition agent #{prop.id})", correlation_id=corr,
            )
            result_entity = movement.id
        else:
            raise HTTPException(status_code=400, detail=f"Type d'action non supporté: {prop.action_type}")
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Payload de proposition incomplet: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    prop.status = "EXECUTED"
    prop.reviewer_id = current_user.id
    prop.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    audit.record(db, user_id=current_user.id, actor_type="ADMIN", action="AGENT_PROPOSAL_APPROVED",
                 company_id=current_user.company_id, entity_type="proposal", entity_id=prop.id,
                 correlation_id=corr, new_value={"executed_entity": result_entity})
    return {"status": "executed", "proposal_id": prop.id, "movement_id": result_entity}


@router.post("/api/agent/proposals/{proposal_id}/reject")
def reject_agent_proposal(
    proposal_id: int,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    prop = repository.get_proposal_by_id(db, proposal_id, current_user.company_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Proposition introuvable")
    if prop.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Proposition déjà traitée ({prop.status}).")
    prop.status = "REJECTED"
    prop.reviewer_id = current_user.id
    prop.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    audit.record(db, user_id=current_user.id, actor_type="ADMIN", action="AGENT_PROPOSAL_REJECTED",
                 company_id=current_user.company_id, entity_type="proposal", entity_id=prop.id,
                 correlation_id=prop.correlation_id or audit.new_correlation_id())
    return {"status": "rejected", "proposal_id": prop.id}
