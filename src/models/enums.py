import enum

class UserTypeEnum(str, enum.Enum):
    RETAIL = "RETAIL"
    WHOLESALE = "WHOLESALE"
    ADMIN = "ADMIN"

class OrderStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PREPARING = "PREPARING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELED = "CANCELED"

class PaymentMethodEnum(str, enum.Enum):
    PIX = "PIX"
    CREDIT_CARD = "CREDIT_CARD"
    BOLETO = "BOLETO"

class TransactionStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"

class RefundStatusEnum(str, enum.Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"

class ShipmentStatusEnum(str, enum.Enum):
    PREPARING = "PREPARING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    RETURNED = "RETURNED"

class DiscountTypeEnum(str, enum.Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"
    FREE_SHIPPING = "FREE_SHIPPING"