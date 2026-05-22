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
    action: str
    timestamp: datetime
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    company_id: int
    class Config:
        from_attributes = True

# --- AUTHENTIFICATION ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class AgentAccessCreate(BaseModel):
    name: str

class AgentAccessResponse(BaseModel):
    email: str
    api_key: str
    user_type: str


class UserSignUp(BaseModel):
    email: EmailStr
    password: str
    company_name: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    company_id: Optional[int] = None

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
