import uuid
from typing import Literal

from pydantic import BaseModel

from models import PaymentStatus


class BankWebhookDTO(BaseModel):
    payment_id: uuid.UUID
    status: PaymentStatus


class WebhookOkDTO(BaseModel):
    result: Literal['ok'] = 'ok'


class WebhookErrorDTO(BaseModel):
    error: str
