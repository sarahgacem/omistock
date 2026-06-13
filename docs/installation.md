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
Le frontend est servi par le backend. Ouvrez dans votre navigateur :
`http://localhost:8000/app/index.html`

> Ne pas ouvrir le fichier en `file://` : le frontend détermine l'URL de l'API
> à partir de `window.location.origin` et doit donc être servi par le backend.

## 4. Comptes de Démonstration
Utilisez les boutons d'accès rapide sur la page de connexion ou les identifiants suivants :
- **Admin Pharmacie** : `admin@test.com` / `password123`
- **Admin Alimentaire** : `food_admin@test.com` / `password123`

## 5. Notes Techniques
- La base de données `stock.db` est automatiquement créée et peuplée au premier lancement.
- Si vous souhaitez réinitialiser les données, supprimez simplement le fichier `stock.db` et redémarrez le serveur.
