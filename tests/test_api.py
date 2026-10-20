import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from factories import create_payment, create_promo_code, create_tariff
from helpers import payment_body, send_webhook
from models import Payment, PaymentStatus
from services.payments import PaymentService

# --- Тарифы ---


async def test_list_tariffs(client: AsyncClient, db: AsyncSession) -> None:
    await create_tariff(db, title='premium', price=2990000)
    await create_tariff(db, title='basic', price=990000)

    response = await client.get('/tariffs')

    assert response.status_code == 200
    assert [(t['title'], t['price']) for t in response.json()] == [
        ('basic', 990000),
        ('premium', 2990000),
    ]


async def test_list_tariffs_empty(client: AsyncClient) -> None:
    response = await client.get('/tariffs')

    assert response.status_code == 200
    assert response.json() == []


# --- Получение платежа ---


async def test_get_payment(client: AsyncClient, db: AsyncSession) -> None:
    payment = await create_payment(db)

    response = await client.get(f'/payments/{payment.id}')

    assert response.status_code == 200
    data = response.json()
    assert data['id'] == str(payment.id)
    assert data['amount'] == payment.amount
    assert data['status'] == 'pending'


async def test_get_missing_payment_is_404(client: AsyncClient) -> None:
    response = await client.get(f'/payments/{uuid.uuid4()}')

    assert response.status_code == 404
    assert response.json() == {'detail': 'payment_not_found'}


# --- Создание платежа ---


@pytest.mark.parametrize(
    ('promo_code', 'amount', 'discount'),
    [
        (None, 1990000, 0),
        ('KVITTO10', 1791000, 199000),
        ('kvitto10', 1791000, 199000),
        (' KvItTo10 ', 1791000, 199000),
    ],
)
async def test_amount_with_and_without_promo_code(
    client: AsyncClient,
    db: AsyncSession,
    promo_code: str | None,
    amount: int,
    discount: int,
) -> None:
    tariff = await create_tariff(db, price=1990000)
    await create_promo_code(db, code='KVITTO10', discount_percent=10)

    response = await client.post('/payments', json=payment_body(tariff.id, promo_code=promo_code))

    assert response.status_code == 201
    data = response.json()
    assert (data['amount'], data['discount']) == (amount, discount)
    assert data['email'] == 'student@example.com'


@pytest.mark.parametrize('months', [3, 6, 12])
@pytest.mark.parametrize('promo_code', [None, 'KVITTO10'])
@pytest.mark.parametrize('price', [990000, 1990000, 2990000, 1000001])
async def test_installment_schedule_sums_to_amount(
    client: AsyncClient,
    db: AsyncSession,
    months: int,
    promo_code: str | None,
    price: int,
) -> None:
    tariff = await create_tariff(db, price=price)
    await create_promo_code(db, code='KVITTO10', discount_percent=10)

    response = await client.post(
        '/payments',
        json=payment_body(
            tariff.id,
            method='installment',
            installment_months=months,
            promo_code=promo_code,
        ),
    )

    assert response.status_code == 201
    data = response.json()
    assert len(data['schedule']) == months
    assert sum(data['schedule']) == data['amount']
    # Остаток раздаётся по копейке: платежи отличаются не больше чем на 1.
    assert max(data['schedule']) - min(data['schedule']) <= 1


async def test_installment_schedule_example(client: AsyncClient, db: AsyncSession) -> None:
    tariff = await create_tariff(db, price=1990000)

    response = await client.post(
        '/payments',
        json=payment_body(tariff.id, method='installment', installment_months=3),
    )

    assert response.status_code == 201
    data = response.json()
    assert data['schedule'] == [663334, 663333, 663333]
    assert sum(data['schedule']) == data['amount']


@pytest.mark.parametrize(
    'fields',
    [
        {'method': 'installment'},
        {'method': 'card', 'installment_months': 3},
        {'method': 'installment', 'installment_months': 4},
    ],
)
async def test_invalid_method_and_months_is_422(
    client: AsyncClient,
    db: AsyncSession,
    fields: dict,
) -> None:
    tariff = await create_tariff(db)

    response = await client.post('/payments', json=payment_body(tariff.id, **fields))

    assert response.status_code == 422


async def test_unknown_tariff_is_404(client: AsyncClient, db: AsyncSession) -> None:
    response = await client.post('/payments', json=payment_body(uuid.uuid4()))

    assert response.status_code == 404
    assert response.json() == {'detail': 'tariff_not_found'}
    assert await db.scalar(select(func.count()).select_from(Payment)) == 0


async def test_same_payment_twice_is_200(client: AsyncClient, db: AsyncSession) -> None:
    tariff = await create_tariff(db)
    body = payment_body(tariff.id)
    headers = {'Idempotency-Key': str(uuid.uuid4())}

    first = await client.post('/payments', json=body, headers=headers)
    second = await client.post('/payments', json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert await db.scalar(select(func.count()).select_from(Payment)) == 1


@pytest.mark.parametrize('key', ['', '   '])
async def test_empty_idempotency_key_is_422(
    client: AsyncClient,
    db: AsyncSession,
    key: str,
) -> None:
    tariff = await create_tariff(db)

    response = await client.post(
        '/payments',
        json=payment_body(tariff.id),
        headers={'Idempotency-Key': key},
    )

    assert response.status_code == 422
    assert response.json()['detail'][0]['loc'] == ['header', 'idempotency-key']
    assert await db.scalar(select(func.count()).select_from(Payment)) == 0


async def test_non_uuid_idempotency_key_is_422(client: AsyncClient, db: AsyncSession) -> None:
    tariff = await create_tariff(db)

    response = await client.post(
        '/payments',
        json=payment_body(tariff.id),
        headers={'Idempotency-Key': 'order-1'},
    )

    assert response.status_code == 422
    assert response.json()['detail'][0]['loc'] == ['header', 'idempotency-key']
    assert await db.scalar(select(func.count()).select_from(Payment)) == 0


async def test_concurrent_same_payment_creates_one(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    tariff = await create_tariff(db)
    body = payment_body(tariff.id)
    headers = {'Idempotency-Key': str(uuid.uuid4())}

    responses = await asyncio.gather(
        *(client.post('/payments', json=body, headers=headers) for _ in range(5))
    )

    assert sorted(r.status_code for r in responses) == [200, 200, 200, 200, 201]
    assert await db.scalar(select(func.count()).select_from(Payment)) == 1


async def test_unexpected_integrity_error_is_500_and_logged(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tariff = await create_tariff(db)
    # Рассрочка без графика нарушает CHECK в БД — непредвиденный IntegrityError.
    monkeypatch.setattr(PaymentService, '_get_schedule', lambda self, amount, months: None)

    response = await client.post(
        '/payments',
        json=payment_body(tariff.id, method='installment', installment_months=3),
        headers={'Idempotency-Key': str(uuid.uuid4())},
    )

    assert response.status_code == 500
    assert response.json() == {'detail': 'internal_error'}
    assert await db.scalar(select(func.count()).select_from(Payment)) == 0
    [record] = [r for r in caplog.records if r.name == 'services.payments']
    assert record.levelname == 'ERROR'
    assert record.exc_info is not None
    # Подробности ошибки — только в логе, клиенту они не уходят.
    assert 'ck_payments_schedule_iff_installment' in caplog.text


async def test_race_of_two_same_requests_is_resolved_by_unique_key(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tariff = await create_tariff(db)
    body = payment_body(tariff.id)
    headers = {'Idempotency-Key': str(uuid.uuid4())}

    original_lookup = PaymentService._get_obj_by_idempotency_key
    lookups = 0
    both_checked = asyncio.Event()

    async def lookup_then_wait_for_other(
        self: PaymentService, key: uuid.UUID | None
    ) -> Payment | None:
        # Оба запроса сначала не находят платёж и только потом идут в INSERT —
        # так гонка воспроизводится всегда, а не по случайности планировщика.
        nonlocal lookups
        result = await original_lookup(self, key)
        lookups += 1
        if lookups == 2:
            both_checked.set()
        if lookups <= 2:
            await asyncio.wait_for(both_checked.wait(), timeout=5)
        return result

    monkeypatch.setattr(
        PaymentService, '_get_obj_by_idempotency_key', lookup_then_wait_for_other
    )

    first, second = await asyncio.gather(
        client.post('/payments', json=body, headers=headers),
        client.post('/payments', json=body, headers=headers),
    )

    assert sorted([first.status_code, second.status_code]) == [200, 201]
    assert first.json() == second.json()
    assert await db.scalar(select(func.count()).select_from(Payment)) == 1
    # Третий поиск — из обработчика IntegrityError: проигравший запрос упал на UNIQUE.
    assert lookups == 3


@pytest.mark.parametrize(
    ('promo_fields', 'detail'),
    [
        (None, 'promo_code_not_found'),
        ({'is_active': False}, 'promo_code_inactive'),
        ({'is_reusable': False, 'is_used': True}, 'promo_code_already_used'),
    ],
)
async def test_bad_promo_code_is_422(
    client: AsyncClient,
    db: AsyncSession,
    promo_fields: dict | None,
    detail: str,
) -> None:
    tariff = await create_tariff(db)
    if promo_fields is not None:
        await create_promo_code(db, code='PROMO', **promo_fields)

    response = await client.post('/payments', json=payment_body(tariff.id, promo_code='PROMO'))

    assert response.status_code == 422
    assert response.json() == {'detail': detail}
    assert await db.scalar(select(func.count()).select_from(Payment)) == 0


async def test_single_use_promo_code_is_taken_by_payment(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    tariff = await create_tariff(db)
    promo = await create_promo_code(db, code='ONCE', is_reusable=False)

    response = await client.post('/payments', json=payment_body(tariff.id, promo_code='ONCE'))

    assert response.status_code == 201
    await db.refresh(promo)
    assert promo.is_used is True


async def test_concurrent_single_use_promo_code_is_taken_once(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    tariff = await create_tariff(db)
    await create_promo_code(db, code='ONCE', is_reusable=False)
    body = payment_body(tariff.id, promo_code='ONCE')

    responses = await asyncio.gather(*(client.post('/payments', json=body) for _ in range(5)))

    assert sorted(r.status_code for r in responses) == [201, 422, 422, 422, 422]
    assert all(
        r.json() == {'detail': 'promo_code_already_used'}
        for r in responses
        if r.status_code == 422
    )
    assert await db.scalar(select(func.count()).select_from(Payment)) == 1


async def test_concurrent_reusable_promo_code_is_applied_to_all(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    tariff = await create_tariff(db)
    await create_promo_code(db, code='KVITTO10')
    body = payment_body(tariff.id, promo_code='KVITTO10')

    responses = await asyncio.gather(*(client.post('/payments', json=body) for _ in range(5)))

    assert [r.status_code for r in responses] == [201] * 5
    assert await db.scalar(select(func.count()).select_from(Payment)) == 5


# --- Вебхук банка ---


async def test_failed_payment_releases_single_use_promo_code(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    promo = await create_promo_code(db, code='ONCE', is_reusable=False)
    payment = await create_payment(db, promo_code=promo)

    response = await send_webhook(client, payment.id, 'failed')

    assert response.status_code == 200
    await db.refresh(promo)
    assert promo.is_used is False
    again = await client.post(
        '/payments',
        json=payment_body(payment.tariff_id, promo_code='ONCE'),
    )
    assert again.status_code == 201


@pytest.mark.parametrize('status', list(PaymentStatus))
async def test_repeated_status_is_409(
    client: AsyncClient,
    db: AsyncSession,
    status: PaymentStatus,
) -> None:
    # Переход в тот же статус не входит в разрешённые по ТЗ — это запрещённый переход.
    promo = await create_promo_code(db, is_reusable=False)
    payment = await create_payment(db, promo_code=promo, status=status)

    response = await send_webhook(client, payment.id, status.value)

    assert response.status_code == 409
    assert response.json() == {'error': 'invalid_transition'}
    await db.refresh(payment)
    await db.refresh(promo)
    assert payment.status == status
    # Отклонённый вебхук ничего не меняет, в том числе флаг промокода.
    assert promo.is_used is True


@pytest.mark.parametrize(
    ('current', 'new'),
    [
        (PaymentStatus.PENDING, PaymentStatus.SUCCEEDED),
        (PaymentStatus.PENDING, PaymentStatus.FAILED),
        (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED),
    ],
)
async def test_allowed_transition(
    client: AsyncClient,
    db: AsyncSession,
    current: PaymentStatus,
    new: PaymentStatus,
) -> None:
    payment = await create_payment(db, status=current)

    response = await send_webhook(client, payment.id, new.value)

    assert response.status_code == 200
    await db.refresh(payment)
    assert payment.status == new


@pytest.mark.parametrize(
    ('current', 'new'),
    [
        (PaymentStatus.PENDING, PaymentStatus.REFUNDED),
        (PaymentStatus.SUCCEEDED, PaymentStatus.PENDING),
        (PaymentStatus.SUCCEEDED, PaymentStatus.FAILED),
        (PaymentStatus.FAILED, PaymentStatus.SUCCEEDED),
        (PaymentStatus.REFUNDED, PaymentStatus.SUCCEEDED),
    ],
)
async def test_invalid_transition_is_409(
    client: AsyncClient,
    db: AsyncSession,
    current: PaymentStatus,
    new: PaymentStatus,
) -> None:
    payment = await create_payment(db, status=current)

    response = await send_webhook(client, payment.id, new.value)

    assert response.status_code == 409
    assert response.json() == {'error': 'invalid_transition'}
    await db.refresh(payment)
    assert payment.status == current


async def test_webhook_for_missing_payment_is_404(client: AsyncClient) -> None:
    response = await send_webhook(client, uuid.uuid4(), 'succeeded')

    assert response.status_code == 404
    assert response.json() == {'detail': 'payment_not_found'}


async def test_webhook_with_bad_signature_is_401(client: AsyncClient, db: AsyncSession) -> None:
    payment = await create_payment(db)

    response = await send_webhook(client, payment.id, 'succeeded', signature='bad')

    assert response.status_code == 401
    await db.refresh(payment)
    assert payment.status == PaymentStatus.PENDING
