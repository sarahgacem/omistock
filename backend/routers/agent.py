"""
OMISTOCK — Interface DÉDIÉE aux agents IA.

Séparation stricte des interfaces (best practice agent-ready) :
- Les humains utilisent les routes /api/* avec JWT.
- Les agents utilisent /api/agent/* avec X-API-Key, des SCOPES explicites et un
  NIVEAU D'AUTONOMIE borné. Un agent ne peut PAS appeler les routes humaines de
  mutation directe ; il passe par cette surface restreinte et auditée.

Modèle d'autorisation :
- READ_ONLY  : lecture (alertes, résumé, prévision).
- SUGGEST    : idem + analyses.
- PROPOSE    : peut créer des PROPOSITIONS (restock/transfert) en attente de
               validation humaine (human-in-the-loop).
- AUTO       : peut exécuter directement, dans la limite de max_action_quantity
               et des scopes "...:auto".
Toutes les actions agent sont tracées (audit chaîné) avec correlation_id.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend import repository
import models
import schemas
import stock
import audit
import agent_policy
import services
from dependencies import get_current_agent
from database import get_db

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _corr(request: Request) -> str:
    return getattr(request.state, "correlation_id", None) or audit.new_correlation_id()


# ---- Lecture (READ_ONLY+) ----------------------------------------------------

@router.get("/alerts")
def agent_alerts(
    request: Request,
    agent: models.User = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    err = agent_policy.authorize_agent_action(
        agent, required_scope="stock:read", required_level=models.AutonomyLevel.READ_ONLY.value
    )
    if err:
        raise HTTPException(status_code=403, detail=err)
    alerts = stock.get_alerts(db, agent.company_id)
    audit.record(db, user_id=agent.id, actor_type="AGENT", action="AGENT_READ_ALERTS",
                 company_id=agent.company_id, entity_type="alerts", correlation_id=_corr(request),
                 new_value={"count": len(alerts)})
    return [{"id": p.id, "name": p.name, "on_hand": p.total_quantity,
             "reorder_point": p.reorder_point} for p in alerts]


@router.get("/forecast/{product_id}")
def agent_forecast(
    product_id: int,
    request: Request,
    agent: models.User = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    err = agent_policy.authorize_agent_action(
        agent, required_scope="stock:read", required_level=models.AutonomyLevel.SUGGEST.value
    )
    if err:
        raise HTTPException(status_code=403, detail=err)
    try:
        result = services.analyze_product_mcp(db, product_id, agent.company_id, agent.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    audit.record(db, user_id=agent.id, actor_type="AGENT", action="AGENT_FORECAST",
                 company_id=agent.company_id, entity_type="product", entity_id=product_id,
                 correlation_id=_corr(request), new_value=result)
    return result


# ---- Propositions (PROPOSE+) : human-in-the-loop -----------------------------

@router.post("/proposals/restock")
def agent_propose_restock(
    data: schemas.AgentRestockProposal,
    request: Request,
    agent: models.User = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    err = agent_policy.authorize_agent_action(
        agent, required_scope="restock:propose",
        required_level=models.AutonomyLevel.PROPOSE.value, quantity=None,
    )
    if err:
        raise HTTPException(status_code=403, detail=err)
    corr = _corr(request)
    payload = data.model_dump()
    prop = repository.create_agent_proposal(
        db, agent_id=agent.id, company_id=agent.company_id, action_type="RESTOCK",
        payload=json.dumps(payload), rationale=data.rationale or "", correlation_id=corr,
    )
    audit.record(db, user_id=agent.id, actor_type="AGENT", action="AGENT_PROPOSE_RESTOCK",
                 company_id=agent.company_id, entity_type="proposal", entity_id=prop.id,
                 correlation_id=corr, new_value=payload)
    return {"status": "pending_human_approval", "proposal_id": prop.id}


# ---- Exécution directe (AUTO) : bornée par scope + plafond quantité ----------

@router.post("/restock")
def agent_auto_restock(
    data: schemas.AgentRestockProposal,
    request: Request,
    agent: models.User = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    err = agent_policy.authorize_agent_action(
        agent, required_scope="restock:auto",
        required_level=models.AutonomyLevel.AUTO.value, quantity=data.quantity,
    )
    if err:
        raise HTTPException(status_code=403, detail=err)
    corr = _corr(request)
    try:
        mv = repository.restock_product(
            db, product_id=data.product_id, branch_id=data.branch_id, quantity=data.quantity,
            company_id=agent.company_id, actor_id=agent.id, unit_cost=data.unit_cost or 0.0,
            reason="Réappro auto (agent IA)", correlation_id=corr,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit.record(db, user_id=agent.id, actor_type="AGENT", action="AGENT_AUTO_RESTOCK",
                 company_id=agent.company_id, entity_type="stock_movement", entity_id=mv.id,
                 correlation_id=corr, new_value={"qty": data.quantity, "product": data.product_id})
    return {"status": "executed", "movement_id": mv.id}


# ---- Inventaire & valorisation (READ_ONLY+) ---------------------------------

@router.get("/inventory")
def agent_inventory(
    request: Request,
    branch_id: int = None,
    low_stock_only: bool = False,
    agent: models.User = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    err = agent_policy.authorize_agent_action(
        agent, required_scope="stock:read", required_level=models.AutonomyLevel.READ_ONLY.value
    )
    if err:
        raise HTTPException(status_code=403, detail=err)

    products = repository.get_products(db, company_id=agent.company_id, branch_id=branch_id)
    result = []
    for p in products:
        on_hand = p.total_quantity
        rop = p.reorder_point
        if low_stock_only and on_hand > rop:
            continue
        result.append({
            "id": p.id, "name": p.name, "sku": p.sku,
            "on_hand": on_hand, "reorder_point": rop,
            "cost_price": p.cost_price or 0.0,
        })
    audit.record(db, user_id=agent.id, actor_type="AGENT", action="AGENT_READ_INVENTORY",
                 company_id=agent.company_id, entity_type="inventory", correlation_id=_corr(request),
                 new_value={"count": len(result), "low_stock_only": low_stock_only})
    return result


@router.get("/valuation")
def agent_valuation(
    request: Request,
    branch_id: int = None,
    agent: models.User = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    err = agent_policy.authorize_agent_action(
        agent, required_scope="stock:read", required_level=models.AutonomyLevel.READ_ONLY.value
    )
    if err:
        raise HTTPException(status_code=403, detail=err)
    value = stock.stock_value_at_cost(db, agent.company_id, branch_id)
    audit.record(db, user_id=agent.id, actor_type="AGENT", action="AGENT_READ_VALUATION",
                 company_id=agent.company_id, entity_type="valuation", correlation_id=_corr(request),
                 new_value={"total_value": value})
    return {"total_value_at_cost": value, "currency": "DA"}


@router.get("/reorder-suggestions")
def agent_reorder_suggestions(
    request: Request,
    agent: models.User = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    err = agent_policy.authorize_agent_action(
        agent, required_scope="stock:read", required_level=models.AutonomyLevel.READ_ONLY.value
    )
    if err:
        raise HTTPException(status_code=403, detail=err)
    alerts = stock.get_alerts(db, agent.company_id)
    suggestions = []
    for p in alerts:
        annual = (p.avg_daily_demand or 0) * 365
        ordering_cost = 500.0
        holding_pct = 0.2
        holding = (p.cost_price or 1.0) * holding_pct
        eoq = stock.economic_order_quantity(annual, ordering_cost, holding)
        suggestions.append({
            "id": p.id, "name": p.name,
            "on_hand": p.total_quantity, "reorder_point": p.reorder_point,
            "suggested_qty": int(eoq) if eoq else max(p.reorder_point - p.total_quantity, 0),
        })
    audit.record(db, user_id=agent.id, actor_type="AGENT", action="AGENT_REORDER_SUGGESTIONS",
                 company_id=agent.company_id, entity_type="suggestions", correlation_id=_corr(request),
                 new_value={"count": len(suggestions)})
    return suggestions


@router.get("/expiring-lots")
def agent_expiring_lots(
    request: Request,
    days: int = 30,
    agent: models.User = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    err = agent_policy.authorize_agent_action(
        agent, required_scope="stock:read", required_level=models.AutonomyLevel.READ_ONLY.value
    )
    if err:
        raise HTTPException(status_code=403, detail=err)
    days = max(1, days)
    lots = stock.expiring_lots(db, agent.company_id, within_days=days)
    result = [
        {"lot_id": l.id, "product_id": l.product_id, "lot_number": l.lot_number,
         "quantity": l.quantity, "expiry_date": l.expiry_date.isoformat() if l.expiry_date else None}
        for l in lots
    ]
    audit.record(db, user_id=agent.id, actor_type="AGENT", action="AGENT_READ_EXPIRING_LOTS",
                 company_id=agent.company_id, entity_type="lots", correlation_id=_corr(request),
                 new_value={"count": len(result), "horizon_days": days})
    return result


# ---- Auto-introspection & suivi propositions ---------------------------------

@router.get("/proposals/mine")
def agent_my_proposals(
    request: Request,
    status: str = None,
    agent: models.User = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    err = agent_policy.authorize_agent_action(
        agent, required_scope="stock:read", required_level=models.AutonomyLevel.READ_ONLY.value
    )
    if err:
        raise HTTPException(status_code=403, detail=err)
    q = db.query(models.AgentProposal).filter(models.AgentProposal.agent_id == agent.id)
    if status:
        q = q.filter(models.AgentProposal.status == status.upper())
    proposals = q.order_by(models.AgentProposal.created_at.desc()).all()
    result = [
        {"id": p.id, "action_type": p.action_type, "status": p.status,
         "rationale": p.rationale, "created_at": p.created_at.isoformat() if p.created_at else None}
        for p in proposals
    ]
    return result


@router.get("/capabilities")
def agent_capabilities(
    request: Request,
    agent: models.User = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    from agent_policy import parse_scopes
    return {
        "agent_id": agent.id,
        "autonomy_level": agent.autonomy_level,
        "scopes": parse_scopes(agent),
        "max_action_quantity": agent.max_action_quantity or 0,
        "api_key_expires_at": agent.api_key_expires_at.isoformat() if agent.api_key_expires_at else None,
    }
