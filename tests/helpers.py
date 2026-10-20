import json
import uuid
from typing import Any

from httpx import AsyncClient, Response

from core.config import settings
from utils.bank_signature import sign


def payment_body(tariff_id: uuid.UUID, **fields: Any) -> dict[str, Any]:
    return {'tariff_id': str(tariff_id), 'email': 'Student@Example.com', 'method': 'card', **fields}


async def send_webhook(
    client: AsyncClient,
    payment_id: uuid.UUID,
    status: str,
    signature: str | None = None,
) -> Response:
    body = json.dumps({'payment_id': str(payment_id), 'status': status}).encode()
    return await client.post(
        '/webhooks/bank',
        content=body,
        headers={
            'Content-Type': 'application/json',
            'X-Signature': signature or sign(body, settings.webhook_secret),
        },
    )
