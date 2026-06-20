
import os
import sys
from datetime import datetime, timedelta, timezone

# Ajouter le chemin du backend pour l'import des modèles
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine
import models, security
from sqlalchemy.orm import Session

def seed(admin_only=False):
    # S'assurer que les tables existent
    models.Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    
    try:
        # 1. Nettoyage Complet
        print("Nettoyage des anciennes données...")
        db.query(models.ActivityLog).delete()
        db.query(models.StockMovement).delete()
        db.query(models.SaleItem).delete()
        db.query(models.Sale).delete()
        db.query(models.Customer).delete()
        db.query(models.Inventory).delete()
        db.query(models.Product).delete()
        db.query(models.Supplier).delete()
        db.query(models.User).delete()
        db.query(models.Branch).delete()
        db.query(models.Company).delete()
        db.commit()

        # 2. Création de l'Entreprise
        print("Création de l'entreprise : OMISTOCK BUSINESS SOLUTIONS...")
        company = models.Company(name="OMISTOCK BUSINESS SOLUTIONS")
        db.add(company)
        db.commit()
        db.refresh(company)

        # 3. Création des Filiales
        print("Création des dépôts Alger et Oran...")
        b_alger = models.Branch(name="Dépôt Alger", city="Alger", company_id=company.id)
        b_oran = models.Branch(name="Dépôt Oran", city="Oran", company_id=company.id)
        db.add_all([b_alger, b_oran])
        db.commit()
        db.refresh(b_alger)
        db.refresh(b_oran)

        # 4. Création des Administrateurs
        print("Création des comptes administrateurs (Alger, Oran, Constantine)...")
        admin = models.User(
            email="admin@test.com",
            hashed_password=security.get_password_hash("password123"),
            company_id=company.id,
            branch_id=b_alger.id,
            user_type="ADMIN"
        )
        oran_admin = models.User(
            email="oran@test.com",
            hashed_password=security.get_password_hash("password123"),
            company_id=company.id,
            branch_id=b_oran.id,
            user_type="ADMIN"
        )
        db.add_all([admin, oran_admin])
        
        # Deuxième entreprise
        print("Création de l'entreprise AGRO-INDUSTRIE DZ...")
        company2 = models.Company(name="AGRO-INDUSTRIE DZ")
        db.add(company2)
        db.commit()
        db.refresh(company2)
        
        b_const = models.Branch(name="Dépôt Constantine", city="Constantine", company_id=company2.id)
        db.add(b_const)
        db.commit()
        db.refresh(b_const)
        
        food_admin = models.User(
            email="food_admin@test.com",
            hashed_password=security.get_password_hash("password123"),
            company_id=company2.id,
            branch_id=b_const.id,
            user_type="ADMIN"
        )
        db.add(food_admin)
        db.commit()

        if admin_only:
            print("Auto-seed (Admin only) terminé avec succès !")
            db.commit()
            return

        # 5. Création des Fournisseurs (Saidal en priorité)
        print("Ajout des fournisseurs (Saidal Group)...")
        s_saidal = models.Supplier(name="Saidal Group", email="contact@saidal.dz", company_id=company.id)
        s_biopharm = models.Supplier(name="Biopharm", email="info@biopharm.com", company_id=company.id)
        db.add_all([s_saidal, s_biopharm])
        db.commit()
        db.refresh(s_saidal)
        # 6. Création des Produits Universels (IT, Santé, Agro)
        print("Ajout du catalogue universel...")
        products_data = [
            # Produits existants
            {"name": "Ordinateur Portable HP Victus", "sku": "IT-HP-VCT", "price": 145000.0, "qty": 450, "min": 100, "sid": s_saidal.id},
            {"name": "Serveur Dell PowerEdge", "sku": "IT-DEL-SRV", "price": 450000.0, "qty": 120, "min": 50, "sid": s_saidal.id},
            {"name": "Doliprane 500mg (Boîte 16)", "sku": "PHA-DOL-500", "price": 250.0, "qty": 500, "min": 100, "sid": s_saidal.id},
            {"name": "Huile de Tournesol 5L", "sku": "AGR-HUI-5L", "price": 1200.0, "qty": 300, "min": 50, "sid": s_biopharm.id},
            {"name": "Café Robusta 250g", "sku": "AGR-CAF-250", "price": 450.0, "qty": 200, "min": 30, "sid": s_saidal.id},
            {"name": "Smartphone Galaxy S21", "sku": "IT-GAL-S21", "price": 85000.0, "qty": 150, "min": 40, "sid": s_saidal.id},
            
            # Nouveaux produits cosmétiques
            {"name": "Écran Solaire SPF50+", "sku": "COS-SUN-50", "price": 1800.0, "qty": 300, "min": 50, "sid": s_biopharm.id},
            {"name": "Sérum Anti-âge Acide Hyaluronique", "sku": "COS-SER-AH", "price": 3500.0, "qty": 120, "min": 20, "sid": s_biopharm.id},
            {"name": "Crème Hydratante Visage 50ml", "sku": "COS-CRE-HYD", "price": 2200.0, "qty": 250, "min": 30, "sid": s_biopharm.id},
            {"name": "Lotion Tonique Apaisante", "sku": "COS-LOT-APA", "price": 1500.0, "qty": 180, "min": 25, "sid": s_biopharm.id},
            {"name": "Masque Purifiant Argile", "sku": "COS-MAS-ARG", "price": 1200.0, "qty": 200, "min": 40, "sid": s_biopharm.id},
            {"name": "Gel Nettoyant Visage", "sku": "COS-GEL-NET", "price": 1400.0, "qty": 300, "min": 50, "sid": s_biopharm.id},
            {"name": "Gommage Exfoliant Doux", "sku": "COS-GOM-EXF", "price": 1700.0, "qty": 150, "min": 20, "sid": s_biopharm.id},
            {"name": "Eau Micellaire Démaquillante", "sku": "COS-EAU-MIC", "price": 1100.0, "qty": 400, "min": 60, "sid": s_biopharm.id},
            {"name": "Baume à Lèvres Réparateur", "sku": "COS-BAU-LEV", "price": 600.0, "qty": 500, "min": 100, "sid": s_biopharm.id},
            {"name": "Shampooing Fortifiant", "sku": "COS-SHA-FOR", "price": 1300.0, "qty": 220, "min": 40, "sid": s_biopharm.id},
            {"name": "Après-shampooing Nourrissant", "sku": "COS-APR-NOU", "price": 1400.0, "qty": 200, "min": 30, "sid": s_biopharm.id},
            {"name": "Huile Sèche Multi-Usages", "sku": "COS-HUI-SEC", "price": 2800.0, "qty": 100, "min": 15, "sid": s_biopharm.id},
            {"name": "Déodorant Bille 24h", "sku": "COS-DEO-BIL", "price": 800.0, "qty": 350, "min": 50, "sid": s_biopharm.id},
            {"name": "Lait Corps Hydratant 400ml", "sku": "COS-LAI-COR", "price": 1900.0, "qty": 280, "min": 40, "sid": s_biopharm.id},
            {"name": "Sérum Vitamine C Éclat", "sku": "COS-SER-VIT", "price": 4200.0, "qty": 80, "min": 10, "sid": s_biopharm.id},
            {"name": "Crème Contour des Yeux", "sku": "COS-CRE-YEU", "price": 2500.0, "qty": 110, "min": 20, "sid": s_biopharm.id},
        ]

        products = []
        for p in products_data:
            prod = models.Product(
                name=p["name"],
                sku=p["sku"],
                price=p["price"],
                quantity=p["qty"],
                min_threshold=p["min"],
                company_id=company.id,
                supplier_id=p["sid"]
            )
            db.add(prod)
            products.append(prod)
        db.commit()
        for p in products: db.refresh(p)

        # 7. Initialisation des Stocks et Inventaires
        print("Répartition du stock entre Alger et Oran...")
        for p in products:
            # Répartition 70% Alger / 30% Oran
            q_alg = int(p.quantity * 0.7)
            q_orn = p.quantity - q_alg
            
            inv_alg = models.Inventory(branch_id=b_alger.id, product_id=p.id, quantity=q_alg, min_threshold=p.min_threshold)
            inv_orn = models.Inventory(branch_id=b_oran.id, product_id=p.id, quantity=q_orn, min_threshold=p.min_threshold)
            db.add_all([inv_alg, inv_orn])
            
            # Mouvement initial (Entrée)
            mov = models.StockMovement(
                product_id=p.id,
                branch_id=b_alger.id,
                quantity=p.quantity,
                reason="Réception Stock Initial",
                movement_type="IN",
                company_id=company.id,
                created_at=datetime.now(timezone.utc) - timedelta(days=2)
            )
            db.add(mov)

        # 8. Transactions entre Alger et Oran (Transfert)
        print("Simulation d'un transfert Alger -> Oran...")
        # Transférer 50 Doliprane d'Alger vers Oran
        doliprane = products[0]
        transfer_qty = 50
        
        # Sortie d'Alger
        mov_out = models.StockMovement(
            product_id=doliprane.id,
            branch_id=b_alger.id,
            quantity=-transfer_qty,
            reason="Transfert vers Oran",
            movement_type="OUT",
            company_id=company.id
        )
        # Entrée à Oran
        mov_in = models.StockMovement(
            product_id=doliprane.id,
            branch_id=b_oran.id,
            quantity=transfer_qty,
            reason="Réception de Alger",
            movement_type="IN",
            company_id=company.id
        )
        db.add_all([mov_out, mov_in])

        # 9. Statistiques de Performance (Ventes Saidal)
        print("Simulation de ventes pour générer des statistiques...")
        customer = models.Customer(name="Pharmacie El-Chifa", company_id=company.id)
        db.add(customer)
        db.commit()
        db.refresh(customer)

        # Ventes sur les 5 derniers jours pour le graphique
        for i in range(5):
            sale_date = datetime.now(timezone.utc) - timedelta(days=i)
            # Vente d'un produit Saidal (Doliprane ou Amoxicilline)
            p_saidal = products[i % 2] 
            sale = models.Sale(
                customer_id=customer.id,
                company_id=company.id,
                branch_id=b_alger.id,
                total_amount=p_saidal.price * 10,
                date=sale_date
            )
            db.add(sale)
            db.commit()
            db.refresh(sale)
            
            item = models.SaleItem(
                sale_id=sale.id,
                product_id=p_saidal.id,
                quantity=10,
                unit_price=p_saidal.price
            )
            db.add(item)
            
            # Déduire du stock (Mouvement OUT)
            mov_sale = models.StockMovement(
                product_id=p_saidal.id,
                branch_id=b_alger.id,
                quantity=-10,
                reason="Vente client",
                movement_type="OUT",
                company_id=company.id,
                created_at=sale_date
            )
            db.add(mov_sale)

        db.commit()
        print("Seeding terminé avec succès !")

    except Exception as e:
        db.rollback()
        print(f"Erreur lors du seeding : {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
