# Импортируйте здесь все модели, чтобы alembic видел их в Base.metadata.
from models.base import Base, TimestampMixin
from models.payment import Payment, PaymentMethod, PaymentStatus
from models.promo_code import PromoCode
from models.tariff import Tariff

__all__ = [
    'Base',
    'TimestampMixin',
    'Payment',
    'PaymentMethod',
    'PaymentStatus',
    'PromoCode',
    'Tariff',
]
