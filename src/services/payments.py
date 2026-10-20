import logging
import uuid

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.postgres import get_session
from models import Payment, PaymentStatus, PromoCode, Tariff
from schemas.payment import PaymentCreateDTO
from services.base import BaseService
from services.exceptions import (
    InternalServerError,
    InvalidTransitionError,
    NotFoundException,
    PromoCodeError,
)

logger = logging.getLogger(__name__)


class PaymentService(BaseService):

    ALLOWED_TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
        PaymentStatus.PENDING: {PaymentStatus.SUCCEEDED, PaymentStatus.FAILED},
        PaymentStatus.SUCCEEDED: {PaymentStatus.REFUNDED},
        PaymentStatus.FAILED: set(),
        PaymentStatus.REFUNDED: set(),
    }

    async def get_payment(self, payment_id: uuid.UUID) -> Payment:
        return await self.get_obj_or_404(Payment, payment_id, 'payment_not_found')

    async def _get_obj_by_idempotency_key(
        self, key: uuid.UUID | None
    ) -> Payment | None:
        if key is None:
            return None
        payment_obj = await self.db.scalar(
            select(Payment).where(Payment.idempotency_key == key)
        )
        return payment_obj

    async def _get_promo_code(self, code: str | None) -> PromoCode | None:
        if code is None:
            return None
        promo = await self.db.scalar(select(PromoCode).where(PromoCode.code == code))
        if promo is None:
            raise PromoCodeError('promo_code_not_found')
        if not promo.is_active:
            raise PromoCodeError('promo_code_inactive')
        if not promo.is_reusable:
            await self.db.refresh(promo, with_for_update=True)
            if promo.is_used:
                raise PromoCodeError('promo_code_already_used')
        return promo

    def _calc_discount(self, price: int, promo: PromoCode) -> int:
        return price * promo.discount_percent // 100

    def _get_schedule(self, amount: int, months: int | None) -> list[int] | None:
        if months is None:
            return None
        base, remainder = divmod(amount, months)
        return [base + 1] * remainder + [base] * (months - remainder)

    async def create_payment(
        self,
        data: PaymentCreateDTO,
        idempotency_key: uuid.UUID | None,
    ) -> tuple[Payment, bool]:
        if payment_obj := await self._get_obj_by_idempotency_key(idempotency_key):
            return payment_obj, False

        tariff = await self.get_obj_or_404(Tariff, data.tariff_id, 'tariff_not_found')
        discount = 0

        if promo := await self._get_promo_code(data.promo_code):
            if not promo.is_reusable:
                promo.is_used = True
            discount = self._calc_discount(tariff.price, promo)

        amount = tariff.price - discount

        payment = Payment(
            tariff_id=tariff.id,
            email=data.email.lower(),
            method=data.method,
            amount=amount,
            discount=discount,
            promo_code_id=promo.id if promo else None,
            installment_months=data.installment_months,
            schedule=self._get_schedule(amount, data.installment_months),
            idempotency_key=idempotency_key,
        )
        self.db.add(payment)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            if payment_obj := await self._get_obj_by_idempotency_key(idempotency_key):
                return payment_obj, False
            logger.exception(
                'Не удалось создать платёж: tariff_id=%s, idempotency_key=%s',
                data.tariff_id,
                idempotency_key,
            )
            raise InternalServerError from exc

        await self.db.refresh(payment)
        return payment, True

    async def change_status(
        self,
        payment_id: uuid.UUID,
        new_status: PaymentStatus,
    ) -> Payment:
        payment = await self.db.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        if payment is None:
            raise NotFoundException(detail='payment_not_found')
        if new_status not in self.ALLOWED_TRANSITIONS[payment.status]:
            await self.db.rollback()
            raise InvalidTransitionError
        payment.status = new_status
        if (
            new_status in [PaymentStatus.FAILED, PaymentStatus.REFUNDED]
            and payment.promo_code_id is not None
        ):
            await self.db.execute(
                update(PromoCode)
                .where(
                    PromoCode.id == payment.promo_code_id,
                    PromoCode.is_reusable.is_(False),
                )
                .values(is_used=False)
            )
        await self.db.commit()
        return payment


def get_payment_service(db: AsyncSession = Depends(get_session)) -> PaymentService:
    return PaymentService(db)
