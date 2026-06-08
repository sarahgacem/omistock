# Guide de Contribution - OMISTOCK

Bienvenue sur le projet OMISTOCK ! Ce guide explique comment configurer et lancer le projet sur votre machine locale pour éviter tout bug.

## ⚙️ Configuration de l'environnement

1.  **Python** : Assurez-vous d'avoir Python 3.10 ou une version supérieure installée.
2.  **Dossier Backend** :
    ```bash
    cd backend
    python -m venv venv
    source venv/bin/activate  # Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```

## 🚀 Lancement du Projet

### 1. Démarrer le Serveur API
Depuis le dossier `backend` :
```bash
python main.py
```
*   Le serveur initialise automatiquement une base de données de test (`stock.db`) si elle n'existe pas.
*   L'API est accessible sur `http://localhost:8000`.

### 2. Accéder à l'Interface
*   Ouvrez le fichier `frontend/index.html` dans votre navigateur.
*   **Notes sur les ports** : Si le port 8000 est déjà utilisé, tuez le processus avec `taskkill /F /IM python.exe /T` (Windows) ou vérifiez vos terminaux ouverts.

## 🧪 Tests de Démonstration
Pour tester l'isolation multi-tenant :
- Utilisez **admin@test.com** pour l'entreprise A.
- Utilisez **food_admin@test.com** pour l'entreprise B.

## 📜 Structure du Projet
- `/backend` : Logique API, Modèles de données et Sécurité.
- `/frontend` : Interface utilisateur (HTML/JS/CSS).
- `/docs` : Documentation supplémentaire.
