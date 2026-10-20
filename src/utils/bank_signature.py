import hashlib
import hmac

from fastapi import Header, HTTPException, Request, status

from core.config import settings


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def verify_webhook_signature(
    request: Request,
    x_signature: str | None = Header(default=None),
) -> None:
    """X-Signature = hex(HMAC-SHA256(тело запроса, WEBHOOK_SECRET)), иначе 401."""
    expected = sign(await request.body(), settings.webhook_secret)
    if x_signature is None or not hmac.compare_digest(x_signature, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail='invalid_signature')
