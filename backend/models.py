from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, DateTime, Enum,
    CheckConstraint, Boolean, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship, object_session
from sqlalchemy.ext.hybrid import hybrid_property
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
    commercial_register_number = Column(String, nullable=True)  # RC
    activity_sector = Column(String, nullable=True)
    nif = Column(String, nullable=True)
    address = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)

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


class AutonomyLevel(str, enum.Enum):
    """Niveaux d'autonomie pour les agents IA (du plus sûr au plus permissif)."""
    READ_ONLY = "read_only"          # Lecture seule (alertes, résumés, prédictions)
    SUGGEST = "suggest"              # Peut produire des suggestions/analyses
    PROPOSE = "propose"             # Peut créer des propositions soumises à validation humaine
    AUTO = "auto"                   # Peut exécuter directement (dans les limites de scope)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=True)
    user_type = Column(String, default="HUMAIN")  # 'HUMAIN' | 'AGENT' | 'ADMIN'
    api_key = Column(String, unique=True, nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    is_active = Column(Boolean, default=True)
    deletion_deadline = Column(DateTime(timezone=True), nullable=True)

    # --- Gouvernance des agents IA (best practice plateforme agent-ready) ---
    # Niveau d'autonomie (cf. AutonomyLevel). Par défaut : lecture seule (le plus sûr).
    autonomy_level = Column(String, default=AutonomyLevel.READ_ONLY.value)
    # Liste de scopes séparés par des virgules (ex: "stock:read,sales:read,transfer:propose")
    agent_scopes = Column(String, nullable=True)
    # Expiration de la clé API agent (rotation/expiry).
    api_key_expires_at = Column(DateTime(timezone=True), nullable=True)
    # Plafond quantité par action autonome (garde-fou pour niveau AUTO).
    max_action_quantity = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

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
    # Délai de livraison moyen (jours) — nécessaire au calcul du point de commande.
    lead_time_days = Column(Integer, default=7)
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
    # price = prix de VENTE (selling price)
    price = Column(Float, default=0.0)
    # cost_price = coût moyen pondéré (WAC) mis à jour à chaque réception.
    cost_price = Column(Float, default=0.0)
    # NOTE: `quantity` est conservée pour compatibilité ascendante MAIS n'est plus
    # la source de vérité. La quantité totale réelle est dérivée de Inventory
    # via la propriété hybride `total_quantity`. Voir repository.recompute_product_quantity.
    quantity = Column(Integer, default=0)
    # Seuil minimal de base (utilisé comme stock de sécurité si non calculé).
    min_threshold = Column(Integer, default=5)
    # Paramètres de réapprovisionnement (théorie de gestion de stock).
    safety_stock = Column(Integer, default=0)        # stock de sécurité
    avg_daily_demand = Column(Float, default=0.0)    # demande moyenne journalière (calculée)
    lead_time_days = Column(Integer, default=0)      # délai d'appro (sinon celui du fournisseur)
    status = Column(String, default=ProductStatus.NEW.value)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)

    company = relationship("Company", back_populates="products")
    supplier = relationship("Supplier", back_populates="products")
    inventory = relationship("Inventory", back_populates="product")
    lots = relationship("Lot", back_populates="product")

    @hybrid_property
    def total_quantity(self) -> int:
        """Quantité totale = somme des inventaires par filiale (source de vérité)."""
        return sum((inv.quantity or 0) for inv in (self.inventory or []))

    @property
    def reorder_point(self) -> int:
        """
        Point de commande (ROP) = demande moyenne x délai d'appro + stock de sécurité.
        Fallback sur min_threshold si les paramètres ne sont pas renseignés.
        """
        lt = self.lead_time_days or (self.supplier.lead_time_days if self.supplier else 0) or 0
        ss = self.safety_stock or 0
        computed = round((self.avg_daily_demand or 0.0) * lt + ss)
        return max(computed, self.min_threshold or 0)


class Inventory(Base):
    """Le stock spécifique à chaque filiale (SOURCE DE VÉRITÉ de la quantité)"""
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    branch_id = Column(Integer, ForeignKey("branches.id"))
    quantity = Column(Integer, default=0)
    min_threshold = Column(Integer, default=5)

    __table_args__ = (
        CheckConstraint('quantity >= 0', name='check_quantity_non_negative'),
        UniqueConstraint('product_id', 'branch_id', name='uq_inventory_product_branch'),
    )

    product = relationship("Product", back_populates="inventory")
    branch = relationship("Branch", back_populates="inventory")


class Lot(Base):
    """
    Lot / batch d'un produit dans une filiale, avec date de péremption.
    Permet la gestion FEFO (First Expired, First Out) pour pharma / agro.
    """
    __tablename__ = "lots"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), index=True)
    lot_number = Column(String, index=True)
    quantity = Column(Integer, default=0)
    expiry_date = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)

    __table_args__ = (
        CheckConstraint('quantity >= 0', name='check_lot_quantity_non_negative'),
    )

    product = relationship("Product", back_populates="lots")


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    branch_id = Column(Integer, ForeignKey("branches.id"))
    quantity = Column(Integer)
    reason = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    movement_type = Column(String, default="IN")  # 'IN' | 'OUT' | 'ADJUST'
    # Traçabilité : qui (utilisateur/agent) a provoqué le mouvement, et corrélation.
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    correlation_id = Column(String, nullable=True, index=True)
    # Mouvement de compensation (rollback) pointant vers le mouvement annulé.
    reverses_movement_id = Column(Integer, ForeignKey("stock_movements.id"), nullable=True)
    reversed = Column(Boolean, default=False)


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
    status = Column(String, default=OrderStatus.DRAFT.value)
    total_amount = Column(Float, default=0.0)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)

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
    # Coût total des marchandises vendues (COGS) pour le calcul de marge.
    total_cost = Column(Float, default=0.0)
    status = Column(String, default="CONFIRMED")  # CONFIRMED | REVERSED

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)

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
    unit_cost = Column(Float, default=0.0)  # coût unitaire au moment de la vente (WAC)

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
    """
    Traçabilité des modifications de stock et ventes.
    Journal en chaîne de hachage (tamper-evident) : chaque entrée référence le
    hash de la précédente (par entreprise), rendant toute altération détectable.
    """
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    actor_type = Column(String, nullable=True)  # HUMAIN | AGENT | ADMIN | SYSTEM
    action = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    # Delta structuré (JSON sérialisé) — remplace le texte libre.
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    entity_type = Column(String, nullable=True)   # product | sale | transfer | ...
    entity_id = Column(Integer, nullable=True)
    correlation_id = Column(String, nullable=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    # Chaîne de hachage anti-falsification.
    prev_hash = Column(String, nullable=True)
    entry_hash = Column(String, nullable=True, index=True)
    # Horodatage canonique EXACT inclus dans le calcul de entry_hash.
    # Persisté pour permettre un re-calcul complet (replay) lors de verify_chain.
    hash_ts = Column(String, nullable=True)

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
    status = Column(String, default=TransferStatus.PENDING.value)
    requester_id = Column(Integer, ForeignKey("users.id"))
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Origine de la demande : utile pour distinguer demandes humaines vs agents.
    origin = Column(String, default="HUMAIN")  # HUMAIN | AGENT
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)

    product = relationship("Product")
    from_branch = relationship("Branch", foreign_keys=[from_branch_id])
    to_branch = relationship("Branch", foreign_keys=[to_branch_id])
    requester = relationship("User", foreign_keys=[requester_id])
    approver = relationship("User", foreign_keys=[approver_id])


class AgentProposal(Base):
    """
    Proposition d'action émise par un agent IA (niveau PROPOSE), en attente de
    validation humaine (human-in-the-loop). Implémente le modèle d'autorisation.
    """
    __tablename__ = "agent_proposals"
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("users.id"))
    action_type = Column(String)                 # RESTOCK | TRANSFER | ...
    payload = Column(Text)                        # JSON de l'action proposée
    rationale = Column(Text, nullable=True)       # explication de l'agent
    status = Column(String, default="PENDING")    # PENDING | APPROVED | REJECTED | EXECUTED
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    correlation_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)

    agent = relationship("User", foreign_keys=[agent_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
