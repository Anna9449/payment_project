from sqlalchemy import BigInteger, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Tariff(Base):
    """Тариф курса. Цена — в копейках."""

    __tablename__ = 'tariffs'
    __table_args__ = (
        CheckConstraint('price > 0', name='price_positive'),
    )

    title: Mapped[str] = mapped_column(String(50), unique=True)
    price: Mapped[int] = mapped_column(BigInteger)
