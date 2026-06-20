"""
Configuration partagée des tests OMISTOCK.

Stratégie d'isolation :
- On force une base SQLite TEMPORAIRE par session via OMISTOCK_DB_PATH avant
  d'importer les modules (qui lisent l'env au moment de l'import).
- On force OMISTOCK_ENV=dev pour autoriser la clé de signature éphémère.
- Les modules backend utilisent des imports "plats" (import models, import stock,
  ...), donc on ajoute le dossier backend/ au sys.path.
- Chaque test reçoit une session propre ; les tables sont créées une fois et la
  base est nettoyée entre les tests pour l'indépendance.
"""
import os
import sys
import tempfile

import pytest

# --- 1. Environnement AVANT tout import des modules backend -------------------
_TMP_DB = os.path.join(tempfile.gettempdir(), "omistock_test.db")
os.environ["OMISTOCK_ENV"] = "dev"
os.environ["OMISTOCK_DB_PATH"] = _TMP_DB
os.environ.setdefault("OMISTOCK_SECRET_KEY", "TEST_ONLY_secret_key_not_for_prod")

# --- 2. sys.path : rendre les modules backend importables à plat --------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
_ROOT_DIR = os.path.dirname(_BACKEND_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import models  # noqa: E402
from database import Base, engine, SessionLocal  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    """Crée le schéma une fois pour la session de test, sur une base neuve."""
    if os.path.exists(_TMP_DB):
        os.remove(_TMP_DB)
    Base.metadata.create_all(bind=engine)
    yield
    # Nettoyage best-effort en fin de session.
    try:
        if os.path.exists(_TMP_DB):
            os.remove(_TMP_DB)
    except OSError:
        pass


@pytest.fixture()
def db():
    """Session SQLAlchemy isolée ; purge toutes les tables avant chaque test."""
    session = SessionLocal()
    # Purge ordonnée (respect des FK) avant chaque test.
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def company(db):
    c = models.Company(name="ACME Test")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture()
def branch(db, company):
    b = models.Branch(name="Dépôt Central", city="Alger", company_id=company.id)
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@pytest.fixture()
def human(db, company, branch):
    u = models.User(
        email="manager@acme.test",
        hashed_password="x",
        user_type="HUMAIN",
        company_id=company.id,
        branch_id=branch.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def product(db, company):
    p = models.Product(
        name="Widget",
        sku="W-1",
        price=10.0,
        cost_price=0.0,
        quantity=0,
        min_threshold=5,
        company_id=company.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p
