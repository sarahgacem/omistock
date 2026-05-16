from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import models
import schemas

def get_dashboard_stats_data(db: Session, cid: int, branch_id: Optional[int] = None) -> Dict[str, Any]:
    if branch_id:
        inventory_items = db.query(models.Inventory).join(models.Product).filter(
            models.Inventory.branch_id == branch_id,
            models.Product.company_id == cid
        ).all()
        
        total_products = len(inventory_items)
        total_qty = sum(item.quantity for item in inventory_items)
        total_value = sum(item.quantity * item.product.price for item in inventory_items)
        alerts = [i.product for i in inventory_items if i.quantity <= i.product.min_threshold]
        
        for i in inventory_items:
            i.product.quantity = i.quantity 
        products = [i.product for i in inventory_items]
    else:
        products = db.query(models.Product).filter(models.Product.company_id == cid).all()
        total_products = len(products)
        total_qty = sum((p.quantity or 0) for p in products)
        total_value = sum((p.price or 0) * (p.quantity or 0) for p in products)
        alerts = [p for p in products if (p.quantity or 0) <= (p.min_threshold or 0)]
    
    if not products and not branch_id:
        return {
            "summary": {"total_products": 0, "alerts_count": 0, "total_value": 0, "total_qty": 0},
            "alerts": [], "top_5": [], "top_sold": [], "movements": [], "trend": []
        }

    today = datetime.now().date()
    start_date = today - timedelta(days=6)
    
    movements_query = db.query(models.StockMovement).filter(models.StockMovement.company_id == cid)
    if branch_id:
        movements_query = movements_query.filter(models.StockMovement.branch_id == branch_id)
    movements_db = movements_query.all()

    trend_dict = { (start_date + timedelta(days=i)).strftime("%A"): {"in": 0, "out": 0} for i in range(7) }
    
    for mov in movements_db:
        mov_date = mov.created_at.date() if mov.created_at else today
        if start_date <= mov_date <= today:
            day_name = mov_date.strftime("%A")
            if day_name in trend_dict:
                if mov.movement_type == "IN" or (mov.quantity and mov.quantity > 0):
                    trend_dict[day_name]["in"] += abs(mov.quantity or 0)
                else:
                    trend_dict[day_name]["out"] += abs(mov.quantity or 0)
                
    trend = [{"day": day, "in": data["in"], "out": data["out"]} for day, data in trend_dict.items()]

    top_5 = sorted(products, key=lambda x: (x.quantity or 0), reverse=True)[:5]

    top_sold_query = db.query(
        models.Product.name, 
        func.sum(models.SaleItem.quantity).label('total_sold')
    ).join(models.SaleItem).join(models.Sale).filter(
        models.Sale.company_id == cid
    )
    if branch_id:
        top_sold_query = top_sold_query.filter(models.Sale.branch_id == branch_id)
    
    top_sold_db = top_sold_query.group_by(models.Product.id).order_by(func.sum(models.SaleItem.quantity).desc()).limit(5).all()
    top_sold = [{"name": row.name, "total_sold": int(row.total_sold)} for row in top_sold_db]

    movements_recent_query = db.query(models.StockMovement).filter(models.StockMovement.company_id == cid)
    if branch_id:
        movements_recent_query = movements_recent_query.filter(models.StockMovement.branch_id == branch_id)
    movements_recent = movements_recent_query.order_by(models.StockMovement.created_at.desc()).limit(10).all()
    
    movements_list = []
    for m in movements_recent:
        p = db.query(models.Product).filter(models.Product.id == m.product_id).first()
        movements_list.append({
            "id": m.id,
            "product_name": p.name if p else "Produit inconnu",
            "quantity": m.quantity,
            "reason": m.reason,
            "date": m.created_at.strftime("%d/%m %H:%M") if m.created_at else "--"
        })
    
    return {
        "summary": {
            "total_products": total_products,
            "alerts_count": len(alerts),
            "total_value": total_value,
            "total_qty": total_qty
        },
        "alerts": [{"id": p.id, "name": p.name, "quantity": p.quantity, "supplier": (p.supplier.name if p.supplier else "N/A")} for p in alerts],
        "top_5": [{"name": p.name, "quantity": p.quantity} for p in top_5],
        "top_sold": top_sold,
        "movements": movements_list,
        "trend": trend
    }

def analyze_product_mcp(db: Session, product_id: int, company_id: int, user_id: int) -> str:
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise Exception("Produit non trouvé")
    
    qty = product.quantity or 0
    
    historique_sorties = db.query(models.AuditLog).filter(
        models.AuditLog.company_id == company_id,
        models.AuditLog.action.ilike("%OUT%") | models.AuditLog.action.ilike("%Vente%") | models.AuditLog.action.ilike("%SELL%")
    ).count()
    
    vitesse_vente_jour = (historique_sorties * 2) + 1 
    
    if qty <= 0:
        advice = f"🚨 ALERTE CRITIQUE : '{product.name}' est déjà en rupture. Action requise."
    else:
        heures_restantes = int((qty / vitesse_vente_jour) * 24)
        if heures_restantes < 48:
            advice = f"⚠️ Attention, ce produit ('{product.name}') sera épuisé dans {heures_restantes}h au rythme actuel ! Un transfert ou une commande urgente est recommandé."
        else:
            jours = heures_restantes // 24
            advice = f"✅ Le stock de '{product.name}' est suffisant. Épuisement estimé dans {jours} jours au rythme actuel."
        
    return advice

def create_user_service(db: Session, data: schemas.UserSignUp) -> Dict[str, str]:
    existing_user = db.query(models.User).filter(models.User.email == data.email).first()
    if existing_user:
        raise Exception("Cet email est déjà utilisé.")
    
    import security
    new_company = models.Company(name=data.company_name)
    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    
    b1 = models.Branch(name="Dépôt Alger", city="Alger", company_id=new_company.id)
    b2 = models.Branch(name="Dépôt Oran", city="Oran", company_id=new_company.id)
    db.add_all([b1, b2])
    
    hashed_password = security.get_password_hash(data.password)
    new_user = models.User(
        email=data.email, 
        hashed_password=hashed_password, 
        company_id=new_company.id,
        branch_id=b1.id 
    )
    db.add(new_user)
    db.commit()
    
    return {"status": "success", "message": "Compte créé avec succès !"}

def authenticate_user(db: Session, form_data: Any) -> Dict[str, str]:
    import security
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise Exception("Identifiants incorrects")
    access_token = security.create_access_token(data={"sub": user.email, "company_id": user.company_id})
    return {"access_token": access_token, "token_type": "bearer"}
