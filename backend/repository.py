"""
OMISTOCK — Data Access Layer (DAL)
Toutes les opérations SQLAlchemy sont centralisées ici.
Les routeurs FastAPI ne doivent pas exécuter de requêtes directes.
"""

from typing import Any, Dict, List, Optional, Union

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models

# Types acceptés pour les données métier (dict ou schémas Pydantic)
DataDict = Union[Dict[str, Any], Any]


def _to_dict(data: DataDict) -> Dict[str, Any]:
    """Convertit un schéma Pydantic ou un dict en dictionnaire."""
    if isinstance(data, dict):
        return data
    if hasattr(data, "model_dump"):
        return data.model_dump(exclude_unset=True)
    if hasattr(data, "dict"):
        return data.dict(exclude_unset=True)
    raise TypeError("product_data / sale_data doit être un dict ou un schéma Pydantic")


# =============================================================================
# Produits
# =============================================================================

def get_products(
    db: Session,
    company_id: int,
    branch_id: Optional[int] = None,
    query: Optional[str] = None,
) -> List[models.Product]:
    q = db.query(models.Product).filter(models.Product.company_id == company_id)

    if branch_id is not None:
        q = q.join(models.Inventory).filter(models.Inventory.branch_id == branch_id)

    if query:
        pattern = f"%{query.strip()}%"
        q = q.filter(
            or_(
                models.Product.name.ilike(pattern),
                models.Product.sku.ilike(pattern),
                models.Product.barcode.ilike(pattern),
            )
        )

    return q.all()


def get_product_by_id(db: Session, product_id: int) -> Optional[models.Product]:
    return db.query(models.Product).filter(models.Product.id == product_id).first()


def get_product_by_id_for_company(
    db: Session, product_id: int, company_id: int
) -> Optional[models.Product]:
    return (
        db.query(models.Product)
        .filter(models.Product.id == product_id, models.Product.company_id == company_id)
        .first()
    )


def create_product(
    db: Session, product_data: DataDict, company_id: int
) -> models.Product:
    try:
        payload = _to_dict(product_data)
        db_product = models.Product(**payload, company_id=company_id)
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
        return db_product
    except Exception:
        db.rollback()
        raise


def update_product(
    db: Session, product_id: int, product_data: DataDict
) -> models.Product:
    try:
        db_product = get_product_by_id(db, product_id)
        if not db_product:
            raise ValueError(f"Produit {product_id} introuvable")

        update_data = _to_dict(product_data)
        branch_id = update_data.pop("branch_id", None)

        if branch_id is not None and "quantity" in update_data:
            inventory = (
                db.query(models.Inventory)
                .filter(
                    models.Inventory.product_id == product_id,
                    models.Inventory.branch_id == branch_id,
                )
                .first()
            )
            qty = update_data.pop("quantity")
            if inventory:
                inventory.quantity = qty
            else:
                db.add(
                    models.Inventory(
                        product_id=product_id,
                        branch_id=branch_id,
                        quantity=qty,
                        min_threshold=db_product.min_threshold,
                    )
                )
            db.flush()
            db_product.quantity = sum(inv.quantity for inv in db_product.inventory)

        for key, value in update_data.items():
            if hasattr(db_product, key):
                setattr(db_product, key, value)

        db.commit()
        db.refresh(db_product)
        return db_product
    except ValueError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def delete_product(db: Session, product_id: int) -> bool:
    try:
        db_product = get_product_by_id(db, product_id)
        if not db_product:
            raise ValueError(f"Produit {product_id} introuvable")
        db.delete(db_product)
        db.commit()
        return True
    except ValueError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def get_alerts(db: Session, company_id: int) -> List[models.Product]:
    return (
        db.query(models.Product)
        .filter(
            models.Product.company_id == company_id,
            models.Product.quantity <= models.Product.min_threshold,
        )
        .all()
    )


# =============================================================================
# Ventes & mouvements de stock
# =============================================================================

def get_sales(db: Session, company_id: int) -> List[models.Sale]:
    return db.query(models.Sale).filter(models.Sale.company_id == company_id).all()


def create_sale(
    db: Session, sale_data: DataDict, company_id: int, agent_id: int
) -> models.Sale:
    """
    Crée une vente, décrémente l'inventaire par filiale et enregistre les mouvements OUT.
    Transaction atomique : rollback en cas d'erreur ou de stock insuffisant.
    """
    try:
        data = _to_dict(sale_data)
        branch_id = data["branch_id"]
        items = data.get("items", [])
        customer_id = data.get("customer_id")

        db_sale = models.Sale(
            customer_id=customer_id,
            company_id=company_id,
            branch_id=branch_id,
            total_amount=0.0,
        )
        db.add(db_sale)
        db.flush()

        total_amount = 0.0

        for item in items:
            item_dict = _to_dict(item) if not isinstance(item, dict) else item
            product_id = item_dict["product_id"]
            quantity = item_dict["quantity"]
            unit_price = item_dict["unit_price"]

            inventory = (
                db.query(models.Inventory)
                .filter(
                    models.Inventory.product_id == product_id,
                    models.Inventory.branch_id == branch_id,
                )
                .first()
            )

            if not inventory or inventory.quantity < quantity:
                raise ValueError(
                    f"Stock insuffisant pour le produit {product_id} "
                    f"(disponible: {inventory.quantity if inventory else 0}, demandé: {quantity})"
                )

            inventory.quantity -= quantity

            item_total = quantity * unit_price
            total_amount += item_total

            db.add(
                models.SaleItem(
                    sale_id=db_sale.id,
                    product_id=product_id,
                    quantity=quantity,
                    unit_price=unit_price,
                )
            )

            db.add(
                models.StockMovement(
                    product_id=product_id,
                    branch_id=branch_id,
                    quantity=-quantity,
                    reason=f"Vente Web #{db_sale.id}",
                    company_id=company_id,
                    movement_type="OUT",
                )
            )

            product = get_product_by_id(db, product_id)
            if product and product.company_id == company_id:
                product.quantity = max(0, (product.quantity or 0) - quantity)

        db_sale.total_amount = total_amount
        db.commit()
        db.refresh(db_sale)
        return db_sale
    except ValueError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def get_movements(db: Session, company_id: int) -> List[models.StockMovement]:
    return (
        db.query(models.StockMovement)
        .filter(models.StockMovement.company_id == company_id)
        .order_by(models.StockMovement.created_at.desc())
        .all()
    )


# =============================================================================
# Transferts inter-dépôts
# =============================================================================

def get_transfer_requests(db: Session, company_id: int) -> List[models.TransferRequest]:
    return (
        db.query(models.TransferRequest)
        .filter(models.TransferRequest.company_id == company_id)
        .order_by(models.TransferRequest.created_at.desc())
        .all()
    )


def get_transfer_request_by_id(
    db: Session, transfer_id: int, company_id: Optional[int] = None
) -> Optional[models.TransferRequest]:
    q = db.query(models.TransferRequest).filter(models.TransferRequest.id == transfer_id)
    if company_id is not None:
        q = q.filter(models.TransferRequest.company_id == company_id)
    return q.first()


def create_transfer_request(
    db: Session, transfer_data: DataDict, from_branch_id: int
) -> models.TransferRequest:
    try:
        data = _to_dict(transfer_data)
        req = models.TransferRequest(
            product_id=data["product_id"],
            from_branch_id=from_branch_id,
            to_branch_id=data["to_branch_id"],
            quantity=data["quantity"],
            requester_id=data["requester_id"],
            company_id=data["company_id"],
            status=models.TransferStatus.PENDING.value,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return req
    except Exception:
        db.rollback()
        raise


def approve_transfer_request(
    db: Session, transfer_id: int, user_id: int
) -> models.TransferRequest:
    """
    Approuve un transfert : sortie du stock du dépôt source + mouvement OUT.
    """
    try:
        req = get_transfer_request_by_id(db, transfer_id)
        if not req:
            raise ValueError(f"Demande de transfert {transfer_id} introuvable")

        if req.status != models.TransferStatus.PENDING.value:
            raise ValueError("Statut invalide : la demande doit être en attente")

        from_inv = (
            db.query(models.Inventory)
            .filter(
                models.Inventory.product_id == req.product_id,
                models.Inventory.branch_id == req.from_branch_id,
            )
            .first()
        )

        if not from_inv or from_inv.quantity < req.quantity:
            raise ValueError("Stock insuffisant dans le dépôt source")

        from_inv.quantity -= req.quantity
        req.status = models.TransferStatus.APPROVED.value
        req.approver_id = user_id

        db.add(
            models.StockMovement(
                product_id=req.product_id,
                branch_id=req.from_branch_id,
                quantity=-req.quantity,
                reason="Transfert approuvé (sortie)",
                company_id=req.company_id,
                movement_type="OUT",
            )
        )

        product = get_product_by_id(db, req.product_id)
        if product:
            product.quantity = max(0, (product.quantity or 0) - req.quantity)

        db.commit()
        db.refresh(req)
        return req
    except ValueError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def confirm_transfer_request(
    db: Session, transfer_id: int, user_id: int
) -> models.TransferRequest:
    """
    Confirme un transfert : entrée du stock au dépôt destination + mouvement IN.
    """
    try:
        req = get_transfer_request_by_id(db, transfer_id)
        if not req:
            raise ValueError(f"Demande de transfert {transfer_id} introuvable")

        if req.status != models.TransferStatus.APPROVED.value:
            raise ValueError("Statut invalide : le transfert doit être approuvé")

        to_inv = (
            db.query(models.Inventory)
            .filter(
                models.Inventory.product_id == req.product_id,
                models.Inventory.branch_id == req.to_branch_id,
            )
            .first()
        )

        if to_inv:
            to_inv.quantity += req.quantity
        else:
            db.add(
                models.Inventory(
                    product_id=req.product_id,
                    branch_id=req.to_branch_id,
                    quantity=req.quantity,
                    min_threshold=5,
                )
            )

        req.status = models.TransferStatus.CONFIRMED.value
        req.approver_id = user_id

        db.add(
            models.StockMovement(
                product_id=req.product_id,
                branch_id=req.to_branch_id,
                quantity=req.quantity,
                reason="Transfert confirmé (entrée)",
                company_id=req.company_id,
                movement_type="IN",
            )
        )

        db.commit()
        db.refresh(req)
        return req
    except ValueError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


# =============================================================================
# Utilisateurs, filiales, fournisseurs, audit
# =============================================================================

def get_agents(db: Session, company_id: int) -> List[models.User]:
    return (
        db.query(models.User)
        .filter(
            models.User.company_id == company_id,
            models.User.user_type == "AGENT",
        )
        .all()
    )


def create_agent(
    db: Session, agent_data: DataDict, company_id: int
) -> models.User:
    try:
        data = _to_dict(agent_data)
        new_user = models.User(
            email=data["email"],
            hashed_password=data.get("hashed_password"),
            user_type=data.get("user_type", "AGENT"),
            api_key=data["api_key"],
            company_id=company_id,
            branch_id=data.get("branch_id"),
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except Exception:
        db.rollback()
        raise


def get_branches(db: Session, company_id: int) -> List[models.Branch]:
    return db.query(models.Branch).filter(models.Branch.company_id == company_id).all()


def get_suppliers(db: Session, company_id: int) -> List[models.Supplier]:
    return db.query(models.Supplier).filter(models.Supplier.company_id == company_id).all()


def get_audit_logs(db: Session, company_id: int) -> List[models.AuditLog]:
    logs = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.company_id == company_id)
        .order_by(models.AuditLog.timestamp.desc())
        .all()
    )
    for log in logs:
        user = db.query(models.User).filter(models.User.id == log.user_id).first()
        if user:
            log.user_email = user.email
            log.user_type = user.user_type
    return logs


def clean_database(db: Session) -> None:
    """Vide les tables métier (réinitialisation de test). Conserve users/companies/branches."""
    try:
        db.query(models.AuditLog).delete()
        db.query(models.ActivityLog).delete()
        db.query(models.StockMovement).delete()
        db.query(models.SaleItem).delete()
        db.query(models.Sale).delete()
        db.query(models.TransferRequest).delete()
        db.query(models.PurchaseOrderItem).delete()
        db.query(models.PurchaseOrder).delete()
        db.query(models.Customer).delete()
        db.query(models.Inventory).delete()
        db.query(models.Product).delete()
        db.query(models.Supplier).delete()
        db.commit()
    except Exception:
        db.rollback()
        raise
