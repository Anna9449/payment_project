from fastapi import APIRouter, Depends, status
from fastapi.responses import ORJSONResponse

from schemas.webhook import BankWebhookDTO, WebhookErrorDTO, WebhookOkDTO
from services.exceptions import InvalidTransitionError
from services.payments import PaymentService, get_payment_service
from utils.bank_signature import verify_webhook_signature

router = APIRouter(prefix='/webhooks', tags=['webhooks'])


@router.post(
    '/bank',
    summary='Коллбэк банка о смене статуса',
    dependencies=[Depends(verify_webhook_signature)],
    response_model=WebhookOkDTO,
    responses={409: {'model': WebhookErrorDTO}},
)
async def bank_webhook(
    request_obj: BankWebhookDTO,
    payment_service: PaymentService = Depends(get_payment_service),
) -> WebhookOkDTO | ORJSONResponse:
    try:
        await payment_service.change_status(request_obj.payment_id, request_obj.status)
    except InvalidTransitionError:
        return ORJSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={'error': 'invalid_transition'},
        )
    return WebhookOkDTO()
