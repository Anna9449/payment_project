import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

from models import PaymentMethod, PaymentStatus


class PaymentCreateDTO(BaseModel):
    tariff_id: uuid.UUID
    email: EmailStr
    method: PaymentMethod
    installment_months: Literal[3, 6, 12] | None = None
    promo_code: str | None = None

    @field_validator('promo_code')
    @classmethod
    def normalize_promo_code(cls, value: str | None) -> str | None:
        if value is not None:
            return value.strip().upper()
        return value

    @model_validator(mode='after')
    def installment_months_matches_method(self) -> Self:
        if self.method == PaymentMethod.INSTALLMENT and self.installment_months is None:
            raise ValueError('installment_months is required for installment')
        if self.method != PaymentMethod.INSTALLMENT and self.installment_months is not None:
            raise ValueError('installment_months is allowed only for installment')
        return self


class PaymentDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: PaymentStatus
    tariff_id: uuid.UUID
    amount: int
    discount: int
    method: PaymentMethod
    installment_months: int | None
    schedule: list[int] | None
    email: str
    created_at: datetime
