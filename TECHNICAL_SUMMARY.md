# Résumé Technique : OMNISTOCK ERP

## 1. Architecture Multi-Tenant
OMNISTOCK utilise une architecture multi-tenant robuste basée sur l'isolation des données au niveau logiciel via une colonne `company_id` présente dans toutes les tables critiques.
- **Isolation Stricte** : Chaque requête API filtre systématiquement les données par le `company_id` extrait du token JWT de l'utilisateur.
- **Middleware de Sécurité** : Un middleware FastAPI intercepte les requêtes `PUT` et `DELETE` pour vérifier que l'utilisateur a le droit de modifier la ressource demandée.
- **Indépendance des Données** : Deux entreprises différentes (ex: Pharmacie vs Alimentation) sont totalement étanches, avec leurs propres stocks, clients et historiques.

## 2. Fonctionnalités Clés
1. **Gestion Multi-Filiales** : Centralisation des stocks tout en permettant une gestion granulaire par dépôt ou boutique (ex: Alger vs Oran).
2. **Transferts Inter-Filiales Sécurisés** : Déplacement de stock atomique (Transaction ACID) avec vérification d'appartenance à la même entreprise.
3. **Module de Vente & Facturation** : Génération de factures HTML professionnelles et suivi des ventes en temps réel.
4. **Journaux d'Activité (Audit)** : Traçabilité complète des actions (connexions, ventes, transferts) pour une transparence totale.
5. **Serveur MCP (Model Context Protocol)** : Exposition d'outils d'analyse (alertes de stock, résumé business) consommables par un LLM. L'analyse et les recommandations sont produites par le LLM en aval ; le serveur MCP fournit les données.

## 3. Stack Technique
- **Backend** : FastAPI (Python 3.13) pour une API asynchrone haute performance.
- **Base de Données** : SQLite avec SQLAlchemy (ORM) pour la gestion des relations et des contraintes (CHECK, Index).
- **Sécurité** : JWT (JSON Web Tokens) pour l'authentification et passlib (bcrypt) pour le hachage des mots de passe.
- **Frontend** : Vanilla HTML/JS avec TailwindCSS pour une interface premium, réactive et sans framework lourd.

## 4. Schéma de la Base de Données

```mermaid
erDiagram
    COMPANY ||--o{ BRANCH : "possède"
    COMPANY ||--o{ PRODUCT : "gère"
    COMPANY ||--o{ USER : "emploie"
    COMPANY ||--o{ ACTIVITY_LOG : "archive"
    COMPANY ||--o{ CUSTOMER : "sert"
    COMPANY ||--o{ SALE : "réalise"
    
    BRANCH ||--o{ USER : "héberge"
    BRANCH ||--o{ INVENTORY : "stocke"
    BRANCH ||--o{ SALE : "effectue"
    
    PRODUCT ||--o{ INVENTORY : "est présent dans"
    PRODUCT ||--o{ SALE_ITEM : "est vendu"
    
    SALE ||--o{ SALE_ITEM : "contient"
    CUSTOMER ||--o{ SALE : "achète"
    USER ||--o{ ACTIVITY_LOG : "génère"

    COMPANY {
        int id
        string name
    }
    BRANCH {
        int id
        string name
        int company_id
    }
    USER {
        int id
        string email
        int company_id
        int branch_id
    }
    PRODUCT {
        int id
        string name
        int company_id
    }
    INVENTORY {
        int id
        int product_id
        int branch_id
        int quantity
    }
    ACTIVITY_LOG {
        int id
        int user_id
        int company_id
        string action
        datetime timestamp
    }
    SALE {
        int id
        int company_id
        int customer_id
        float total_amount
    }
```

## 5. Architecture MCP (réelle)

Le serveur MCP fonctionnel est `mcp/server.py`. Il s'agit d'une implémentation
unique basée sur **FastMCP** qui lit directement la base SQLite `stock.db`.

- **Outils exposés** :
  - `analyze_stock(company_id)` : liste les produits sous le seuil pour une entreprise.
  - `get_business_summary(company_id)` : résumé des ventes (jour/total) et des transferts.
- **Flux** : `LLM (client MCP) → mcp/server.py → SQLite (stock.db)`.
- **Isolation** : le `company_id` est passé en paramètre des outils.
- **Dépendance** : `mcp` (déclarée dans `mcp/requirements.txt`, environnement séparé du backend).

> Note : l'analyse et les recommandations sont générées par le LLM en aval ;
> le serveur MCP se limite à fournir des données factuelles.
