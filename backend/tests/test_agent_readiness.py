"""Tests plateforme agent-ready : audit chaîné (tamper-evident) + politique d'autonomie."""
import audit
import agent_policy
import models


# ---------------------------------------------------------------------------
# Audit : chaîne de hachage infalsifiable
# ---------------------------------------------------------------------------

def test_audit_chain_valid_after_appends(db, company, human):
    for i in range(3):
        audit.record(
            db, user_id=human.id, actor_type="HUMAIN", action=f"ACT_{i}",
            company_id=company.id, new_value={"i": i},
        )
    result = audit.verify_chain(db, company.id)
    assert result["valid"] is True
    assert result["checked"] == 3
    assert result["broken_at"] is None


def test_audit_chain_detects_tampering(db, company, human):
    logs = [
        audit.record(db, user_id=human.id, actor_type="HUMAIN", action=f"A{i}",
                     company_id=company.id, new_value={"i": i})
        for i in range(3)
    ]
    # Falsification : on casse le maillon prev_hash de la 2e entrée.
    logs[1].prev_hash = "TAMPERED"
    db.commit()
    result = audit.verify_chain(db, company.id)
    assert result["valid"] is False
    assert result["broken_at"] == logs[1].id


def test_audit_isolated_per_company(db, company, human):
    other = models.Company(name="Other Co")
    db.add(other)
    db.commit()
    db.refresh(other)
    audit.record(db, user_id=human.id, actor_type="HUMAIN", action="X",
                 company_id=company.id, new_value={})
    # La chaîne de l'autre entreprise est vide et valide indépendamment.
    res = audit.verify_chain(db, other.id)
    assert res["valid"] is True
    assert res["checked"] == 0
    assert res["broken_at"] is None
    assert audit.verify_chain(db, company.id)["checked"] == 1


# ---------------------------------------------------------------------------
# Politique d'autonomie des agents
# ---------------------------------------------------------------------------

def _agent(level, scopes, cap=0):
    return models.User(
        email="agent@x", user_type="AGENT", autonomy_level=level,
        agent_scopes=scopes, max_action_quantity=cap, company_id=1,
    )


def test_read_only_agent_cannot_auto_execute():
    agent = _agent("read_only", "stock:read", cap=100)
    err = agent_policy.authorize_agent_action(
        agent, required_scope="restock:auto", required_level="auto", quantity=10)
    assert err is not None  # refusé (niveau insuffisant)


def test_propose_agent_blocked_from_auto_but_allowed_to_propose():
    agent = _agent("propose", "restock:propose,restock:auto", cap=100)
    # PROPOSE < AUTO -> exécution directe refusée.
    assert agent_policy.authorize_agent_action(
        agent, required_scope="restock:auto", required_level="auto", quantity=5) is not None
    # mais la proposition (niveau propose) passe.
    assert agent_policy.authorize_agent_action(
        agent, required_scope="restock:propose", required_level="propose") is None


def test_auto_agent_blocked_by_missing_scope():
    agent = _agent("auto", "stock:read", cap=100)
    err = agent_policy.authorize_agent_action(
        agent, required_scope="restock:auto", required_level="auto", quantity=5)
    assert err is not None and "Scope" in err


def test_auto_agent_blocked_by_quantity_cap():
    agent = _agent("auto", "restock:auto", cap=10)
    # 50 > plafond 10 -> refusé.
    assert agent_policy.authorize_agent_action(
        agent, required_scope="restock:auto", required_level="auto", quantity=50) is not None
    # 5 <= 10 -> autorisé.
    assert agent_policy.authorize_agent_action(
        agent, required_scope="restock:auto", required_level="auto", quantity=5) is None


def test_no_cap_means_no_autonomous_quantity():
    agent = _agent("auto", "restock:auto", cap=0)
    assert agent_policy.authorize_agent_action(
        agent, required_scope="restock:auto", required_level="auto", quantity=1) is not None


def test_human_rejected_from_agent_path():
    human = models.User(email="h@x", user_type="HUMAIN", company_id=1)
    err = agent_policy.authorize_agent_action(
        human, required_scope="stock:read", required_level="read_only")
    assert err is not None


def test_wildcard_scope_grants_domain():
    agent = _agent("auto", "restock:*", cap=100)
    assert agent_policy.has_scope(agent, "restock:auto") is True
    assert agent_policy.has_scope(agent, "stock:read") is False
