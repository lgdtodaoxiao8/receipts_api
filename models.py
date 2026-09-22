from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CategoryOut(BaseModel):
    id: int
    name: str


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    price: Decimal = Field(gt=0)


class ItemOut(BaseModel):
    name: str
    price: Decimal


class ReceiptIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    shop: str | None = Field(default=None, max_length=200)
    total: Decimal | None = Field(default=None, ge=0)
    items: list[ItemIn] = Field(min_length=1)


class ReceiptOut(BaseModel):
    id: int
    shop: str | None
    total: Decimal | None
    purchased_at: datetime
    items: list[ItemOut]
