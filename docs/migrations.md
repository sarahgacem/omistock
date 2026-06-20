# Gestion du schéma & migrations — OMISTOCK

## État actuel (assumé, transitoire)

Au démarrage, `backend/main.py` exécute deux étapes :

1. `models.Base.metadata.create_all(bind=engine)` — crée les tables manquantes.
2. `run_db_migrations()` — ajoute de façon **idempotente** les colonnes introduites
   par le refactor sur une base existante, via des `ALTER TABLE ... ADD COLUMN`
   protégés par `try/except` (l'exception « colonne déjà présente » est ignorée).

Cette approche « additive best-effort » est volontairement simple parce que :

- le moteur de dev/POC est **SQLite**, dont le `ALTER TABLE` est limité
  (pas de `DROP COLUMN`, pas de modification de type/contrainte en place) ;
- les changements du refactor sont **purement additifs** (nouvelles colonnes
  avec valeurs par défaut, nouvelles tables), donc sûrs à rejouer.

### Limites connues (à ne pas masquer)
- Pas de **versionnage** des migrations ni d'historique : impossible de connaître
  l'état exact d'une base, ni de faire un *downgrade*.
- Les modifications **non additives** (renommer/supprimer une colonne, changer un
  type, ajouter une contrainte sur données existantes) ne sont **pas** gérées.
- Le `except Exception` large peut masquer une vraie erreur d'`ALTER` autre que
  « colonne déjà présente ».

## Cible recommandée : Alembic

Pour la production, remplacer l'auto-migration par **Alembic** (migrations
versionnées, réversibles, traçables) :

```bash
pip install alembic
alembic init migrations
```

`migrations/env.py` :

```python
from database import Base, SQLALCHEMY_DATABASE_URL
import models  # noqa: F401  (enregistre tous les modèles sur Base.metadata)

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)
```

Workflow :

```bash
alembic revision --autogenerate -m "ajout WAC, lots, audit chaîné, gouvernance agents"
alembic upgrade head      # appliquer
alembic downgrade -1      # revenir en arrière
```

Une fois Alembic en place :

1. Supprimer `run_db_migrations()` de `main.py` et le `create_all` au boot.
2. Faire de `alembic upgrade head` une étape de déploiement explicite
   (et non un effet de bord du démarrage applicatif).
3. Pour SQLite, activer le mode *batch* d'Alembic afin de contourner les limites
   d'`ALTER TABLE` (recréation de table transparente) :

   ```python
   with op.batch_alter_table("products") as batch:
       batch.add_column(sa.Column("cost_price", sa.Float(), server_default="0"))
   ```

## En attendant

- Garder les changements de schéma **additifs** tant qu'Alembic n'est pas en place.
- Documenter chaque nouvelle colonne dans `run_db_migrations()` (déjà le cas).
- Pour réduire le risque du `except` large, restreindre l'exception attendue au
  message « duplicate column » plutôt que d'avaler toute exception.
