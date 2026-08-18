"""Pydantic schemas."""
from pydantic import BaseModel, Field
from typing import List, Optional, Any


class ProductIn(BaseModel):
    sku: str
    name: str
    category: Optional[str] = "General"
    supplier: Optional[str] = "Default Supplier"
    location: str = "A01"
    physical_stock: int = 0
    min_stock: int = 5
    safety_stock: int = 5
    reorder_level: int = 10
    avg_daily_demand: float = 1
    unit_price: float = 100


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    supplier: Optional[str] = None
    location: Optional[str] = None
    min_stock: Optional[int] = None
    safety_stock: Optional[int] = None
    reorder_level: Optional[int] = None
    avg_daily_demand: Optional[float] = None
    unit_price: Optional[float] = None


class StockOp(BaseModel):
    product_id: str
    quantity: int
    reason: Optional[str] = ""
    location: Optional[str] = None


class OrderItemIn(BaseModel):
    product_id: str
    quantity: int


class OrderIn(BaseModel):
    customer_name: str
    customer_priority: str = "NORMAL"  # LOW/NORMAL/HIGH/VIP
    required_by: str  # ISO
    order_value: Optional[float] = None
    items: List[OrderItemIn]


class WorkerIn(BaseModel):
    name: str
    role: str  # PICKER / PACKER / QC / DISPATCH
    available: bool = True
    efficiency: int = 90


class ExceptionIn(BaseModel):
    type: str
    order_id: Optional[str] = None
    product_id: Optional[str] = None
    description: str
    severity: str = "MEDIUM"


class SimRequest(BaseModel):
    decision_id: str


class Setting(BaseModel):
    key: str
    value: str
