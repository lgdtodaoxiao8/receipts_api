from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from datetime import datetime

class CategoryOut(BaseModel):
    id: int
    name: str

class ItemIn(BaseModel):
    name: str
    price: Decimal = Field(gt=0)

class ItemOut(BaseModel):
    name: str
    price: Decimal

class ReceiptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shop: str | None = None
    total: Decimal | None = None
    items: list[ItemIn] = Field(min_length=1)

class ReceiptOut(BaseModel):
    id: int
    shop: str | None = None
    total: Decimal | None = None
    purchased_at: datetime
    items: list[ItemOut]
