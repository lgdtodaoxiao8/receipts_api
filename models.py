from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class CategoryOut(BaseModel):
    id: int
    name: str


class CategoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    price: Decimal = Field(gt=0)
    category_id: int | None = Field(default=None, gt=0)


class ItemOut(BaseModel):
    name: str
    price: Decimal
    category_name: str | None


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

    @computed_field
    @property
    def calculated_total(self) -> Decimal:
        return sum((item.price for item in self.items), Decimal(0))

    @computed_field
    @property
    def discrepancy(self) -> Decimal | None:
        if self.total is None:
            return None

        return self.calculated_total - self.total


class ReceiptTextIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=10, max_length=5000)
