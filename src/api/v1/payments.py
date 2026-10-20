import uuid

from fastapi import APIRouter, Depends, Header, Response, status

from models.payment import Payment
from schemas.payment import PaymentCreateDTO, PaymentDTO
from services.payments import PaymentService, get_payment_service

router = APIRouter(prefix='/payments', tags=['payments'])


@router.post(
    '',
    summary='Создать платёж',
    response_model=PaymentDTO,
    responses={200: {'description': 'Платёж с таким Idempotency-Key уже создан'}},
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    request_obj: PaymentCreateDTO,
    response: Response,
    payment_service: PaymentService = Depends(get_payment_service),
    idempotency_key: uuid.UUID | None = Header(default=None),
) -> Payment:
    payment, created = await payment_service.create_payment(request_obj, idempotency_key)
    if not created:
        response.status_code = status.HTTP_200_OK
    return payment


@router.get(
    '/{payment_id}',
    summary='Платёж по id',
    response_model=PaymentDTO,
)
async def get_payment(
    payment_id: uuid.UUID,
    payment_service: PaymentService = Depends(get_payment_service),
) -> Payment:
    return await payment_service.get_payment(payment_id)
