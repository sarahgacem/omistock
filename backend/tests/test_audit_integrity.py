"""
Tests de l'intégrité du journal d'audit (tamper-evidence).

Vérifie la correction du gap "verify_chain ne recalculait pas entry_hash" :
- une chaîne intacte est valide ;
- une modification EN PLACE du contenu d'une entrée est détectée (replay complet
  du hash via la colonne hash_ts persistée) ;
- une rupture de continuité (prev_hash) est détectée.
"""
import audit
import models


def _seed_entries(db, company, human, n=3):
    cid = company.id
    for i in range(n):
        audit.record(
            db,
            user_id=human.id,
            actor_type="HUMAIN",
            action=f"TEST_ACTION_{i}",
            company_id=cid,
            entity_type="product",
            entity_id=i + 1,
            new_value={"i": i},
        )


def test_valid_chain_verifies(db, company, human):
    _seed_entries(db, company, human, n=3)
    result = audit.verify_chain(db, company.id)
    assert result["valid"] is True
    assert result["checked"] == 3
    assert result["broken_at"] is None
    # Toutes les entrées doivent porter un hash_ts (replay possible).
    assert result.get("legacy_entries", 0) == 0


def test_inplace_content_tampering_is_detected(db, company, human):
    """Le coeur du gap corrigé : éditer le contenu sans toucher la chaîne doit casser le hash."""
    _seed_entries(db, company, human, n=3)

    # On falsifie le contenu d'une entrée du milieu SANS changer prev_hash/entry_hash.
    middle = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.company_id == company.id)
        .order_by(models.AuditLog.id.asc())
        .all()[1]
    )
    middle.new_value = '{"i": 999, "tampered": true}'
    db.commit()

    result = audit.verify_chain(db, company.id)
    assert result["valid"] is False
    assert result["broken_at"] == middle.id


def test_prev_hash_break_is_detected(db, company, human):
    _seed_entries(db, company, human, n=3)
    second = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.company_id == company.id)
        .order_by(models.AuditLog.id.asc())
        .all()[1]
    )
    second.prev_hash = "deadbeef"  # rupture de continuité
    db.commit()

    result = audit.verify_chain(db, company.id)
    assert result["valid"] is False
    assert result["broken_at"] == second.id
