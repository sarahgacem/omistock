from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import models
import schemas
import stock
import audit


def log_audit(
    db: Session,
    user_id: int,
    action: str,
    old_val: Any,
    new_val: Any,
    company_id: int,
    *,
    actor_type: str = "HUMAIN",
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
):
    """
    Compatibilité ascendante : délègue au journal d'audit chaîné par hash.
    (Anciennes signatures positionnelles toujours supportées.)
    """
    return audit.record(
        db,
        user_id=user_id,
        actor_type=actor_type,
        action=action,
        old_value=old_val,
        new_value=new_val,
        company_id=company_id,
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
    )


def get_dashboard_stats_data(db: Session, cid: int, branch_id: Optional[int] = None) -> Dict[str, Any]:
    products = db.query(models.Product).filter(models.Product.company_id == cid).all()

    # Stock disponible (source de vérité = Inventory)
    def on_hand(p):
        if branch_id is not None:
            return sum((inv.quantity or 0) for inv in p.inventory if inv.branch_id == branch_id)
        return p.total_quantity

    total_products = len(products)
    total_qty = sum(on_hand(p) for p in products)
    # Valorisation AU COÛT (WAC), pas au prix de vente.
    total_value = stock.stock_value_at_cost(db, cid, branch_id)
    # Alertes basées sur le point de commande (ROP) réel.
    alerts = stock.get_alerts(db, cid, branch_id)

    if not products:
        return {
            "summary": {"total_products": 0, "alerts_count": 0, "total_value": 0,
                        "total_qty": 0, "potential_margin": 0},
            "alerts": [], "top_5": [], "top_sold": [], "movements": [], "trend": [],
            "branch_distribution": [], "expiring_lots": [],
        }

    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=6)

    movements_query = db.query(models.StockMovement).filter(models.StockMovement.company_id == cid)
    if branch_id:
        movements_query = movements_query.filter(models.StockMovement.branch_id == branch_id)
    movements_db = movements_query.all()

    trend_dict = {(start_date + timedelta(days=i)).strftime("%A"): {"in": 0, "out": 0} for i in range(7)}
    for mov in movements_db:
        mov_date = mov.created_at.date() if mov.created_at else today
        if start_date <= mov_date <= today:
            day_name = mov_date.strftime("%A")
            if day_name in trend_dict:
                if mov.movement_type == "IN" or (mov.quantity and mov.quantity > 0):
                    trend_dict[day_name]["in"] += abs(mov.quantity or 0)
                else:
                    trend_dict[day_name]["out"] += abs(mov.quantity or 0)
    trend = [{"day": d, "in": v["in"], "out": v["out"]} for d, v in trend_dict.items()]

    top_5 = sorted(products, key=on_hand, reverse=True)[:5]

    top_sold_query = (
        db.query(models.Product.name, func.sum(models.SaleItem.quantity).label("total_sold"))
        .join(models.SaleItem).join(models.Sale)
        .filter(models.Sale.company_id == cid, models.Sale.status == "CONFIRMED")
    )
    if branch_id:
        top_sold_query = top_sold_query.filter(models.Sale.branch_id == branch_id)
    top_sold_db = (
        top_sold_query.group_by(models.Product.id)
        .order_by(func.sum(models.SaleItem.quantity).desc())
        .limit(5).all()
    )
    top_sold = [{"name": r.name, "total_sold": int(r.total_sold)} for r in top_sold_db]

    movements_recent_q = db.query(models.StockMovement).filter(models.StockMovement.company_id == cid)
    if branch_id:
        movements_recent_q = movements_recent_q.filter(models.StockMovement.branch_id == branch_id)
    movements_recent = movements_recent_q.order_by(models.StockMovement.created_at.desc()).limit(10).all()
    movements_list = []
    for m in movements_recent:
        p = db.query(models.Product).filter(models.Product.id == m.product_id).first()
        movements_list.append({
            "id": m.id,
            "product_name": p.name if p else "Produit inconnu",
            "quantity": m.quantity,
            "reason": m.reason,
            "date": m.created_at.strftime("%d/%m %H:%M") if m.created_at else "--",
        })

    branches = db.query(models.Branch).filter(models.Branch.company_id == cid).all()
    branch_distribution = [
        {"branch_name": b.name, "branch_city": b.city,
         "stock_value": stock.stock_value_at_cost(db, cid, b.id)}
        for b in branches
    ]

    # Marge potentielle = valeur de vente - valeur au coût.
    potential_sale_value = 0.0
    for p in products:
        potential_sale_value += on_hand(p) * (p.price or 0.0)
    potential_margin = round(potential_sale_value - total_value, 2)

    expiring = stock.expiring_lots(db, cid, within_days=30)

    return {
        "summary": {
            "total_products": total_products,
            "alerts_count": len(alerts),
            "total_value": total_value,
            "total_qty": total_qty,
            "potential_margin": potential_margin,
        },
        "alerts": [
            {"id": p.id, "name": p.name, "quantity": on_hand(p),
             "reorder_point": p.reorder_point,
             "supplier": (p.supplier.name if p.supplier else "N/A")}
            for p in alerts
        ],
        "top_5": [{"name": p.name, "quantity": on_hand(p)} for p in top_5],
        "top_sold": top_sold,
        "movements": movements_list,
        "trend": trend,
        "branch_distribution": branch_distribution,
        "expiring_lots": [
            {"product_id": l.product_id, "lot_number": l.lot_number,
             "quantity": l.quantity,
             "expiry_date": l.expiry_date.isoformat() if l.expiry_date else None}
            for l in expiring
        ],
    }


def analyze_product_mcp(db: Session, product_id: int, company_id: int, user_id: int) -> Dict[str, Any]:
    """
    Prévision RÉELLE basée sur la demande historique (et non un nombre arbitraire).
    Retourne un objet structuré : stock, demande/jour, jours avant rupture, ROP, recommandation.
    """
    product = (
        db.query(models.Product)
        .filter(models.Product.id == product_id, models.Product.company_id == company_id)
        .first()
    )
    if not product:
        raise ValueError("Produit non trouvé")

    on_hand = product.total_quantity
    avg_daily = stock.compute_avg_daily_demand(db, product_id, company_id, window_days=30)
    rop = product.reorder_point

    if avg_daily > 0:
        days_left = round(on_hand / avg_daily, 1)
    else:
        days_left = None

    if on_hand <= 0:
        reco = "RUPTURE : commande urgente requise."
        severity = "critical"
    elif on_hand <= rop:
        reco = f"Sous le point de commande ({rop}). Déclencher un réapprovisionnement."
        severity = "warning"
    elif days_left is not None and days_left <= (product.lead_time_days or 7):
        reco = f"Rupture estimée dans ~{days_left} jours, soit avant le délai d'appro. Commander."
        severity = "warning"
    else:
        reco = "Stock suffisant au rythme actuel."
        severity = "ok"

    return {
        "product_id": product_id,
        "name": product.name,
        "on_hand": on_hand,
        "avg_daily_demand": avg_daily,
        "reorder_point": rop,
        "days_until_stockout": days_left,
        "lead_time_days": product.lead_time_days or (product.supplier.lead_time_days if product.supplier else 0) or 0,
        "severity": severity,
        "recommendation": reco,
    }


def create_user_service(db: Session, data: schemas.UserSignUp) -> Dict[str, str]:
    import security
    if db.query(models.User).filter(models.User.email == data.email).first():
        raise ValueError("Cet email est déjà utilisé.")

    new_company = models.Company(
        name=data.company_name,
        commercial_register_number=data.commercial_register_number,
        activity_sector=data.activity_sector,
        nif=data.nif,
        address=data.address,
        email=data.company_email or data.email,
        phone=data.company_phone,
    )
    db.add(new_company)
    db.commit()
    db.refresh(new_company)

    b1 = models.Branch(name="Dépôt Alger", city="Alger", company_id=new_company.id)
    b2 = models.Branch(name="Dépôt Oran", city="Oran", company_id=new_company.id)
    db.add_all([b1, b2])
    db.flush()

    new_user = models.User(
        email=data.email,
        hashed_password=security.get_password_hash(data.password),
        company_id=new_company.id,
        branch_id=b1.id,
        user_type="ADMIN",
    )
    db.add(new_user)
    db.commit()
    return {"status": "success", "message": "Compte créé avec succès !"}


def authenticate_user(db: Session, form_data: Any) -> Dict[str, str]:
    """
    Authentifie l'utilisateur. NE supprime plus de données ici (effet de bord
    destructif retiré : la purge est gérée par une tâche d'administration dédiée).
    Réactive simplement un compte en période de grâce après login réussi.
    """
    import security
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise ValueError("Identifiants incorrects")

    # Compte en cours de suppression : on le réactive (annulation de la suppression).
    if getattr(user, "deletion_deadline", None) is not None:
        deadline = user.deletion_deadline
        deadline = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > deadline:
            raise ValueError("Ce compte est en attente de suppression définitive. Contactez l'administrateur.")
        user.is_active = True
        user.deletion_deadline = None
        db.commit()

    access_token = security.create_access_token(
        data={"sub": user.email, "company_id": user.company_id, "role": user.user_type}
    )
    return {"access_token": access_token, "token_type": "bearer"}


def purge_expired_accounts(db: Session) -> int:
    """
    Tâche d'administration (hors chemin d'authentification) : supprime définitivement
    les entreprises dont l'unique admin a dépassé le délai de grâce. À appeler via
    un job planifié, jamais pendant un login.
    """
    now = datetime.now(timezone.utc)
    purged = 0
    candidates = (
        db.query(models.User)
        .filter(models.User.deletion_deadline != None)  # noqa: E711
        .all()
    )
    for user in candidates:
        deadline = user.deletion_deadline
        deadline = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
        if now <= deadline:
            continue
        company_users = db.query(models.User).filter(models.User.company_id == user.company_id).count()
        if company_users <= 1:
            cid = user.company_id
            for model in (
                models.AuditLog, models.ActivityLog, models.AgentProposal, models.StockMovement,
            ):
                db.query(model).filter(model.company_id == cid).delete(synchronize_session=False)
            db.query(models.SaleItem).filter(
                models.SaleItem.sale_id.in_(
                    db.query(models.Sale.id).filter(models.Sale.company_id == cid)
                )
            ).delete(synchronize_session=False)
            db.query(models.Sale).filter(models.Sale.company_id == cid).delete(synchronize_session=False)
            db.query(models.TransferRequest).filter(models.TransferRequest.company_id == cid).delete(synchronize_session=False)
            db.query(models.Lot).filter(models.Lot.company_id == cid).delete(synchronize_session=False)
            db.query(models.Inventory).filter(
                models.Inventory.branch_id.in_(
                    db.query(models.Branch.id).filter(models.Branch.company_id == cid)
                )
            ).delete(synchronize_session=False)
            db.query(models.Product).filter(models.Product.company_id == cid).delete(synchronize_session=False)
            db.query(models.Supplier).filter(models.Supplier.company_id == cid).delete(synchronize_session=False)
            db.query(models.Customer).filter(models.Customer.company_id == cid).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.company_id == cid).delete(synchronize_session=False)
            db.query(models.Branch).filter(models.Branch.company_id == cid).delete(synchronize_session=False)
            db.query(models.Company).filter(models.Company.id == cid).delete(synchronize_session=False)
            purged += 1
    db.commit()
    return purged


def create_branch_user(db: Session, user_data: schemas.BranchUserCreate, company_id: int, role: str) -> models.User:
    import security
    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise ValueError("Cet email est déjà utilisé.")
    branch = (
        db.query(models.Branch)
        .filter(models.Branch.id == user_data.branch_id, models.Branch.company_id == company_id)
        .first()
    )
    if not branch:
        raise ValueError("Filiale invalide ou n'appartient pas à votre entreprise.")
    if role == "ADMIN":
        existing_admin = (
            db.query(models.User)
            .filter(
                models.User.branch_id == user_data.branch_id,
                models.User.user_type == "ADMIN",
                models.User.company_id == company_id,
            )
            .first()
        )
        if existing_admin:
            raise ValueError("Cette filiale possède déjà un administrateur.")
    new_user = models.User(
        email=user_data.email,
        hashed_password=security.get_password_hash(user_data.password),
        user_type=role,
        branch_id=user_data.branch_id,
        company_id=company_id,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
