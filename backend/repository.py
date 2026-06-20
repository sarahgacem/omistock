"""
OMISTOCK — Data Access Layer (DAL)
Toutes les opérations SQLAlchemy métier sont centralisées ici.
Les routeurs FastAPI ne doivent pas exécuter de requêtes directes.

Règle d'or : l'INVENTAIRE par filiale (table Inventory) est la SEULE source de
vérité des quantités. `Product.quantity` n'est qu'un cache dérivé recalculé via
stock.recompute_product_quantity().
"""

from typing import Any, Dict, List, Optional, Union

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
import stock

DataDict = Union[Dict[str, Any], Any]


def _to_dict(data: DataDict) -> Dict[str, Any]:
    if isinstance(data, dict):
        return data
    if hasattr(data, "model_dump"):
        return data.model_dump(exclude_unset=True)
    if hasattr(data, "dict"):
        return data.dict(exclude_unset=True)
    raise TypeError("data doit être un dict ou un schéma Pydantic")


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


def create_product(db: Session, product_data: DataDict, company_id: int) -> models.Product:
    try:
        payload = _to_dict(product_data)
        # La quantité ne se définit jamais directement sur le produit : elle dérive
        # de l'inventaire. On retire la clé pour éviter d'écrire un cache incohérent.
        initial_qty = payload.pop("quantity", 0)
        branch_id = payload.pop("branch_id", None)
        db_product = models.Product(**payload, company_id=company_id)
        db.add(db_product)
        db.flush()
        if branch_id is not None and initial_qty:
            db.add(
                models.Inventory(
                    product_id=db_product.id,
                    branch_id=branch_id,
                    quantity=initial_qty,
                    min_threshold=db_product.min_threshold,
                )
            )
            db.flush()
        stock.recompute_product_quantity(db, db_product)
        db.commit()
        db.refresh(db_product)
        return db_product
    except Exception:
        db.rollback()
        raise


def update_product(db: Session, product_id: int, product_data: DataDict) -> models.Product:
    try:
        db_product = get_product_by_id(db, product_id)
        if not db_product:
            raise ValueError(f"Produit {product_id} introuvable")

        update_data = _to_dict(product_data)
        branch_id = update_data.pop("branch_id", None)

        if "quantity" in update_data:
            qty = update_data.pop("quantity")
            if branch_id is None:
                raise ValueError("La modification de quantité requiert un branch_id (stock par filiale).")
            inventory = (
                db.query(models.Inventory)
                .filter(
                    models.Inventory.product_id == product_id,
                    models.Inventory.branch_id == branch_id,
                )
                .first()
            )
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

        for key, value in update_data.items():
            if hasattr(db_product, key) and key not in ("id", "company_id", "quantity"):
                setattr(db_product, key, value)

        stock.recompute_product_quantity(db, db_product)
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


def get_alerts(db: Session, company_id: int, branch_id: Optional[int] = None) -> List[models.Product]:
    """Alertes basées sur l'inventaire réel et le point de commande (cf. stock.get_alerts)."""
    return stock.get_alerts(db, company_id, branch_id)


# =============================================================================
# Réapprovisionnement (réception) — WAC + lots
# =============================================================================

def restock_product(
    db: Session,
    *,
    product_id: int,
    branch_id: int,
    quantity: int,
    company_id: int,
    actor_id: int,
    unit_cost: float = 0.0,
    reason: str = "Réapprovisionnement",
    correlation_id: Optional[str] = None,
    lot_number: Optional[str] = None,
    expiry_date=None,
) -> models.StockMovement:
    """Réception de marchandise : met à jour l'inventaire, le WAC, le lot et trace le mouvement."""
    try:
        if quantity <= 0:
            raise ValueError("La quantité de réapprovisionnement doit être positive.")
        product = get_product_by_id_for_company(db, product_id, company_id)
        if not product:
            raise ValueError("Produit invalide.")

        # WAC mis à jour AVANT d'incrémenter la quantité agrégée.
        stock.apply_weighted_average_cost(product, quantity, unit_cost)

        inventory = (
            db.query(models.Inventory)
            .filter(
                models.Inventory.product_id == product_id,
                models.Inventory.branch_id == branch_id,
            )
            .first()
        )
        if inventory:
            inventory.quantity += quantity
        else:
            db.add(
                models.Inventory(
                    product_id=product_id,
                    branch_id=branch_id,
                    quantity=quantity,
                    min_threshold=product.min_threshold,
                )
            )

        if lot_number or expiry_date:
            db.add(
                models.Lot(
                    product_id=product_id,
                    branch_id=branch_id,
                    lot_number=lot_number or "N/A",
                    quantity=quantity,
                    expiry_date=expiry_date,
                    company_id=company_id,
                )
            )

        movement = models.StockMovement(
            product_id=product_id,
            branch_id=branch_id,
            quantity=quantity,
            reason=reason,
            company_id=company_id,
            movement_type="IN",
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
        db.add(movement)
        db.flush()
        stock.recompute_product_quantity(db, product)
        stock.refresh_demand_and_rop(db, product)
        db.commit()
        db.refresh(movement)
        return movement
    except ValueError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


# =============================================================================
# Ventes & mouvements de stock
# =============================================================================

def get_sales(db: Session, company_id: int) -> List[models.Sale]:
    return db.query(models.Sale).filter(models.Sale.company_id == company_id).all()


def get_sale_by_id(db: Session, sale_id: int, company_id: int) -> Optional[models.Sale]:
    return (
        db.query(models.Sale)
        .filter(models.Sale.id == sale_id, models.Sale.company_id == company_id)
        .first()
    )


def create_sale(
    db: Session, sale_data: DataDict, company_id: int, agent_id: int,
    correlation_id: Optional[str] = None,
) -> models.Sale:
    """Vente atomique : décrémente l'inventaire par filiale (FEFO), calcule le COGS, trace les mouvements."""
    try:
        data = _to_dict(sale_data)
        branch_id = data["branch_id"]
        items = data.get("items", [])
        customer_id = data.get("customer_id")
        if not items:
            raise ValueError("Une vente doit comporter au moins une ligne.")

        db_sale = models.Sale(
            customer_id=customer_id,
            company_id=company_id,
            branch_id=branch_id,
            total_amount=0.0,
            total_cost=0.0,
            actor_id=agent_id,
            status="CONFIRMED",
        )
        db.add(db_sale)
        db.flush()

        total_amount = 0.0
        total_cost = 0.0
        touched_products = []

        for item in items:
            item_dict = _to_dict(item) if not isinstance(item, dict) else item
            product_id = item_dict["product_id"]
            quantity = item_dict["quantity"]
            unit_price = item_dict["unit_price"]
            if quantity <= 0:
                raise ValueError("Quantité de vente invalide.")

            product = get_product_by_id_for_company(db, product_id, company_id)
            if not product:
                raise ValueError(f"Produit {product_id} introuvable pour cette entreprise.")

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
            stock.consume_lots_fefo(db, product_id, branch_id, quantity)

            unit_cost = product.cost_price or 0.0
            total_amount += quantity * unit_price
            total_cost += quantity * unit_cost

            db.add(
                models.SaleItem(
                    sale_id=db_sale.id,
                    product_id=product_id,
                    quantity=quantity,
                    unit_price=unit_price,
                    unit_cost=unit_cost,
                )
            )
            db.add(
                models.StockMovement(
                    product_id=product_id,
                    branch_id=branch_id,
                    quantity=-quantity,
                    reason=f"Vente #{db_sale.id}",
                    company_id=company_id,
                    movement_type="OUT",
                    actor_id=agent_id,
                    correlation_id=correlation_id,
                )
            )
            touched_products.append(product)

        db_sale.total_amount = round(total_amount, 2)
        db_sale.total_cost = round(total_cost, 2)
        db.flush()
        for p in touched_products:
            stock.recompute_product_quantity(db, p)
            stock.refresh_demand_and_rop(db, p)
        db.commit()
        db.refresh(db_sale)
        return db_sale
    except ValueError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def reverse_sale(
    db: Session, sale_id: int, company_id: int, actor_id: int,
    correlation_id: Optional[str] = None,
) -> models.Sale:
    """
    Rollback au niveau action : annule une vente confirmée via des mouvements de
    compensation (réintègre le stock) sans supprimer l'historique.
    """
    try:
        sale = get_sale_by_id(db, sale_id, company_id)
        if not sale:
            raise ValueError("Vente introuvable.")
        if sale.status == "REVERSED":
            raise ValueError("Cette vente a déjà été annulée.")

        for item in sale.items:
            inventory = (
                db.query(models.Inventory)
                .filter(
                    models.Inventory.product_id == item.product_id,
                    models.Inventory.branch_id == sale.branch_id,
                )
                .first()
            )
            if inventory:
                inventory.quantity += item.quantity
            else:
                db.add(
                    models.Inventory(
                        product_id=item.product_id,
                        branch_id=sale.branch_id,
                        quantity=item.quantity,
                        min_threshold=5,
                    )
                )
            db.add(
                models.StockMovement(
                    product_id=item.product_id,
                    branch_id=sale.branch_id,
                    quantity=item.quantity,
                    reason=f"Annulation vente #{sale.id} (compensation)",
                    company_id=company_id,
                    movement_type="IN",
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                )
            )
            product = get_product_by_id(db, item.product_id)
            if product:
                db.flush()
                stock.recompute_product_quantity(db, product)

        sale.status = "REVERSED"
        db.commit()
        db.refresh(sale)
        return sale
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
            origin=data.get("origin", "HUMAIN"),
            status=models.TransferStatus.PENDING.value,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return req
    except Exception:
        db.rollback()
        raise


def approve_transfer_request(db: Session, transfer_id: int, user_id: int) -> models.TransferRequest:
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
                actor_id=user_id,
            )
        )
        product = get_product_by_id(db, req.product_id)
        if product:
            db.flush()
            stock.recompute_product_quantity(db, product)
        db.commit()
        db.refresh(req)
        return req
    except ValueError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def confirm_transfer_request(db: Session, transfer_id: int, user_id: int) -> models.TransferRequest:
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
                actor_id=user_id,
            )
        )
        product = get_product_by_id(db, req.product_id)
        if product:
            db.flush()
            stock.recompute_product_quantity(db, product)
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
# Utilisateurs, filiales, fournisseurs, audit, propositions agents
# =============================================================================

def get_agents(db: Session, company_id: int) -> List[models.User]:
    return (
        db.query(models.User)
        .filter(models.User.company_id == company_id, models.User.user_type == "AGENT")
        .all()
    )


def create_agent(db: Session, agent_data: DataDict, company_id: int) -> models.User:
    try:
        data = _to_dict(agent_data)
        new_user = models.User(
            email=data["email"],
            hashed_password=data.get("hashed_password"),
            user_type=data.get("user_type", "AGENT"),
            api_key=data["api_key"],
            company_id=company_id,
            branch_id=data.get("branch_id"),
            autonomy_level=data.get("autonomy_level", models.AutonomyLevel.READ_ONLY.value),
            agent_scopes=data.get("agent_scopes"),
            api_key_expires_at=data.get("api_key_expires_at"),
            max_action_quantity=data.get("max_action_quantity", 0),
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


def create_agent_proposal(
    db: Session, *, agent_id: int, company_id: int, action_type: str,
    payload: str, rationale: str, correlation_id: str,
) -> models.AgentProposal:
    prop = models.AgentProposal(
        agent_id=agent_id,
        company_id=company_id,
        action_type=action_type,
        payload=payload,
        rationale=rationale,
        correlation_id=correlation_id,
        status="PENDING",
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


def get_agent_proposals(db: Session, company_id: int, status: Optional[str] = None) -> List[models.AgentProposal]:
    q = db.query(models.AgentProposal).filter(models.AgentProposal.company_id == company_id)
    if status:
        q = q.filter(models.AgentProposal.status == status)
    return q.order_by(models.AgentProposal.created_at.desc()).all()


def get_proposal_by_id(db: Session, proposal_id: int, company_id: int) -> Optional[models.AgentProposal]:
    return (
        db.query(models.AgentProposal)
        .filter(models.AgentProposal.id == proposal_id, models.AgentProposal.company_id == company_id)
        .first()
    )


def clean_database(db: Session) -> None:
    """Vide les tables métier (réinitialisation de test). Conserve users/companies/branches."""
    try:
        db.query(models.AuditLog).delete()
        db.query(models.ActivityLog).delete()
        db.query(models.AgentProposal).delete()
        db.query(models.StockMovement).delete()
        db.query(models.SaleItem).delete()
        db.query(models.Sale).delete()
        db.query(models.TransferRequest).delete()
        db.query(models.PurchaseOrderItem).delete()
        db.query(models.PurchaseOrder).delete()
        db.query(models.Customer).delete()
        db.query(models.Lot).delete()
        db.query(models.Inventory).delete()
        db.query(models.Product).delete()
        db.query(models.Supplier).delete()
        db.commit()
    except Exception:
        db.rollback()
        raise


# =============================================================================
# Inventaire physique / Cycle counting (théorie de gestion de stock)
# =============================================================================

def adjust_inventory(
    db: Session,
    *,
    product_id: int,
    branch_id: int,
    counted_quantity: int,
    company_id: int,
    actor_id: int,
    reason: str = "Comptage physique (cycle count)",
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ajustement d'inventaire suite à un comptage physique (cycle count).

    Best practice de gestion de stock : le stock système doit régulièrement être
    réconcilié avec le stock physique réel. Cette fonction :
      - lit le stock système courant (source de vérité = Inventory) ;
      - calcule la VARIANCE = stock_compté - stock_système ;
      - aligne l'inventaire sur la quantité comptée ;
      - trace un mouvement de type 'ADJUST' (positif ou négatif) avec acteur + corrélation ;
      - recalcule le cache `Product.quantity`.

    Retourne {system_before, counted, variance, movement_id}. La quantité comptée
    ne peut pas être négative ; la variance, elle, peut l'être (perte/casse/vol).
    """
    try:
        if counted_quantity < 0:
            raise ValueError("La quantité comptée ne peut pas être négative.")
        product = get_product_by_id_for_company(db, product_id, company_id)
        if not product:
            raise ValueError("Produit invalide.")

        inventory = (
            db.query(models.Inventory)
            .filter(
                models.Inventory.product_id == product_id,
                models.Inventory.branch_id == branch_id,
            )
            .first()
        )
        system_before = inventory.quantity if inventory else 0
        variance = counted_quantity - system_before

        if variance == 0:
            # Pas d'écart : aucune mutation, mais on retourne l'état (no-op auditable côté routeur).
            return {
                "system_before": system_before,
                "counted": counted_quantity,
                "variance": 0,
                "movement_id": None,
            }

        if inventory:
            inventory.quantity = counted_quantity
        else:
            db.add(
                models.Inventory(
                    product_id=product_id,
                    branch_id=branch_id,
                    quantity=counted_quantity,
                    min_threshold=product.min_threshold,
                )
            )

        movement = models.StockMovement(
            product_id=product_id,
            branch_id=branch_id,
            quantity=variance,  # signé : + = excédent trouvé, - = manquant
            reason=reason,
            company_id=company_id,
            movement_type="ADJUST",
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
        db.add(movement)
        db.flush()
        stock.recompute_product_quantity(db, product)
        db.commit()
        db.refresh(movement)
        return {
            "system_before": system_before,
            "counted": counted_quantity,
            "variance": variance,
            "movement_id": movement.id,
        }
    except ValueError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
