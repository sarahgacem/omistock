from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from models import ProductStatus, OrderStatus

# --- FOURNISSEURS ---
class SupplierBase(BaseModel):
    name: str
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class SupplierCreate(SupplierBase):
    pass

class SupplierResponse(SupplierBase):
    id: int
    company_id: int
    class Config:
        from_attributes = True

# --- FILIALES ---
class BranchBase(BaseModel):
    name: str
    city: Optional[str] = None

class BranchCreate(BranchBase):
    pass

class BranchResponse(BranchBase):
    id: int
    company_id: int
    class Config:
        from_attributes = True

# --- PRODUITS ---
class ProductBase(BaseModel):
    name: str
    sku: Optional[str] = None
    barcode: Optional[str] = None
    quantity: int = 0
    price: float = 0.0
    min_threshold: int = 5
    status: ProductStatus = ProductStatus.NEW
    created_at: Optional[datetime] = None

class ProductCreate(ProductBase):
    supplier_id: Optional[int] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[float] = None
    min_threshold: Optional[int] = None
    status: Optional[ProductStatus] = None
    supplier_id: Optional[int] = None

class ProductAnalyzeRequest(BaseModel):
    product_id: int

class InventoryResponse(BaseModel):
    id: int
    branch_id: int
    quantity: int
    branch: BranchResponse
    class Config:
        from_attributes = True

class ProductResponse(ProductBase):
    id: int
    company_id: int
    supplier: Optional[SupplierResponse] = None
    inventory: List[InventoryResponse] = []
    # Champs dérivés (théorie de gestion de stock) exposés à l'IHM.
    cost_price: Optional[float] = 0.0          # coût moyen pondéré (WAC)
    total_quantity: Optional[int] = None       # somme des inventaires (source de vérité)
    reorder_point: Optional[int] = None        # point de commande calculé
    avg_daily_demand: Optional[float] = None
    safety_stock: Optional[int] = None
    lead_time_days: Optional[int] = None
    class Config:
        from_attributes = True

# --- MOUVEMENTS DE STOCK ---
class StockMovementCreate(BaseModel):
    product_id: int
    quantity: int
    reason: str
    movement_type: Optional[str] = "IN"

class StockMovementResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    reason: str
    movement_type: str
    created_at: datetime
    actor_id: Optional[int] = None          # traçabilité : qui a déclenché
    correlation_id: Optional[str] = None    # corrélation intention -> action
    class Config:
        from_attributes = True

# --- TRANSFERTS ---
class TransferCreate(BaseModel):
    product_id: int
    from_branch_id: int
    to_branch_id: int
    quantity: int

class TransferRequestCreate(BaseModel):
    product_id: int
    from_branch_id: int
    to_branch_id: int
    quantity: int

class TransferRequestResponse(BaseModel):
    id: int
    product_id: int
    from_branch_id: int
    to_branch_id: int
    quantity: int
    status: str
    requester_id: int
    approver_id: Optional[int] = None
    created_at: datetime
    product: ProductResponse
    from_branch: BranchResponse
    to_branch: BranchResponse
    class Config:
        from_attributes = True

# --- BONS DE COMMANDE ---
class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    total_amount: float = 0.0

class PurchaseOrderResponse(BaseModel):
    id: int
    order_number: str
    supplier_id: int
    status: OrderStatus
    total_amount: float
    created_at: datetime
    supplier: SupplierResponse
    class Config:
        from_attributes = True

# --- VENTES & CLIENTS ---
class CustomerCreate(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

class CustomerResponse(CustomerCreate):
    id: int
    company_id: int
    class Config:
        from_attributes = True

class SaleItemCreate(BaseModel):
    product_id: int
    quantity: int
    unit_price: float

class SaleItemResponse(SaleItemCreate):
    id: int
    sale_id: int
    class Config:
        from_attributes = True

class SaleCreate(BaseModel):
    customer_id: Optional[int] = None
    branch_id: int
    items: List[SaleItemCreate]

class SaleResponse(BaseModel):
    id: int
    date: datetime
    total_amount: float
    customer_id: Optional[int] = None
    company_id: int
    branch_id: int
    items: List[SaleItemResponse]
    class Config:
        from_attributes = True

class InvoiceItem(BaseModel):
    product_name: str
    quantity: int
    unit_price: float
    total: float

class InvoiceResponse(BaseModel):
    sale_id: int
    customer_name: Optional[str] = "Client Comptant"
    date: datetime
    items: List[InvoiceItem]
    total_amount: float


# --- LOGS D'ACTIVITÉ ---
class ActivityLogResponse(BaseModel):
    id: int
    user_id: int
    action: str
    timestamp: datetime
    company_id: int
    user_email: Optional[str] = None # We will populate this in the endpoint
    class Config:
        from_attributes = True

class AuditLogResponse(BaseModel):
    id: int
    user_id: int
    user_email: Optional[str] = None
    user_type: Optional[str] = None
    actor_type: Optional[str] = None
    action: str
    timestamp: datetime
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    correlation_id: Optional[str] = None
    prev_hash: Optional[str] = None
    entry_hash: Optional[str] = None
    company_id: int
    class Config:
        from_attributes = True

# --- AUTHENTIFICATION ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class EmployeeCreate(BaseModel):
    email: EmailStr
    password: str
    branch_id: int

class BranchUserCreate(BaseModel):
    email: EmailStr
    password: str
    branch_id: int

class RestockCreate(BaseModel):
    supplier_id: int
    product_id: int
    branch_id: int
    quantity: int
    purchase_price: Optional[float] = 0.0

class AgentAccessCreate(BaseModel):
    name: str

class AgentAccessResponse(BaseModel):
    email: str
    api_key: str
    user_type: str


class CompanyResponse(BaseModel):
    id: int
    name: str
    commercial_register_number: Optional[str] = None
    activity_sector: Optional[str] = None
    nif: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    class Config:
        from_attributes = True

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    commercial_register_number: Optional[str] = None
    activity_sector: Optional[str] = None
    nif: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

class UserSignUp(BaseModel):
    email: EmailStr
    password: str
    company_name: str
    commercial_register_number: Optional[str] = None
    activity_sector: Optional[str] = None
    nif: Optional[str] = None
    address: Optional[str] = None
    company_email: Optional[str] = None
    company_phone: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    company_id: Optional[int] = None

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    user_type: str
    branch_id: Optional[int] = None
    company_id: int
    is_active: bool
    deletion_deadline: Optional[datetime] = None
    class Config:
        from_attributes = True

# --- SCANNER MOBILE ---
class ScanAddRequest(BaseModel):
    barcode: str
    quantity: int
    branch_id: int

class ScanSellRequest(BaseModel):
    barcode: str
    branch_id: int

class ScanSaleResponse(BaseModel):
    sale: SaleResponse
    name: str


# --- GOUVERNANCE / ACTIONS AGENT IA (ajouté au refactor) ---
class AgentAccessCreateV2(BaseModel):
    name: str
    autonomy_level: str = "read_only"           # read_only | suggest | propose | auto
    agent_scopes: Optional[str] = None          # ex: "stock:read,restock:propose"
    max_action_quantity: int = 0
    branch_id: Optional[int] = None
    api_key_ttl_days: int = 90                   # durée de vie de la clé API

class AgentAccessResponseV2(BaseModel):
    email: str
    api_key: str
    user_type: str
    autonomy_level: Optional[str] = None
    agent_scopes: Optional[str] = None
    api_key_expires_at: Optional[datetime] = None

class AgentRestockProposal(BaseModel):
    product_id: int
    branch_id: int
    quantity: int
    unit_cost: Optional[float] = 0.0
    rationale: Optional[str] = None

class AgentProposalResponse(BaseModel):
    id: int
    agent_id: int
    action_type: str
    payload: str
    rationale: Optional[str] = None
    status: str
    correlation_id: Optional[str] = None
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True


# --- Inventaire physique / cycle count (théorie de gestion de stock) ---
class CycleCountCreate(BaseModel):
    product_id: int
    branch_id: int
    counted_quantity: int                        # quantité réellement comptée (>= 0)
    reason: Optional[str] = "Comptage physique (cycle count)"

class CycleCountResponse(BaseModel):
    product_id: int
    branch_id: int
    system_before: int
    counted: int
    variance: int                                # + excédent / - manquant
    movement_id: Optional[int] = None
