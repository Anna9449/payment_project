import uuid

from pydantic import BaseModel, ConfigDict


class TariffDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    price: int
