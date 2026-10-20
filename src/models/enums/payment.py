import enum


class PaymentMethod(enum.StrEnum):
    CARD = 'card'
    SBP = 'sbp'
    INSTALLMENT = 'installment'


class PaymentStatus(enum.StrEnum):
    PENDING = 'pending'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    REFUNDED = 'refunded'
