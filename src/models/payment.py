import enum
import uuid

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin
from models.enums import PaymentMethod, PaymentStatus
from models.tariff import Tariff


def _str_enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    # Храним как varchar + CHECK, а не нативный ENUM Postgres:
    # новые значения добавляются без ALTER TYPE.
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )


class Payment(TimestampMixin, Base):
    """Платёж. Все суммы — в копейках."""

    __tablename__ = 'payments'
    __table_args__ = (
        CheckConstraint('amount > 0', name='amount_positive'),
        CheckConstraint('discount >= 0', name='discount_non_negative'),
        CheckConstraint(
            'installment_months IN (3, 6, 12)',
            name='installment_months_allowed',
        ),
        # Срок и график есть только у рассрочки, и только у неё.
        CheckConstraint(
            "(method = 'installment') = (installment_months IS NOT NULL)",
            name='installment_months_iff_installment',
        ),
        CheckConstraint(
            '(installment_months IS NULL) = (schedule IS NULL)',
            name='schedule_iff_installment',
        ),
    )

    tariff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('tariffs.id', ondelete='RESTRICT'),
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    method: Mapped[PaymentMethod] = mapped_column(
        _str_enum(PaymentMethod, 'payment_method'),
    )
    status: Mapped[PaymentStatus] = mapped_column(
        _str_enum(PaymentStatus, 'payment_status'),
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
        index=True,
    )

    # amount — к оплате (цена тарифа минус скидка), discount — размер скидки.
    amount: Mapped[int] = mapped_column(BigInteger)
    discount: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    promo_code_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('promo_codes.id', ondelete='RESTRICT'),
        index=True,
    )

    installment_months: Mapped[int | None] = mapped_column(SmallInteger)
    # Список сумм платежей графика в копейках, например [663334, 663333, 663333].
    # none_as_null: Python None → SQL NULL, а не JSON-значение 'null'.
    schedule: Mapped[list[int] | None] = mapped_column(JSON(none_as_null=True))

    idempotency_key: Mapped[uuid.UUID | None] = mapped_column(unique=True)

    tariff: Mapped[Tariff] = relationship(lazy='raise')
