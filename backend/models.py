from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum

class ProductStatus(str, enum.Enum):
    NEW = "neuf"
    USED = "occasion"
    REFURBISHED = "reconditionné"

class Company(Base):
    """L'entreprise parente (ex: Le Groupe DTN)"""
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    branches = relationship("Branch", back_populates="company")
    products = relationship("Product", back_populates="company")

class Branch(Base):
    """Une filiale ou un site (ex: Boutique Paris, Boutique Oran)"""
    __tablename__ = "branches"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    city = Column(String)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    
    company = relationship("Company", back_populates="branches")
    users = relationship("User", back_populates="branch")
    inventory = relationship("Inventory", back_populates="branch")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=True)
    user_type = Column(String, default="HUMAIN") # 'HUMAIN' ou 'AGENT'
    api_key = Column(String, unique=True, nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    
    branch = relationship("Branch", back_populates="users")
    company = relationship("Company")

class Supplier(Base):
    """Les coordonnées des fournisseurs"""
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    contact_name = Column(String)
    email = Column(String)
    phone = Column(String)
    address = Column(String)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    
    company = relationship("Company")
    products = relationship("Product", back_populates="supplier")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")

class Product(Base):
    """La liste des articles partagée par toutes les filiales d'une même entreprise"""
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    sku = Column(String, index=True)
    barcode = Column(String, index=True)
    price = Column(Float, default=0.0)
    quantity = Column(Integer, default=0)
    min_threshold = Column(Integer, default=5)
    status = Column(String, default=ProductStatus.NEW)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    
    company = relationship("Company", back_populates="products")
    supplier = relationship("Supplier", back_populates="products")
    inventory = relationship("Inventory", back_populates="product")

class Inventory(Base):
    """Le stock spécifique à chaque filiale"""
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    branch_id = Column(Integer, ForeignKey("branches.id"))
    quantity = Column(Integer, default=0)
    min_threshold = Column(Integer, default=5)
    
    __table_args__ = (
        CheckConstraint('quantity >= 0', name='check_quantity_non_negative'),
    )
    
    product = relationship("Product", back_populates="inventory")
    branch = relationship("Branch", back_populates="inventory")

class StockMovement(Base):
    __tablename__ = "stock_movements"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    branch_id = Column(Integer, ForeignKey("branches.id"))
    quantity = Column(Integer)
    reason = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    movement_type = Column(String, default="IN")  # 'IN' ou 'OUT'

class OrderStatus(str, enum.Enum):
    DRAFT = "brouillon"
    SENT = "envoyé"
    RECEIVED = "reçu"
    CANCELLED = "annulé"

class PurchaseOrder(Base):
    """Les bons de commande passés aux fournisseurs"""
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, index=True)
    date = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, default=OrderStatus.DRAFT)
    total_amount = Column(Float, default=0.0)
    
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    
    supplier = relationship("Supplier", back_populates="purchase_orders")
    company = relationship("Company")
    items = relationship("PurchaseOrderItem", back_populates="purchase_order")

class PurchaseOrderItem(Base):
    """Lignes d'un bon de commande"""
    __tablename__ = "purchase_order_items"
    id = Column(Integer, primary_key=True, index=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer)
    unit_price = Column(Float)
    
    purchase_order = relationship("PurchaseOrder", back_populates="items")
    product = relationship("Product")

class Customer(Base):
    """Clients de l'entreprise"""
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String)
    phone = Column(String)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    
    company = relationship("Company")
    sales = relationship("Sale", back_populates="customer")

class Sale(Base):
    """Enregistrement d'une vente (facture)"""
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime(timezone=True), server_default=func.now())
    total_amount = Column(Float, default=0.0)
    
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    
    customer = relationship("Customer", back_populates="sales")
    company = relationship("Company")
    branch = relationship("Branch")
    items = relationship("SaleItem", back_populates="sale")

class SaleItem(Base):
    """Lignes d'une vente"""
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer)
    unit_price = Column(Float)
    
    sale = relationship("Sale", back_populates="items")
    product = relationship("Product")

class ActivityLog(Base):
    """Journalisation des actions utilisateurs"""
    __tablename__ = "activity_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    
    user = relationship("User")
    company = relationship("Company")

class AuditLog(Base):
    """Traçabilité des modifications de stock et ventes"""
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    
    user = relationship("User")
    company = relationship("Company")

class TransferStatus(str, enum.Enum):
    PENDING = "en_attente"
    APPROVED = "approuvé"
    CONFIRMED = "confirmé"
    REJECTED = "rejeté"

class TransferRequest(Base):
    """Demandes de transfert de stock entre dépôts"""
    __tablename__ = "transfer_requests"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    from_branch_id = Column(Integer, ForeignKey("branches.id"))
    to_branch_id = Column(Integer, ForeignKey("branches.id"))
    quantity = Column(Integer)
    status = Column(String, default=TransferStatus.PENDING)
    requester_id = Column(Integer, ForeignKey("users.id"))
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)

    product = relationship("Product")
    from_branch = relationship("Branch", foreign_keys=[from_branch_id])
    to_branch = relationship("Branch", foreign_keys=[to_branch_id])
    requester = relationship("User", foreign_keys=[requester_id])
    approver = relationship("User", foreign_keys=[approver_id])

