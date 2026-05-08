
import os
import sys

# Ajouter le chemin du backend pour l'import des modèles
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine
import models, security
from sqlalchemy.orm import Session

def seed():
    # S'assurer que les tables existent
    models.Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    
    try:
        # Nettoyage
        print("Nettoyage des anciennes données...")
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

        # 1. Entreprise
        company = models.Company(name="SANTÉ PRO ALGERIE")
        db.add(company)
        db.commit()
        db.refresh(company)

        # 2. Filiales
        b_alger = models.Branch(name="Dépôt Alger", city="Alger", company_id=company.id)
        b_oran = models.Branch(name="Dépôt Oran", city="Oran", company_id=company.id)
        db.add_all([b_alger, b_oran])
        db.commit()
        db.refresh(b_alger)
        db.refresh(b_oran)

        # 3. Admin
        admin = models.User(
            email="admin@test.com",
            hashed_password=security.get_password_hash("password123"),
            company_id=company.id,
            branch_id=b_alger.id
        )
        db.add(admin)

        # 4. Fournisseurs
        s1 = models.Supplier(name="Saidal Group", email="contact@saidal.dz", company_id=company.id)
        s2 = models.Supplier(name="Biopharm", email="info@biopharm.com", company_id=company.id)
        s3 = models.Supplier(name="Indusdz", email="sales@indusdz.dz", company_id=company.id)
        db.add_all([s1, s2, s3])
        db.commit()
        db.refresh(s1)
        db.refresh(s2)
        db.refresh(s3)

            
            # MATÉRIEL
            {"name": "Stéthoscope Littmann", "sku": "MAT-STE-LIT", "price": 18000.0, "qty": 8, "min": 2, "cat": "Matériel", "sid": s2.id},
            {"name": "Tensiomètre Bras", "sku": "MAT-TEN-BRA", "price": 6500.0, "qty": 3, "min": 5, "cat": "Matériel", "sid": s2.id},
            {"name": "Oxymètre de pouls", "sku": "MAT-OXY-POU", "price": 2500.0, "qty": 50, "min": 15, "cat": "Matériel", "sid": s2.id},
            {"name": "Thermomètre Infrarouge", "sku": "MAT-THE-INF", "price": 3500.0, "qty": 15, "min": 10, "cat": "Matériel", "sid": s1.id},
            {"name": "Gants en Latex (Boîte)", "sku": "MAT-GAN-LAT", "price": 1200.0, "qty": 100, "min": 40, "cat": "Matériel", "sid": s1.id},
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

        # 6. Inventaire et Mouvements
        print("Initialisation des stocks et mouvements...")
        for prod in products:
            # Répartir la quantité entre Alger et Oran
            q_alg = int(prod.quantity * 0.7)
            q_orn = prod.quantity - q_alg
            
            inv_alg = models.Inventory(branch_id=b_alger.id, product_id=prod.id, quantity=q_alg, min_threshold=prod.min_threshold)
            inv_orn = models.Inventory(branch_id=b_oran.id, product_id=prod.id, quantity=q_orn, min_threshold=prod.min_threshold)
            db.add_all([inv_alg, inv_orn])
            
            # Mouvement initial
            if prod.quantity > 0:
                mov = models.StockMovement(
                    product_id=prod.id,
                    branch_id=b_alger.id,
                    quantity=prod.quantity,
                    reason="Stock Initial",
                    movement_type="IN",
                    company_id=company.id
                )
                db.add(mov)

        db.commit()
        print("Seeding terminé avec succès !")

    except Exception as e:
        db.rollback()
        print(f"Erreur lors du seeding : {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
