import uuid
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from models import Base
from services.exceptions import NotFoundException

ModelT = TypeVar('ModelT', bound=Base)


class BaseService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_obj_or_404(
        self,
        model: type[ModelT],
        obj_id: uuid.UUID,
        detail_err: str | None = None,
    ) -> ModelT:
        obj = await self.db.get(model, obj_id)
        if obj is None:
            raise NotFoundException(detail=detail_err or 'obj_not_found')
        return obj
