"""
OMISTOCK — Politique d'autorisation des agents IA (agent-ready best practice).

Modèle :
- autonomy_level : READ_ONLY < SUGGEST < PROPOSE < AUTO (ordre croissant de pouvoir).
- agent_scopes   : liste de capacités fines (ex: "stock:read", "transfer:propose",
                   "restock:auto"). Un agent ne peut faire QUE ce qui est explicitement
                   autorisé (least privilege).
- max_action_quantity : plafond quantité pour les actions autonomes (garde-fou).

Les humains (HUMAIN/ADMIN) ne sont pas soumis à cette politique : ils passent par
le RBAC classique. Cette politique borne uniquement les agents (user_type == AGENT).
"""
from typing import List, Optional

import models

LEVEL_ORDER = {
    models.AutonomyLevel.READ_ONLY.value: 0,
    models.AutonomyLevel.SUGGEST.value: 1,
    models.AutonomyLevel.PROPOSE.value: 2,
    models.AutonomyLevel.AUTO.value: 3,
}


def parse_scopes(user: models.User) -> List[str]:
    if not getattr(user, "agent_scopes", None):
        return []
    return [s.strip() for s in user.agent_scopes.split(",") if s.strip()]


def has_scope(user: models.User, scope: str) -> bool:
    scopes = parse_scopes(user)
    # support wildcard "domain:*"
    domain = scope.split(":")[0]
    return scope in scopes or f"{domain}:*" in scopes or "*" in scopes


def level_at_least(user: models.User, required: str) -> bool:
    have = LEVEL_ORDER.get(getattr(user, "autonomy_level", None) or "", -1)
    need = LEVEL_ORDER.get(required, 99)
    return have >= need


def quantity_within_limit(user: models.User, quantity: int) -> bool:
    cap = getattr(user, "max_action_quantity", 0) or 0
    if cap <= 0:
        return False  # aucun plafond configuré => pas d'action autonome quantitative
    return quantity <= cap


def authorize_agent_action(
    user: models.User,
    *,
    required_scope: str,
    required_level: str,
    quantity: Optional[int] = None,
) -> Optional[str]:
    """
    Retourne None si autorisé, sinon un message d'erreur explicite.
    Pour les non-agents, renvoie un refus : utiliser le RBAC humain à la place.
    """
    if getattr(user, "user_type", None) != "AGENT":
        return "Cette voie est réservée aux agents IA."
    if not level_at_least(user, required_level):
        return (
            f"Niveau d'autonomie insuffisant (requis: {required_level}, "
            f"actuel: {getattr(user, 'autonomy_level', 'inconnu')})."
        )
    if not has_scope(user, required_scope):
        return f"Scope manquant : '{required_scope}' n'est pas autorisé pour cet agent."
    if quantity is not None and not quantity_within_limit(user, quantity):
        return (
            f"Quantité {quantity} au-delà du plafond autorisé pour l'agent "
            f"(max: {getattr(user, 'max_action_quantity', 0)})."
        )
    return None
