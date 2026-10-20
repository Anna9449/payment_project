from fastapi import APIRouter

from api.v1 import payments, tariffs, webhooks

router = APIRouter()

router.include_router(tariffs.router)
router.include_router(payments.router)
router.include_router(webhooks.router)
