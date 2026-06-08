import os, sys
# Fix: Ajouter le dossier backend au path pour permettre les imports quand on lance depuis la racine
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine
import models, security
from sqlalchemy.sql import func

def init_db():
    # Créer les tables si elles n'existent pas
    models.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    # Nettoyage pour repartir sur du propre pour la démo Pharma
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

    # 1. Création de l'Entreprise Mère
    print("Création de OMISTOCK BUSINESS SOLUTIONS...")
    company = models.Company(name="OMISTOCK BUSINESS SOLUTIONS")
    db.add(company)
    db.commit()
    db.refresh(company)
    
    # 2. Création des Filiales (Branches)
    print("Création des filiales...")
    b_alger = models.Branch(name="Dépôt Central Alger", city="Alger", company_id=company.id)
    b_oran = models.Branch(name="Unité Oran", city="Oran", company_id=company.id)
    db.add_all([b_alger, b_oran])
    db.commit()
    db.refresh(b_alger)
    db.refresh(b_oran)

    # 3. Création des utilisateurs
    print("Création des utilisateurs...")
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
    db.commit()
    
    # 4. Création des Fournisseurs
    print("Création des fournisseurs...")
    s_saidal = models.Supplier(name="Saidal", contact_name="Direction", email="contact@saidal.dz", company_id=company.id)
    s_biopharm = models.Supplier(name="Biopharm", contact_name="Logistique", email="supply@biopharm.com", company_id=company.id)
    db.add_all([s_saidal, s_biopharm])
    db.commit()
    db.refresh(s_saidal)
    db.refresh(s_biopharm)

    # 5. Création du Catalogue Produits
    print("Ajout du catalogue...")
    p1 = models.Product(name="Doliprane 500mg", sku="PHA-DOL-500", barcode="1001", price=220.0, min_threshold=100, company_id=company.id, supplier_id=s_saidal.id)
    p2 = models.Product(name="Amoxicilline 1g", sku="PHA-AMO-1G", barcode="1002", price=680.0, min_threshold=50, company_id=company.id, supplier_id=s_saidal.id)
    p3 = models.Product(name="Insuline Glargine", sku="PHA-INS-GLA", barcode="1003", price=4500.0, min_threshold=20, company_id=company.id, supplier_id=s_biopharm.id)
    p4 = models.Product(name="Lovenox 4000 UI", sku="PHA-LOV-40", barcode="1004", price=2500.0, min_threshold=20, company_id=company.id, supplier_id=s_biopharm.id)
    p5 = models.Product(name="Écran Solaire Vénus", sku="COS-VEN-SOL", barcode="2001", price=1200.0, min_threshold=30, company_id=company.id, supplier_id=s_saidal.id)
    p6 = models.Product(name="Shampooing Swalis", sku="COS-SWA-SHA", barcode="2002", price=450.0, min_threshold=40, company_id=company.id, supplier_id=s_saidal.id)
    p7 = models.Product(name="Gants Stériles", sku="MAT-GLO-ST", barcode="3001", price=1200.0, min_threshold=50, company_id=company.id, supplier_id=s_biopharm.id)
    
    db.add_all([p1, p2, p3, p4, p5, p6, p7])
    db.commit()
    db.refresh(p1)
    db.refresh(p2)
    db.refresh(p3)
    db.refresh(p4)
    db.refresh(p5)
    db.refresh(p6)
    db.refresh(p7)

    # 6. Création des Clients
    print("Création des clients de test...")
    c1 = models.Customer(name="Pharmacie Centrale Alger", email="contact@pharmacie-centrale.dz", phone="021000000", company_id=company.id)
    c2 = models.Customer(name="Clinique Es-Saada", email="contact@clinique-essaada.dz", phone="041000000", company_id=company.id)
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)

    # 7. État Initial des Stocks (Inventaire par Branche)
    print("Initialisation des stocks par branche...")
    # Alger
    inv1_alg = models.Inventory(branch_id=b_alger.id, product_id=p1.id, quantity=100)  # Doliprane 100
    inv2_alg = models.Inventory(branch_id=b_alger.id, product_id=p2.id, quantity=200)  # Amoxicilline
    inv3_alg = models.Inventory(branch_id=b_alger.id, product_id=p3.id, quantity=15)   # Insuline (ALERTE)
    inv4_alg = models.Inventory(branch_id=b_alger.id, product_id=p4.id, quantity=50)   # Lovenox
    inv7_alg = models.Inventory(branch_id=b_alger.id, product_id=p7.id, quantity=100)  # Gants
    
    # Oran
    inv1_orn = models.Inventory(branch_id=b_oran.id, product_id=p1.id, quantity=0)    # Doliprane 0 (RUPTURE)
    inv5_orn = models.Inventory(branch_id=b_oran.id, product_id=p5.id, quantity=100)  # Écran
    inv6_orn = models.Inventory(branch_id=b_oran.id, product_id=p6.id, quantity=80)   # Shampooing
    inv7_orn = models.Inventory(branch_id=b_oran.id, product_id=p7.id, quantity=30)   # Gants (ALERTE)
    
    db.add_all([inv1_alg, inv2_alg, inv3_alg, inv4_alg, inv7_alg, inv1_orn, inv5_orn, inv6_orn, inv7_orn])
    db.commit()

    # 8. Mouvements initiaux "IN"
    print("Enregistrement des mouvements initiaux...")
    m_in = [
        models.StockMovement(product_id=p1.id, branch_id=b_alger.id, quantity=100, reason="Stock initial", company_id=company.id, movement_type="IN"),
        models.StockMovement(product_id=p2.id, branch_id=b_alger.id, quantity=200, reason="Stock initial", company_id=company.id, movement_type="IN"),
        models.StockMovement(product_id=p3.id, branch_id=b_alger.id, quantity=15, reason="Stock initial", company_id=company.id, movement_type="IN"),
        models.StockMovement(product_id=p4.id, branch_id=b_alger.id, quantity=50, reason="Stock initial", company_id=company.id, movement_type="IN"),
        models.StockMovement(product_id=p7.id, branch_id=b_alger.id, quantity=100, reason="Stock initial", company_id=company.id, movement_type="IN"),
        # Oran n'a pas de Doliprane au départ
        models.StockMovement(product_id=p5.id, branch_id=b_oran.id, quantity=100, reason="Stock initial", company_id=company.id, movement_type="IN"),
        models.StockMovement(product_id=p6.id, branch_id=b_oran.id, quantity=80, reason="Stock initial", company_id=company.id, movement_type="IN"),
        models.StockMovement(product_id=p7.id, branch_id=b_oran.id, quantity=30, reason="Stock initial", company_id=company.id, movement_type="IN"),
    ]
    db.add_all(m_in)
    db.commit()

    # 9. Simulation de Transfert inter-filiales (DÉSACTIVÉ POUR LA DÉMO MANUELLE)
    print("Prêt pour la démo de transfert Alger -> Oran.")


    # 10. Simulation de Ventes
    print("Simulation de ventes...")
    # Vente 1 : Alger
    sale1 = models.Sale(customer_id=c1.id, company_id=company.id, branch_id=b_alger.id, total_amount=(30 * p2.price + 10 * p4.price))
    db.add(sale1)
    db.commit()
    db.refresh(sale1)
    
    si1 = models.SaleItem(sale_id=sale1.id, product_id=p2.id, quantity=30, unit_price=p2.price)
    si2 = models.SaleItem(sale_id=sale1.id, product_id=p4.id, quantity=10, unit_price=p4.price)
    db.add_all([si1, si2])
    
    m_out1 = models.StockMovement(product_id=p2.id, branch_id=b_alger.id, quantity=30, reason="Vente Client", company_id=company.id, movement_type="OUT")
    m_out2 = models.StockMovement(product_id=p4.id, branch_id=b_alger.id, quantity=10, reason="Vente Client", company_id=company.id, movement_type="OUT")
    db.add_all([m_out1, m_out2])
    
    inv2_alg.quantity -= 30
    inv4_alg.quantity -= 10

    # Vente 2 : Oran
    sale2 = models.Sale(customer_id=c2.id, company_id=company.id, branch_id=b_oran.id, total_amount=(15 * p5.price))
    db.add(sale2)
    db.commit()
    db.refresh(sale2)
    
    si3 = models.SaleItem(sale_id=sale2.id, product_id=p5.id, quantity=15, unit_price=p5.price)
    db.add(si3)
    
    m_out3 = models.StockMovement(product_id=p5.id, branch_id=b_oran.id, quantity=15, reason="Vente Client", company_id=company.id, movement_type="OUT")
    db.add(m_out3)
    
    inv5_orn.quantity -= 15

    db.commit()
    
    # 11. Mettre à jour la quantité globale dans la table Product pour le dashboard (somme des filiales)
    p1.quantity = inv1_alg.quantity + inv1_orn.quantity
    p2.quantity = inv2_alg.quantity
    p3.quantity = inv3_alg.quantity
    p4.quantity = inv4_alg.quantity
    p5.quantity = inv5_orn.quantity
    p6.quantity = inv6_orn.quantity
    p7.quantity = inv7_alg.quantity + inv7_orn.quantity
    db.commit()

    # --- 12. Création de la DEUXIÈME entreprise : AGRO-INDUSTRIE DZ ---
    print("Création de AGRO-INDUSTRIE DZ...")
    company2 = models.Company(name="AGRO-INDUSTRIE DZ")
    db.add(company2)
    db.commit()
    db.refresh(company2)

    # Filiale Constantine
    b_const = models.Branch(name="Dépôt Constantine", city="Constantine", company_id=company2.id)
    db.add(b_const)
    db.commit()
    db.refresh(b_const)

    # Admin Alimentation
    admin2 = models.User(
        email="food_admin@test.com",
        hashed_password=security.get_password_hash("password123"),
        company_id=company2.id,
        branch_id=b_const.id
    )
    db.add(admin2)
    db.commit()

    # Produits Alimentation
    print("Ajout du catalogue Alimentation...")
    pa1 = models.Product(name="Couscous 1kg", sku="ALI-COU-1K", barcode="5001", price=150.0, quantity=500, min_threshold=100, company_id=company2.id)
    pa2 = models.Product(name="Huile d'olive 1L", sku="ALI-HUI-1L", barcode="5002", price=950.0, quantity=120, min_threshold=30, company_id=company2.id)
    db.add_all([pa1, pa2])
    db.commit()

    # Inventaire Alimentation
    inv_pa1 = models.Inventory(branch_id=b_const.id, product_id=pa1.id, quantity=500)
    inv_pa2 = models.Inventory(branch_id=b_const.id, product_id=pa2.id, quantity=120)
    db.add_all([inv_pa1, inv_pa2])
    db.commit()

    db.close()
    print("Initialisation complète (Multi-Entreprise) terminée avec succès !")

if __name__ == "__main__":
    init_db()
