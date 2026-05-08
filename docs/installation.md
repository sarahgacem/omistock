# Installation Rapide d'OMISTOCK

Suivez ces étapes pour lancer le projet sur votre machine locale.

## 1. Prérequis
- Python 3.10 ou plus
- Navigateur web moderne

## 2. Configuration du Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Le serveur sera lancé sur `http://localhost:8000`.

## 3. Accès au Frontend
Ouvrez simplement le fichier `frontend/index.html` dans votre navigateur.

## 4. Comptes de Démonstration
Utilisez les boutons d'accès rapide sur la page de connexion ou les identifiants suivants :
- **Admin Pharmacie** : `admin@test.com` / `password123`
- **Admin Alimentaire** : `food_admin@test.com` / `password123`

## 5. Notes Techniques
- La base de données `stock.db` est automatiquement créée et peuplée au premier lancement.
- Si vous souhaitez réinitialiser les données, supprimez simplement le fichier `stock.db` et redémarrez le serveur.
