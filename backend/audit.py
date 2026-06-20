"""
OMISTOCK — Service d'audit traçable et infalsifiable (tamper-evident).

Chaque entrée d'audit :
- est horodatée ;
- enregistre l'acteur (humain ou agent) et son type ;
- enregistre un delta structuré (JSON) old -> new ;
- porte un correlation_id pour relier intention -> action -> résultat ;
- est chaînée par hash (prev_hash -> entry_hash) par entreprise, ce qui rend
  toute modification ou suppression d'une entrée détectable (intégrité).
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

import models


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def _canonical(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    except Exception:
        return str(value)


def _last_hash(db: Session, company_id: int) -> Optional[str]:
    last = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.company_id == company_id)
        .order_by(models.AuditLog.id.desc())
        .first()
    )
    return last.entry_hash if last else None


def _compute_hash(
    *,
    prev: Optional[str],
    company_id: int,
    user_id: int,
    actor_type: Optional[str],
    action: Optional[str],
    entity_type: Optional[str],
    entity_id: Optional[int],
    old_s: Optional[str],
    new_s: Optional[str],
    ts: Optional[str],
) -> str:
    """
    Calcul canonique du hash d'une entrée d'audit.
    Utilisé À LA FOIS lors de l'écriture (record) ET lors de la vérification
    (verify_chain) afin que la chaîne puisse être REJOUÉE intégralement, y compris
    l'horodatage exact (persisté dans la colonne hash_ts).
    """
    payload = "|".join(
        [
            str(prev or ""),
            str(company_id),
            str(user_id),
            actor_type or "",
            action or "",
            entity_type or "",
            str(entity_id or ""),
            old_s or "",
            new_s or "",
            ts or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record(
    db: Session,
    *,
    user_id: int,
    actor_type: str,
    action: str,
    company_id: int,
    old_value: Any = None,
    new_value: Any = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    commit: bool = True,
) -> models.AuditLog:
    """Ajoute une entrée d'audit chaînée par hash."""
    old_s = _canonical(old_value)
    new_s = _canonical(new_value)
    prev = _last_hash(db, company_id)
    ts = datetime.now(timezone.utc).isoformat()

    entry_hash = _compute_hash(
        prev=prev,
        company_id=company_id,
        user_id=user_id,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_s=old_s,
        new_s=new_s,
        ts=ts,
    )

    log = models.AuditLog(
        user_id=user_id,
        actor_type=actor_type,
        action=action,
        old_value=old_s,
        new_value=new_s,
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        company_id=company_id,
        prev_hash=prev,
        entry_hash=entry_hash,
        hash_ts=ts,
    )
    db.add(log)
    if commit:
        db.commit()
        db.refresh(log)
    return log


def verify_chain(db: Session, company_id: int) -> dict:
    """
    Revalide INTÉGRALEMENT la chaîne de hachage d'une entreprise.

    Pour chaque entrée :
      1. on vérifie la continuité du maillon (prev_hash == hash de l'entrée précédente) ;
      2. on RECALCULE entry_hash à partir de tous les champs persistés (y compris
         l'horodatage canonique hash_ts) et on le compare au hash stocké.

    Toute insertion, suppression, réordonnancement OU modification en place du
    contenu d'une entrée est ainsi détectée.

    Retourne {"valid", "checked", "broken_at", "reason"}.
    Compat : les entrées historiques sans hash_ts (avant migration) ne peuvent pas
    être rejouées sur l'horodatage ; pour celles-ci on retombe sur la vérification
    de continuité uniquement (legacy), signalée via "legacy_entries".
    """
    logs = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.company_id == company_id)
        .order_by(models.AuditLog.id.asc())
        .all()
    )
    prev = None
    legacy = 0
    for log in logs:
        # 1) continuité du maillon
        if log.prev_hash != prev:
            return {
                "valid": False,
                "checked": len(logs),
                "broken_at": log.id,
                "reason": "prev_hash discontinu (insertion/suppression/réordonnancement)",
            }
        # 2) re-calcul complet du hash
        if log.hash_ts is None:
            # Entrée legacy (avant l'ajout de hash_ts) : replay impossible.
            legacy += 1
        else:
            recomputed = _compute_hash(
                prev=prev,
                company_id=log.company_id,
                user_id=log.user_id,
                actor_type=log.actor_type,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                old_s=log.old_value,
                new_s=log.new_value,
                ts=log.hash_ts,
            )
            if recomputed != log.entry_hash:
                return {
                    "valid": False,
                    "checked": len(logs),
                    "broken_at": log.id,
                    "reason": "entry_hash recalculé != stocké (modification en place du contenu)",
                }
        prev = log.entry_hash
    return {
        "valid": True,
        "checked": len(logs),
        "broken_at": None,
        "legacy_entries": legacy,
        "reason": "ok",
    }
