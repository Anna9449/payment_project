from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.postgres import get_session
from models import Tariff
from services.base import BaseService


class TariffService(BaseService):

    async def list_tariffs(self) -> list[Tariff]:
        result = await self.db.scalars(select(Tariff).order_by(Tariff.price))
        return list(result)


def get_tariff_service(db: AsyncSession = Depends(get_session)) -> TariffService:
    return TariffService(db)
