from sqlalchemy import Boolean, CheckConstraint, SmallInteger, String, false, true
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class PromoCode(TimestampMixin, Base):
    """Промокод на скидку в процентах от цены тарифа."""

    __tablename__ = 'promo_codes'
    __table_args__ = (
        CheckConstraint('discount_percent BETWEEN 1 AND 99', name='discount_percent_range'),
        CheckConstraint('code = upper(code)', name='code_uppercase'),
    )

    code: Mapped[str] = mapped_column(String(50), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    is_reusable: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    discount_percent: Mapped[int] = mapped_column(SmallInteger)
    # Только для одноразовых: снимается, когда платёж с этим промокодом провалился.
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
