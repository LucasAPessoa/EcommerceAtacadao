"""add transactional checkout

Revision ID: 31a9c6e2f4b8
Revises: 7047b95fc407
Create Date: 2026-08-30 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "31a9c6e2f4b8"
down_revision: Union[str, Sequence[str], None] = "7047b95fc407"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE orderstatusenum RENAME VALUE 'PENDING' TO 'PENDING_PAYMENT'")
    op.execute("ALTER TYPE orderstatusenum RENAME VALUE 'APPROVED' TO 'PAID'")
    op.execute("ALTER TYPE orderstatusenum RENAME VALUE 'PREPARING' TO 'PROCESSING'")
    op.execute("ALTER TYPE orderstatusenum ADD VALUE IF NOT EXISTS 'EXPIRED'")

    op.execute("ALTER TYPE transactionstatusenum RENAME VALUE 'COMPLETED' TO 'APPROVED'")
    op.execute("ALTER TYPE transactionstatusenum RENAME VALUE 'FAILED' TO 'REJECTED'")
    for value in (
        "PROCESSING",
        "CANCELED",
        "PARTIALLY_REFUNDED",
        "CHARGEBACK",
    ):
        op.execute(f"ALTER TYPE transactionstatusenum ADD VALUE IF NOT EXISTS '{value}'")

    reservation_status = postgresql.ENUM(
        "ACTIVE",
        "CONFIRMED",
        "RELEASED",
        "EXPIRED",
        name="stockreservationstatusenum",
    )
    op.alter_column(
        "product_variants",
        "base_price",
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        postgresql_using="base_price::numeric(12,2)",
        existing_nullable=False,
    )
    op.alter_column(
        "pricing_tiers",
        "unit_price",
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        postgresql_using="unit_price::numeric(12,2)",
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_product_variants_price_non_negative",
        "product_variants",
        "base_price >= 0",
    )
    op.create_check_constraint(
        "ck_product_variants_stock_non_negative",
        "product_variants",
        "stock_quantity >= 0",
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY product_id, min_quantity
                       ORDER BY updated_at DESC, id
                   ) AS row_number
            FROM pricing_tiers
        )
        DELETE FROM pricing_tiers target
        USING ranked
        WHERE target.id = ranked.id AND ranked.row_number > 1
        """
    )
    op.create_unique_constraint(
        "uq_pricing_tiers_product_min",
        "pricing_tiers",
        ["product_id", "min_quantity"],
    )
    op.create_check_constraint("ck_pricing_tiers_min_quantity", "pricing_tiers", "min_quantity > 1")
    op.create_check_constraint(
        "ck_pricing_tiers_price_non_negative", "pricing_tiers", "unit_price >= 0"
    )

    op.add_column(
        "orders",
        sa.Column("checkout_idempotency_key", sa.UUID(), nullable=True),
    )
    op.add_column("orders", sa.Column("subtotal_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column(
        "orders",
        sa.Column("currency", sa.String(3), nullable=False, server_default="BRL"),
    )
    op.add_column(
        "orders",
        sa.Column("shipping_provider", sa.String(80), nullable=False, server_default="LEGACY"),
    )
    op.add_column("orders", sa.Column("shipping_service_id", sa.Integer()))
    op.add_column("orders", sa.Column("shipping_service_name", sa.String(100)))
    op.add_column("orders", sa.Column("shipping_delivery_time_days", sa.Integer()))
    op.execute(
        """
        UPDATE orders
        SET subtotal_amount = GREATEST(
            total_amount - shipping_fee + discount_amount,
            0
        )
        """
    )
    op.alter_column("orders", "subtotal_amount", nullable=False)
    op.alter_column(
        "orders",
        "total_amount",
        existing_type=sa.Numeric(10, 2),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
    )

    op.add_column(
        "order_items",
        sa.Column("base_price_snapshot", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column("order_items", sa.Column("product_name_snapshot", sa.String(255)))
    op.add_column("order_items", sa.Column("variation_name_snapshot", sa.String(100)))
    op.add_column("order_items", sa.Column("sku_snapshot", sa.String(100)))
    op.add_column("order_items", sa.Column("pricing_tier_min_quantity", sa.Integer()))
    op.add_column("order_items", sa.Column("logistics_snapshot", postgresql.JSONB()))
    op.execute(
        """
        UPDATE order_items oi
        SET base_price_snapshot = oi.unit_price_snapshot,
            product_name_snapshot = p.name,
            variation_name_snapshot = pv.variation_name,
            sku_snapshot = pv.bling_sku,
            logistics_snapshot = jsonb_build_object(
                'weight_kg', pv.weight_kg,
                'height_cm', pv.height_cm,
                'width_cm', pv.width_cm,
                'length_cm', pv.length_cm
            )
        FROM product_variants pv
        JOIN products p ON p.id = pv.product_id
        WHERE oi.variant_id = pv.id
        """
    )
    for column in (
        "base_price_snapshot",
        "product_name_snapshot",
        "variation_name_snapshot",
        "sku_snapshot",
        "logistics_snapshot",
    ):
        op.alter_column("order_items", column, nullable=False)

    # Versões anteriores permitiam linhas repetidas para o mesmo SKU. A
    # consolidação preserva a quantidade antes de aplicar as constraints.
    for table, owner_column in (
        ("cart_items", "cart_id"),
        ("order_items", "order_id"),
    ):
        op.execute(
            f"""
            WITH ranked AS (
                SELECT id,
                       SUM(quantity) OVER (
                           PARTITION BY {owner_column}, variant_id
                       ) AS total_quantity,
                       ROW_NUMBER() OVER (
                           PARTITION BY {owner_column}, variant_id
                           ORDER BY created_at, id
                       ) AS row_number
                FROM {table}
            )
            UPDATE {table} target
            SET quantity = ranked.total_quantity
            FROM ranked
            WHERE target.id = ranked.id AND ranked.row_number = 1
            """
        )
        op.execute(
            f"""
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY {owner_column}, variant_id
                           ORDER BY created_at, id
                       ) AS row_number
                FROM {table}
            )
            DELETE FROM {table} target
            USING ranked
            WHERE target.id = ranked.id AND ranked.row_number > 1
            """
        )

    op.create_unique_constraint(
        "uq_cart_items_cart_variant", "cart_items", ["cart_id", "variant_id"]
    )
    op.create_check_constraint("ck_cart_items_quantity_positive", "cart_items", "quantity > 0")
    op.create_unique_constraint(
        "uq_order_items_order_variant", "order_items", ["order_id", "variant_id"]
    )
    op.create_check_constraint("ck_order_items_quantity_positive", "order_items", "quantity > 0")
    op.create_check_constraint(
        "ck_order_items_price_non_negative",
        "order_items",
        "unit_price_snapshot >= 0",
    )
    op.create_unique_constraint(
        "uq_orders_user_checkout_idempotency",
        "orders",
        ["user_id", "checkout_idempotency_key"],
    )
    op.create_check_constraint("ck_orders_subtotal_non_negative", "orders", "subtotal_amount >= 0")
    op.create_check_constraint("ck_orders_discount_non_negative", "orders", "discount_amount >= 0")
    op.create_check_constraint("ck_orders_shipping_non_negative", "orders", "shipping_fee >= 0")
    op.create_check_constraint("ck_orders_total_non_negative", "orders", "total_amount >= 0")
    op.create_check_constraint("ck_transactions_amount_non_negative", "transactions", "amount >= 0")
    op.create_check_constraint(
        "ck_transactions_installments_positive", "transactions", "installments >= 1"
    )

    op.create_table(
        "stock_reservations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("variant_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", reservation_status, nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime()),
        sa.Column("released_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_stock_reservations_quantity_positive"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "variant_id", name="uq_stock_reservations_order_variant"),
    )
    op.create_index("ix_stock_reservations_order_id", "stock_reservations", ["order_id"])
    op.create_index("ix_stock_reservations_variant_id", "stock_reservations", ["variant_id"])
    op.create_index("ix_stock_reservations_status", "stock_reservations", ["status"])
    op.create_index("ix_stock_reservations_expires_at", "stock_reservations", ["expires_at"])


def downgrade() -> None:
    op.drop_table("stock_reservations")
    postgresql.ENUM(name="stockreservationstatusenum").drop(op.get_bind(), checkfirst=True)

    for name, table in (
        ("ck_transactions_installments_positive", "transactions"),
        ("ck_transactions_amount_non_negative", "transactions"),
        ("ck_orders_total_non_negative", "orders"),
        ("ck_orders_shipping_non_negative", "orders"),
        ("ck_orders_discount_non_negative", "orders"),
        ("ck_orders_subtotal_non_negative", "orders"),
        ("uq_orders_user_checkout_idempotency", "orders"),
        ("ck_order_items_price_non_negative", "order_items"),
        ("ck_order_items_quantity_positive", "order_items"),
        ("uq_order_items_order_variant", "order_items"),
        ("ck_cart_items_quantity_positive", "cart_items"),
        ("uq_cart_items_cart_variant", "cart_items"),
        ("ck_pricing_tiers_price_non_negative", "pricing_tiers"),
        ("ck_pricing_tiers_min_quantity", "pricing_tiers"),
        ("uq_pricing_tiers_product_min", "pricing_tiers"),
        ("ck_product_variants_stock_non_negative", "product_variants"),
        ("ck_product_variants_price_non_negative", "product_variants"),
    ):
        constraint_type = "unique" if name.startswith("uq_") else "check"
        op.drop_constraint(name, table, type_=constraint_type)

    for column in (
        "logistics_snapshot",
        "pricing_tier_min_quantity",
        "sku_snapshot",
        "variation_name_snapshot",
        "product_name_snapshot",
        "base_price_snapshot",
    ):
        op.drop_column("order_items", column)

    for column in (
        "shipping_delivery_time_days",
        "shipping_service_name",
        "shipping_service_id",
        "shipping_provider",
        "currency",
        "subtotal_amount",
        "checkout_idempotency_key",
    ):
        op.drop_column("orders", column)

    op.alter_column(
        "orders",
        "total_amount",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Numeric(10, 2),
        existing_nullable=False,
    )
    op.alter_column(
        "pricing_tiers",
        "unit_price",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Float(),
        postgresql_using="unit_price::double precision",
        existing_nullable=False,
    )
    op.alter_column(
        "product_variants",
        "base_price",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Float(),
        postgresql_using="base_price::double precision",
        existing_nullable=False,
    )

    op.execute("UPDATE orders SET status = 'CANCELED' WHERE status = 'EXPIRED'")
    op.execute("ALTER TYPE orderstatusenum RENAME VALUE 'PROCESSING' TO 'PREPARING'")
    op.execute("ALTER TYPE orderstatusenum RENAME VALUE 'PAID' TO 'APPROVED'")
    op.execute("ALTER TYPE orderstatusenum RENAME VALUE 'PENDING_PAYMENT' TO 'PENDING'")
    op.execute(
        "UPDATE transactions SET status = 'REJECTED' WHERE status IN ('PROCESSING', 'CANCELED')"
    )
    op.execute(
        "UPDATE transactions SET status = 'REFUNDED' "
        "WHERE status IN ('PARTIALLY_REFUNDED', 'CHARGEBACK')"
    )
    op.execute("ALTER TYPE transactionstatusenum RENAME VALUE 'REJECTED' TO 'FAILED'")
    op.execute("ALTER TYPE transactionstatusenum RENAME VALUE 'APPROVED' TO 'COMPLETED'")
