# OMISTOCK - Système de Gestion de Stock Intelligent

OMISTOCK est une plateforme web moderne de gestion d'inventaire multi-tenant, conçue pour les entreprises multisites. Elle permet un suivi précis des stocks, des ventes et des rapports financiers en temps réel.

## 🚀 Fonctionnalités Clés

- **Dashboard Dynamique** : Visualisation instantanée des KPIs (Valeur du stock, alertes, ventes).
- **Gestion Multi-sites** : Support natif pour plusieurs filiales (ex: Alger, Oran, Constantine) avec isolation des données.
- **Inventaire Universel** : Adapté à tout type de secteur (Électronique, Pharmacie, Alimentaire, etc.).
- **Rapports & Analyses** : Graphiques avancés avec Chart.js et calcul de bénéfices.
- **Exportation Professionnelle** : Génération de factures HTML et export de rapports au format PDF.
- **Sécurité Multi-Tenant** : Authentification JWT avec isolation stricte par entreprise (Company ID).

## 🛠️ Stack Technique

- **Backend** : FastAPI (Python 3.10+), SQLAlchemy (ORM), SQLite.
- **Frontend** : Vanilla JS, TailwindCSS, Chart.js.
- **Authentification** : OAuth2 avec Password flow et jetons JWT.

## 📦 Installation

Consultez le fichier [Installation Rapide](docs/installation.md) pour les instructions détaillées.

# OMISTOCK - Système de Gestion de Stock Intelligent

Ce dépôt contient la version finale propre et refactorisée du projet **OMISTOCK** (Application Web, Mobile PWA et Mémoire) pour la soutenance.

## 🚀 Lancement rapide avec Docker

Pour faciliter l'évaluation et garantir un environnement d'exécution strictement identique, l'application a été entièrement conteneurisée.

### Prérequis
* **Docker Desktop** installé et démarré sur votre machine.

### Procédure de lancement
1. Ouvrez un terminal à la racine du projet `omistock/`.
2. Exécutez la commande suivante pour construire et lancer l'environnement unifié :
```bash
   docker compose up --build
