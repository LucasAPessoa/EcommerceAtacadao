import enum


class UserTypeEnum(str, enum.Enum):
    INDIVIDUAL = "INDIVIDUAL"
    COMPANY = "COMPANY"
    ADMIN = "ADMIN"


class OrderStatusEnum(str, enum.Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAYMENT_RECONCILIATION = "PAYMENT_RECONCILIATION"
    PAID = "PAID"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"


class PaymentMethodEnum(str, enum.Enum):
    MERCADO_PAGO = "MERCADO_PAGO"
    PIX = "PIX"
    CREDIT_CARD = "CREDIT_CARD"
    BOLETO = "BOLETO"


class TransactionStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    CHARGEBACK = "CHARGEBACK"


class StockReservationStatusEnum(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CONFIRMED = "CONFIRMED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class RefundStatusEnum(str, enum.Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


class ReconciliationStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"


class ReconciliationReasonEnum(str, enum.Enum):
    STOCK_COMMIT_FAILED = "STOCK_COMMIT_FAILED"
    CANCELED_ORDER_APPROVED = "CANCELED_ORDER_APPROVED"


class ReconciliationOutcomeEnum(str, enum.Enum):
    FULFILLMENT_CONFIRMED = "FULFILLMENT_CONFIRMED"
    REFUND_REQUESTED = "REFUND_REQUESTED"
    REFUNDED = "REFUNDED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ShipmentStatusEnum(str, enum.Enum):
    PREPARING = "PREPARING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    RETURNED = "RETURNED"


class DiscountTypeEnum(str, enum.Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"
    FREE_SHIPPING = "FREE_SHIPPING"
