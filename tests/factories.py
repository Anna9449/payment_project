"""Фабрики тестовых данных: пишут сразу в БД, минуя API."""

import itertools
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models import Payment, PaymentMethod, PaymentStatus, PromoCode, Tariff

_seq = itertools.count(1)


async def create_tariff(db: AsyncSession, **fields: Any) -> Tariff:
    tariff = Tariff(**{'title': f'tariff-{next(_seq)}', 'price': 1990000, **fields})
    db.add(tariff)
    await db.commit()
    return tariff


async def create_promo_code(db: AsyncSession, **fields: Any) -> PromoCode:
    promo = PromoCode(
        **{
            'code': f'PROMO{next(_seq)}',
            'discount_percent': 10,
            'is_active': True,
            'is_reusable': True,
            'is_used': False,
            **fields,
        }
    )
    db.add(promo)
    await db.commit()
    return promo


async def create_payment(
    db: AsyncSession,
    *,
    tariff: Tariff | None = None,
    promo_code: PromoCode | None = None,
    **fields: Any,
) -> Payment:
    if tariff is None:
        tariff = await create_tariff(db)
    discount = tariff.price * promo_code.discount_percent // 100 if promo_code else 0
    if promo_code is not None and not promo_code.is_reusable:
        # Как в сервисе: платёж занимает одноразовый промокод.
        promo_code.is_used = True
    payment = Payment(
        **{
            'tariff_id': tariff.id,
            'email': 'student@example.com',
            'method': PaymentMethod.CARD,
            'status': PaymentStatus.PENDING,
            'amount': tariff.price - discount,
            'discount': discount,
            'promo_code_id': promo_code.id if promo_code else None,
            **fields,
        }
    )
    db.add(payment)
    await db.commit()
    return payment
