from fastapi import APIRouter, Depends

from models.tariff import Tariff
from schemas.tariff import TariffDTO
from services.tariffs import TariffService, get_tariff_service

router = APIRouter(prefix='/tariffs', tags=['tariffs'])


@router.get(
    '',
    summary='Список тарифов',
    response_model=list[TariffDTO],
)
async def get_tariffs(
    tariff_service: TariffService = Depends(get_tariff_service),
) -> list[Tariff]:
    return await tariff_service.list_tariffs()
