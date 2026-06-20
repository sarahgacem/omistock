"""
OMISTOCK — Service de gestion de stock (théorie / best practices).

Implémente :
- Source de vérité unique : la quantité totale d'un produit est dérivée de Inventory.
- Coût moyen pondéré (WAC) recalculé à chaque réception.
- Demande moyenne journalière calculée depuis l'historique des ventes.
- Point de commande (ROP) = demande * délai + stock de sécurité.
- Quantité économique de commande (EOQ / formule de Wilson).
- Valorisation du stock au coût (et non au prix de vente).
- Détection d'alertes basée sur l'inventaire réel (par filiale et global).
"""
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import models


def recompute_product_quantity(db: Session, product: models.Product) -> int:
    """Recalcule et persiste la quantité agrégée à partir des inventaires (cache dérivé)."""
    total = (
        db.query(func.coalesce(func.sum(models.Inventory.quantity), 0))
        .filter(models.Inventory.product_id == product.id)
        .scalar()
        or 0
    )
    product.quantity = int(total)
    return product.quantity


def apply_weighted_average_cost(
    product: models.Product, incoming_qty: int, incoming_unit_cost: float
) -> float:
    """
    Met à jour le coût moyen pondéré (WAC) du produit lors d'une réception.
    WAC = (stock_actuel * coût_actuel + qté_reçue * coût_reçu) / (stock_actuel + qté_reçue)
    """
    current_qty = product.quantity or 0
    current_cost = product.cost_price or 0.0
    if incoming_qty <= 0:
        return current_cost
    if incoming_unit_cost is None or incoming_unit_cost <= 0:
        # Pas de coût fourni : on conserve le WAC existant.
        return current_cost
    new_total = current_qty + incoming_qty
    if new_total <= 0:
        return current_cost
    wac = (current_qty * current_cost + incoming_qty * incoming_unit_cost) / new_total
    product.cost_price = round(wac, 4)
    return product.cost_price


def compute_avg_daily_demand(
    db: Session, product_id: int, company_id: int, window_days: int = 30
) -> float:
    """Demande moyenne journalière sur une fenêtre glissante (ventes confirmées)."""
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    total = (
        db.query(func.coalesce(func.sum(models.SaleItem.quantity), 0))
        .join(models.Sale, models.SaleItem.sale_id == models.Sale.id)
        .filter(
            models.SaleItem.product_id == product_id,
            models.Sale.company_id == company_id,
            models.Sale.status == "CONFIRMED",
            models.Sale.date >= since,
        )
        .scalar()
        or 0
    )
    return round(float(total) / float(window_days), 4)


def refresh_demand_and_rop(
    db: Session, product: models.Product, window_days: int = 30
) -> None:
    """Recalcule la demande moyenne du produit (le ROP est dérivé via la property)."""
    product.avg_daily_demand = compute_avg_daily_demand(
        db, product.id, product.company_id, window_days
    )


def economic_order_quantity(
    annual_demand: float, ordering_cost: float, holding_cost_per_unit: float
) -> Optional[float]:
    """EOQ (formule de Wilson). Retourne None si paramètres invalides."""
    if annual_demand <= 0 or ordering_cost <= 0 or holding_cost_per_unit <= 0:
        return None
    return round(math.sqrt((2 * annual_demand * ordering_cost) / holding_cost_per_unit), 2)


def stock_value_at_cost(db: Session, company_id: int, branch_id: Optional[int] = None) -> float:
    """Valorisation du stock AU COÛT (WAC), pas au prix de vente."""
    q = (
        db.query(
            func.coalesce(
                func.sum(models.Inventory.quantity * models.Product.cost_price), 0.0
            )
        )
        .join(models.Product, models.Inventory.product_id == models.Product.id)
        .filter(models.Product.company_id == company_id)
    )
    if branch_id is not None:
        q = q.filter(models.Inventory.branch_id == branch_id)
    return round(float(q.scalar() or 0.0), 2)


def get_alerts(
    db: Session, company_id: int, branch_id: Optional[int] = None
) -> List[models.Product]:
    """
    Alertes basées sur l'INVENTAIRE RÉEL (source de vérité) :
    un produit est en alerte si son stock disponible <= point de commande (ROP).
    """
    products = db.query(models.Product).filter(models.Product.company_id == company_id).all()
    alerts = []
    for p in products:
        if branch_id is not None:
            on_hand = sum(
                (inv.quantity or 0) for inv in p.inventory if inv.branch_id == branch_id
            )
        else:
            on_hand = p.total_quantity
        if on_hand <= p.reorder_point:
            alerts.append(p)
    return alerts


def expiring_lots(
    db: Session, company_id: int, within_days: int = 30
) -> List[models.Lot]:
    """Lots dont la péremption approche (gestion FEFO)."""
    horizon = datetime.now(timezone.utc) + timedelta(days=within_days)
    return (
        db.query(models.Lot)
        .filter(
            models.Lot.company_id == company_id,
            models.Lot.quantity > 0,
            models.Lot.expiry_date != None,  # noqa: E711
            models.Lot.expiry_date <= horizon,
        )
        .order_by(models.Lot.expiry_date.asc())
        .all()
    )


def consume_lots_fefo(
    db: Session, product_id: int, branch_id: int, quantity: int
) -> List[Dict]:
    """
    Décrémente les lots en FEFO (First Expired First Out) lors d'une sortie.
    Best-effort : si aucun lot n'est suivi pour ce produit, ne fait rien.
    Retourne la liste des prélèvements {lot_id, qty}.
    """
    remaining = quantity
    picks = []
    lots = (
        db.query(models.Lot)
        .filter(
            models.Lot.product_id == product_id,
            models.Lot.branch_id == branch_id,
            models.Lot.quantity > 0,
        )
        .order_by(models.Lot.expiry_date.asc().nullslast(), models.Lot.received_at.asc())
        .all()
    )
    for lot in lots:
        if remaining <= 0:
            break
        take = min(lot.quantity, remaining)
        lot.quantity -= take
        remaining -= take
        picks.append({"lot_id": lot.id, "qty": take})
    return picks
