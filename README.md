# OMISTOCK - Système de Gestion de Stock Intelligent

OMISTOCK est une plateforme web de gestion d'inventaire multi-tenant, conçue pour les entreprises multisites. Elle permet un suivi des stocks, des ventes et des rapports, avec une application mobile (PWA) et un serveur MCP pour l'analyse des données.

## 🚀 Fonctionnalités Clés

- **Dashboard Dynamique** : KPIs (valeur du stock, alertes, quantités) et graphiques Chart.js.
- **Gestion Multi-sites** : Plusieurs filiales (ex: Alger, Oran, Constantine) avec isolation des données par entreprise.
- **Inventaire par dépôt** : Stock géré par filiale, transferts inter-dépôts.
- **Rapports** : Visualisation des indicateurs et impression de factures HTML.
- **Sécurité Multi-Tenant** : Authentification JWT avec isolation par entreprise (Company ID).
- **PWA Mobile** : Scan de codes-barres et installation sur mobile.
- **Serveur MCP** : Outils d'analyse (alertes de stock, résumé business) consommables par un LLM.

## 🛠️ Stack Technique

- **Backend** : FastAPI (Python 3.10+), SQLAlchemy (ORM), SQLite.
- **Frontend** : Vanilla JS, TailwindCSS, Chart.js (servi par le backend sous `/app`).
- **Authentification** : OAuth2 password flow + jetons JWT.
- **MCP** : `mcp` (FastMCP) — voir `mcp/server.py`.

## 📦 Installation & Lancement

> Prérequis : Python 3.10+.

```bash
# 1. Installer les dépendances
cd backend
python -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt

# 2. Lancer le serveur (API + frontend)
python main.py                  # équivaut à : uvicorn main:app --host 0.0.0.0 --port 8000
```

La base `stock.db` est créée et peuplée automatiquement au premier démarrage.

## 🌐 Accès à l'application

Le frontend est servi par le backend. Ouvrez dans votre navigateur :

```
http://localhost:8000/app/index.html
```

> Important : l'application doit être ouverte via cette URL (et non en `file://`),
> car le frontend détermine l'URL de l'API à partir de `window.location.origin`.

### Comptes de démonstration
- **Admin Pharmacie/Tech** : `admin@test.com` / `password123`
- **Admin Alimentation** : `food_admin@test.com` / `password123`

## 🤖 Serveur MCP

Le serveur MCP fonctionnel se trouve dans `mcp/server.py`. Il lit la base `stock.db`
et expose des outils d'analyse (`analyze_stock`, `get_business_summary`).

```bash
pip install -r backend/requirements.txt   # inclut la dépendance `mcp`
python mcp/server.py
```

## 📚 Documentation

Voir [docs/installation.md](docs/installation.md) pour les détails d'installation.
