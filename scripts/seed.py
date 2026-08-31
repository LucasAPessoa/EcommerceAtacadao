"""
Seed de dados pra testar a conexão entre o front e o back.

Cria um dataset determinístico com todas as entidades persistentes e todos os
valores dos enums de identidade, catálogo, checkout, pagamento e logística.
Os pedidos preservam snapshots de preço/logística como o checkout transacional.

Idempotente: rodar de novo não duplica nada (busca por email/código/nome
antes de criar). Se quiser recomeçar do zero, dropa o banco e roda as
migrations de novo.

Uso (a partir da raiz do projeto, com o ambiente/.env já configurado):

    python -m scripts.seed

Se as tabelas ainda não existirem (não rodou alembic ainda), roda com:

    python -m scripts.seed --create-tables

Isso usa Base.metadata.create_all() como atalho — não substitui as
migrations de verdade, é só pra popular rápido num ambiente de teste.
"""

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from src.core.db import AsyncSessionLocal, engine
from src.core.sec import get_password_hash
from src.models import Base
from src.models.catalog import (
    Category,
    ListingAttribute,
    ListingImage,
    PricingTier,
    Product,
    ProductImage,
    ProductListing,
    ProductQuestion,
    ProductReview,
    ProductVariant,
    product_category_table,
)
from src.models.enums import (
    DiscountTypeEnum,
    OrderStatusEnum,
    PaymentMethodEnum,
    RefundStatusEnum,
    ShipmentStatusEnum,
    StockReservationStatusEnum,
    TransactionStatusEnum,
    UserTypeEnum,
)
from src.models.identity import Address, RefreshToken, Role, User
from src.models.operations import ERPWebhookLog, LocalCEPRange, Refund, Shipment, Transaction
from src.models.sales import (
    Cart,
    CartItem,
    Coupon,
    Order,
    OrderItem,
    OrderStatusHistory,
    StockReservation,
)


def placeholder_image(text: str, bg: str) -> str:
    """URL de imagem gerada na hora (só um retângulo com texto) — sem imagem real."""
    return f"https://placehold.co/800x800/{bg}/ffffff?text={text.replace(' ', '+')}"


async def get_or_create(session, model, defaults: dict | None = None, **lookup):
    result = await session.execute(select(model).filter_by(**lookup))
    instance = result.scalar_one_or_none()
    if instance:
        return instance, False
    instance = model(**lookup, **(defaults or {}))
    session.add(instance)
    await session.flush()
    return instance, True


async def validate_seed(session) -> None:
    """Falha explicitamente se alguma entidade ou valor de enum não foi criado."""
    entity_models = (
        Role,
        User,
        RefreshToken,
        Address,
        Category,
        Product,
        ProductVariant,
        ProductListing,
        ListingAttribute,
        ListingImage,
        ProductImage,
        PricingTier,
        ProductReview,
        ProductQuestion,
        Coupon,
        Cart,
        CartItem,
        Order,
        OrderItem,
        StockReservation,
        OrderStatusHistory,
        Transaction,
        Refund,
        LocalCEPRange,
        Shipment,
        ERPWebhookLog,
    )
    missing_entities = []
    for model in entity_models:
        result = await session.execute(select(model).limit(1))
        if result.scalars().first() is None:
            missing_entities.append(model.__tablename__)
    if missing_entities:
        raise RuntimeError(f"Entidades sem dados no seed: {', '.join(missing_entities)}")

    enum_columns = (
        ("user_type", User.user_type, UserTypeEnum),
        ("discount_type", Coupon.discount_type, DiscountTypeEnum),
        ("order_status", Order.status, OrderStatusEnum),
        ("payment_method", Transaction.payment_method, PaymentMethodEnum),
        ("transaction_status", Transaction.status, TransactionStatusEnum),
        ("reservation_status", StockReservation.status, StockReservationStatusEnum),
        ("refund_status", Refund.status, RefundStatusEnum),
        ("shipment_status", Shipment.status, ShipmentStatusEnum),
    )
    missing_enum_values: list[str] = []
    for name, column, enum_type in enum_columns:
        result = await session.execute(select(column).distinct())
        actual = {value.value for value in result.scalars().all()}
        expected = {value.value for value in enum_type}
        for value in sorted(expected - actual):
            missing_enum_values.append(f"{name}.{value}")
    if missing_enum_values:
        raise RuntimeError(
            "Valores de enum ausentes no seed: " + ", ".join(missing_enum_values)
        )


async def seed(create_tables: bool) -> None:
    if create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Tabelas criadas via Base.metadata.create_all().")

    async with AsyncSessionLocal() as session:
        # --- Roles ---
        admin_role, _ = await get_or_create(session, Role, name="admin")
        user_role, _ = await get_or_create(session, Role, name="user")

        # --- Usuários ---
        admin_user, admin_created = await get_or_create(
            session,
            User,
            email="admin@atacadaocenter.com.br",
            defaults=dict(
                password_hash=get_password_hash("Admin123!"),
                full_name="Admin da Loja",
                role_id=admin_role.id,
                user_type=UserTypeEnum.ADMIN,
                cpf="11122233344",
            ),
        )

        customer1, _ = await get_or_create(
            session,
            User,
            email="cliente1@example.com",
            defaults=dict(
                password_hash=get_password_hash("Cliente123!"),
                full_name="Joana Ribeiro",
                role_id=user_role.id,
                user_type=UserTypeEnum.INDIVIDUAL,
                cpf="22233344455",
            ),
        )

        customer2, _ = await get_or_create(
            session,
            User,
            email="cliente2@example.com",
            defaults=dict(
                password_hash=get_password_hash("Cliente123!"),
                full_name="Mercadinho Boa Vista Ltda",
                role_id=user_role.id,
                user_type=UserTypeEnum.COMPANY,
                cpf="33344455566",
                cnpj="12345678000199",
                corporate_name="Mercadinho Boa Vista Ltda",
            ),
        )

        # Token revogado de referência: cobre a entidade sem criar uma sessão
        # autenticável válida no dataset.
        await get_or_create(
            session,
            RefreshToken,
            token="seed-revoked-refresh-token",
            defaults=dict(
                user_id=customer1.id,
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
                revoked=True,
            ),
        )

        # --- Endereços ---
        address1, _ = await get_or_create(
            session,
            Address,
            user_id=customer1.id,
            zip_code="20040020",
            defaults=dict(
                street="Avenida Rio Branco",
                number="156",
                complement="Apto 302",
                neighborhood="Centro",
                city="Rio de Janeiro",
                state="RJ",
                is_default=True,
            ),
        )
        await get_or_create(
            session,
            Address,
            user_id=customer2.id,
            zip_code="27213100",
            defaults=dict(
                street="Rua Fonseca Hermes",
                number="890",
                complement=None,
                neighborhood="Aterrado",
                city="Volta Redonda",
                state="RJ",
                is_default=True,
            ),
        )

        # --- Categorias ---
        category_names = ["Limpeza", "Alimentos", "Bebidas", "Higiene Pessoal"]
        categories: dict[str, Category] = {}
        for name in category_names:
            category, _ = await get_or_create(
                session,
                Category,
                name=name,
                defaults=dict(description=f"Produtos de {name.lower()}", is_active=True),
            )
            categories[name] = category

        # --- Produtos + variantes ---
        # (nome, categoria, code, brand, unit, [(variacao, sku, preco, estoque, peso_kg, dims_cm)])
        product_specs = [
            (
                "Detergente Neutro 5L",
                "Limpeza",
                "DET-5L",
                "Ypê",
                "UN",
                [("Padrão", "DET-5L-UN", 24.90, 120, 5.3, (28, 15, 15))],
            ),
            (
                "Água Sanitária 5L",
                "Limpeza",
                "AGSAN-5L",
                "Qboa",
                "UN",
                [("Padrão", "AGSAN-5L-UN", 18.50, 90, 5.1, (28, 15, 15))],
            ),
            (
                "Papel Higiênico Folha Dupla",
                "Limpeza",
                "PH-FD16",
                "Personal",
                "FD",
                [("Fardo 16 rolos", "PH-FD16-UN", 39.90, 60, 3.2, (40, 30, 30))],
            ),
            (
                "Arroz Tipo 1",
                "Alimentos",
                "ARZ-T1",
                "Tio João",
                "KG",
                [
                    ("Pacote 5kg", "ARZ-T1-5KG", 27.90, 150, 5.0, (35, 20, 8)),
                    ("Saca 25kg", "ARZ-T1-25KG", 119.90, 40, 25.0, (60, 40, 15)),
                ],
            ),
            (
                "Feijão Carioca",
                "Alimentos",
                "FEI-CAR",
                "Camil",
                "KG",
                [("Pacote 1kg", "FEI-CAR-1KG", 8.90, 200, 1.0, (18, 12, 5))],
            ),
            (
                "Óleo de Soja",
                "Alimentos",
                "OLEO-SOJA",
                "Liza",
                "CX",
                [("Caixa c/ 20 (900ml)", "OLEO-SOJA-CX20", 149.90, 35, 18.0, (35, 25, 25))],
            ),
            (
                "Café Torrado e Moído",
                "Alimentos",
                "CAFE-500",
                "Pilão",
                "UN",
                [("Pacote 500g", "CAFE-500-UN", 16.90, 100, 0.5, (18, 10, 6))],
            ),
            (
                "Macarrão Espaguete",
                "Alimentos",
                "MAC-ESP",
                "Adria",
                "CX",
                [("Caixa c/ 10 (500g)", "MAC-ESP-CX10", 42.00, 55, 5.0, (30, 20, 12))],
            ),
            (
                "Refrigerante Cola 2L",
                "Bebidas",
                "REFRI-COLA-2L",
                "Coca-Cola",
                "FD",
                [("Fardo com 6", "REFRI-COLA-2L-FD6", 54.90, 45, 12.5, (40, 30, 20))],
            ),
            (
                "Água Mineral 500ml",
                "Bebidas",
                "AGUA-500",
                "Crystal",
                "FD",
                [("Fardo com 12", "AGUA-500-FD12", 15.90, 80, 6.5, (30, 20, 20))],
            ),
            (
                "Sabonete em Barra",
                "Higiene Pessoal",
                "SAB-BARRA",
                "Lux",
                "KIT",
                [("Kit com 12", "SAB-BARRA-KIT12", 22.90, 70, 1.1, (20, 15, 8))],
            ),
            (
                "Shampoo Neutro 1L",
                "Higiene Pessoal",
                "SHAMP-1L",
                "Palmolive",
                "UN",
                [
                    ("1 Litro", "SHAMP-1L-UN", 21.90, 65, 1.05, (25, 8, 8)),
                    ("Refil 1 Litro", "SHAMP-1L-REFIL", 17.90, 40, 1.0, (22, 6, 6)),
                ],
            ),
        ]

        color_by_category = {
            "Limpeza": "1e3a5f",
            "Alimentos": "c9a227",
            "Bebidas": "e0592a",
            "Higiene Pessoal": "2f7a4f",
        }

        variants_by_code: dict[str, ProductVariant] = {}

        for name, category_name, code, brand, unit, variant_specs in product_specs:
            product, _ = await get_or_create(
                session,
                Product,
                code=code,
                defaults=dict(
                    name=name,
                    description=(
                        f"{name} de qualidade, ideal pra revenda ou consumo em grande volume."
                    ),
                    is_active=True,
                    brand=brand,
                    unit=unit,
                    product_type="P",
                    format="S",
                    status="A",
                    condition=1,
                ),
            )
            existing_link = await session.execute(
                select(product_category_table).filter_by(
                    product_id=product.id, category_id=categories[category_name].id
                )
            )
            if not existing_link.first():
                await session.execute(
                    product_category_table.insert().values(
                        product_id=product.id, category_id=categories[category_name].id
                    )
                )

            for variation_name, sku, price, stock, weight, (height, width, length) in variant_specs:
                variant, created = await get_or_create(
                    session,
                    ProductVariant,
                    bling_sku=sku,
                    defaults=dict(
                        product_id=product.id,
                        variation_name=variation_name,
                        base_price=price,
                        stock_quantity=stock,
                        is_active=True,
                        weight_kg=weight,
                        height_cm=height,
                        width_cm=width,
                        length_cm=length,
                    ),
                )
                variants_by_code[sku] = variant

                if created:
                    color = color_by_category[category_name]
                    session.add(
                        ProductImage(
                            variant_id=variant.id,
                            image_url=placeholder_image(name, color),
                            is_main=True,
                        )
                    )
                    session.add(
                        ProductImage(
                            variant_id=variant.id,
                            image_url=placeholder_image(f"{name} 2", color),
                            is_main=False,
                        )
                    )

        await session.flush()

        # --- Anúncio de marketplace + atributos + imagens ---
        detergent_product_id = variants_by_code["DET-5L-UN"].product_id
        listing, _ = await get_or_create(
            session,
            ProductListing,
            bling_id=900001,
            defaults=dict(
                product_id=detergent_product_id,
                title="Detergente Neutro 5L — Atacado",
                description="Anúncio de referência sincronizado com o ERP.",
                status=1,
            ),
        )
        await get_or_create(
            session,
            ListingAttribute,
            listing_id=listing.id,
            name="Volume",
            defaults=dict(
                bling_external_id="volume-5l",
                attribute_type="measurement",
                value="5",
                unit="L",
            ),
        )
        await get_or_create(
            session,
            ListingImage,
            listing_id=listing.id,
            sort_order=1,
            defaults=dict(
                bling_id=910001,
                url=placeholder_image("Detergente Neutro 5L", "1e3a5f"),
                image_type="PRIMARY",
            ),
        )

        # --- Faixas de preço (compra em quantidade) ---
        arroz_5kg = variants_by_code["ARZ-T1-5KG"].product_id
        cafe = variants_by_code["CAFE-500-UN"].product_id
        await get_or_create(
            session,
            PricingTier,
            product_id=arroz_5kg,
            min_quantity=10,
            defaults=dict(unit_price=25.90),
        )
        await get_or_create(
            session,
            PricingTier,
            product_id=arroz_5kg,
            min_quantity=30,
            defaults=dict(unit_price=23.90),
        )
        await get_or_create(
            session, PricingTier, product_id=cafe, min_quantity=20, defaults=dict(unit_price=14.90)
        )

        # --- Avaliações e perguntas ---
        review_targets = ["DET-5L-UN", "ARZ-T1-5KG", "REFRI-COLA-2L-FD6", "SHAMP-1L-UN"]
        review_texts = [
            (5, "Chega sempre rápido e o preço compensa comprar em quantidade."),
            (4, "Bom produto, só achei a embalagem um pouco frágil pro transporte."),
            (5, "Já é a terceira vez que compro, recomendo."),
            (3, "Preço justo, mas demorou mais que o esperado pra chegar."),
        ]
        for sku, (rating, comment) in zip(review_targets, review_texts):
            variant = variants_by_code[sku]
            existing = await session.execute(
                select(ProductReview).filter_by(product_id=variant.product_id, user_id=customer1.id)
            )
            if not existing.scalar_one_or_none():
                session.add(
                    ProductReview(
                        product_id=variant.product_id,
                        user_id=customer1.id,
                        rating=rating,
                        comment=comment,
                        is_approved=True,
                    )
                )

        question_targets = ["ARZ-T1-25KG", "OLEO-SOJA-CX20", "PH-FD16-UN"]
        questions = [
            ("A saca de 25kg vem lacrada?", "Sim, lacrada de fábrica."),
            ("Tem validade mínima de quantos meses na entrega?", None),
            ("O fardo de papel higiênico é folha dupla mesmo?", "Sim, folha dupla, 30m por rolo."),
        ]
        for sku, (question_text, answer_text) in zip(question_targets, questions):
            variant = variants_by_code[sku]
            existing = await session.execute(
                select(ProductQuestion).filter_by(
                    product_id=variant.product_id, user_id=customer2.id
                )
            )
            if not existing.scalar_one_or_none():
                session.add(
                    ProductQuestion(
                        product_id=variant.product_id,
                        user_id=customer2.id,
                        question_text=question_text,
                        answer_text=answer_text,
                    )
                )

        # --- Cupons ---
        await get_or_create(
            session,
            Coupon,
            code="BEMVINDO10",
            defaults=dict(
                discount_type=DiscountTypeEnum.PERCENTAGE,
                discount_value=10,
                min_order_amount=50,
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=90),
                is_active=True,
            ),
        )
        await get_or_create(
            session,
            Coupon,
            code="FRETEGRATIS",
            defaults=dict(
                discount_type=DiscountTypeEnum.FREE_SHIPPING,
                discount_value=0,
                min_order_amount=150,
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=90),
                is_active=True,
            ),
        )
        await get_or_create(
            session,
            Coupon,
            code="MENOS15",
            defaults=dict(
                discount_type=DiscountTypeEnum.FIXED_AMOUNT,
                discount_value=15,
                min_order_amount=100,
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=90),
                is_active=True,
            ),
        )
        await get_or_create(
            session,
            Coupon,
            code="EXPIRADO",
            defaults=dict(
                discount_type=DiscountTypeEnum.PERCENTAGE,
                discount_value=20,
                min_order_amount=None,
                expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
                is_active=False,
            ),
        )

        await session.flush()

        # --- Carrinho pré-preenchido pro cliente 1 ---
        cart, _ = await get_or_create(session, Cart, user_id=customer1.id)
        await session.flush()
        for sku, qty in [("DET-5L-UN", 2), ("ARZ-T1-5KG", 1)]:
            variant = variants_by_code[sku]
            existing_item = await session.execute(
                select(CartItem).filter_by(cart_id=cart.id, variant_id=variant.id)
            )
            if not existing_item.scalar_one_or_none():
                session.add(CartItem(cart_id=cart.id, variant_id=variant.id, quantity=qty))

        # --- Pedidos e operações derivados do checkout ---
        async def create_order(
            user: User,
            order_status: OrderStatusEnum,
            items_specs: list[tuple[str, int]],
            address: Address,
            payment_method: PaymentMethodEnum,
            transaction_status: TransactionStatusEnum,
        ) -> tuple[Order, Transaction]:
            subtotal = sum(
                (Decimal(str(variants_by_code[sku].base_price)) * qty for sku, qty in items_specs),
                Decimal("0.00"),
            )
            order = Order(
                user_id=user.id,
                status=order_status,
                checkout_idempotency_key=uuid.uuid4(),
                shipping_address_snapshot={
                    "zip_code": address.zip_code,
                    "street": address.street,
                    "number": address.number,
                    "complement": address.complement,
                    "neighborhood": address.neighborhood,
                    "city": address.city,
                    "state": address.state,
                },
                discount_amount=0,
                subtotal_amount=subtotal,
                shipping_fee=Decimal("19.90"),
                total_amount=subtotal + Decimal("19.90"),
                shipping_provider="SEED",
                shipping_service_name="Entrega de demonstração",
            )
            session.add(order)
            await session.flush()

            for sku, qty in items_specs:
                variant = variants_by_code[sku]
                product_name_result = await session.execute(
                    select(Product.name).where(Product.id == variant.product_id)
                )
                product_name = product_name_result.scalar_one()
                session.add(
                    OrderItem(
                        order_id=order.id,
                        variant_id=variant.id,
                        quantity=qty,
                        unit_price_snapshot=Decimal(str(variant.base_price)),
                        base_price_snapshot=Decimal(str(variant.base_price)),
                        product_name_snapshot=product_name,
                        variation_name_snapshot=variant.variation_name,
                        sku_snapshot=variant.bling_sku,
                        pricing_tier_min_quantity=None,
                        logistics_snapshot={
                            "weight_kg": variant.weight_kg,
                            "height_cm": variant.height_cm,
                            "width_cm": variant.width_cm,
                            "length_cm": variant.length_cm,
                        },
                    )
                )

            transaction = Transaction(
                order_id=order.id,
                payment_method=payment_method,
                gateway_ref_id=f"SEED-{order_status.value}",
                amount=order.total_amount,
                installments=3 if payment_method == PaymentMethodEnum.CREDIT_CARD else 1,
                status=transaction_status,
                paid_at=(
                    datetime.now(UTC).replace(tzinfo=None)
                    if transaction_status == TransactionStatusEnum.APPROVED
                    else None
                ),
            )
            session.add(transaction)
            session.add(
                OrderStatusHistory(
                    order_id=order.id,
                    old_status=None,
                    new_status=order_status,
                    changed_by_user_id=user.id,
                )
            )
            await session.flush()
            return order, transaction

        order_scenarios = [
            (OrderStatusEnum.PENDING_PAYMENT, "CAFE-500-UN", PaymentMethodEnum.PIX,
             TransactionStatusEnum.PENDING),
            (OrderStatusEnum.PAID, "DET-5L-UN", PaymentMethodEnum.CREDIT_CARD,
             TransactionStatusEnum.PROCESSING),
            (OrderStatusEnum.PROCESSING, "ARZ-T1-5KG", PaymentMethodEnum.BOLETO,
             TransactionStatusEnum.APPROVED),
            (OrderStatusEnum.SHIPPED, "REFRI-COLA-2L-FD6", PaymentMethodEnum.PIX,
             TransactionStatusEnum.REJECTED),
            (OrderStatusEnum.DELIVERED, "AGUA-500-FD12", PaymentMethodEnum.CREDIT_CARD,
             TransactionStatusEnum.CANCELED),
            (OrderStatusEnum.CANCELED, "SAB-BARRA-KIT12", PaymentMethodEnum.BOLETO,
             TransactionStatusEnum.REFUNDED),
            (OrderStatusEnum.EXPIRED, "SHAMP-1L-UN", PaymentMethodEnum.PIX,
             TransactionStatusEnum.PARTIALLY_REFUNDED),
        ]
        orders_by_status: dict[OrderStatusEnum, Order] = {}
        transactions_by_status: dict[TransactionStatusEnum, Transaction] = {}
        for order_status, sku, payment_method, transaction_status in order_scenarios:
            existing = await session.execute(
                select(Order).filter_by(user_id=customer1.id, status=order_status)
            )
            order = existing.scalars().first()
            if order is None:
                order, transaction = await create_order(
                    customer1,
                    order_status,
                    [(sku, 1)],
                    address1,
                    payment_method,
                    transaction_status,
                )
            else:
                transaction_result = await session.execute(
                    select(Transaction).where(Transaction.order_id == order.id)
                )
                transaction = transaction_result.scalars().first()
            orders_by_status[order_status] = order
            if transaction is not None:
                transactions_by_status[transaction_status] = transaction

        # Um pedido pode registrar múltiplas tentativas de pagamento. Isso
        # permite representar todos os estados do gateway sem falsificar o
        # estado comercial do pedido.
        chargeback_transaction, _ = await get_or_create(
            session,
            Transaction,
            gateway_ref_id="SEED-CHARGEBACK",
            defaults=dict(
                order_id=orders_by_status[OrderStatusEnum.DELIVERED].id,
                payment_method=PaymentMethodEnum.CREDIT_CARD,
                amount=orders_by_status[OrderStatusEnum.DELIVERED].total_amount,
                installments=3,
                status=TransactionStatusEnum.CHARGEBACK,
            ),
        )
        transactions_by_status[TransactionStatusEnum.CHARGEBACK] = chargeback_transaction

        # --- Reservas de estoque em todos os estados ---
        reservation_scenarios = [
            (StockReservationStatusEnum.ACTIVE, OrderStatusEnum.PENDING_PAYMENT, "CAFE-500-UN"),
            (StockReservationStatusEnum.CONFIRMED, OrderStatusEnum.PAID, "DET-5L-UN"),
            (StockReservationStatusEnum.RELEASED, OrderStatusEnum.CANCELED, "SAB-BARRA-KIT12"),
            (StockReservationStatusEnum.EXPIRED, OrderStatusEnum.EXPIRED, "SHAMP-1L-UN"),
        ]
        now = datetime.now(UTC).replace(tzinfo=None)
        for reservation_status, order_status, sku in reservation_scenarios:
            await get_or_create(
                session,
                StockReservation,
                order_id=orders_by_status[order_status].id,
                variant_id=variants_by_code[sku].id,
                defaults=dict(
                    quantity=1,
                    status=reservation_status,
                    expires_at=now + timedelta(minutes=30),
                    confirmed_at=(
                        now
                        if reservation_status == StockReservationStatusEnum.CONFIRMED
                        else None
                    ),
                    released_at=(
                        now
                        if reservation_status
                        in (StockReservationStatusEnum.RELEASED, StockReservationStatusEnum.EXPIRED)
                        else None
                    ),
                ),
            )

        # --- Frete local e remessas em todos os estados ---
        local_range, _ = await get_or_create(
            session,
            LocalCEPRange,
            cep_start="20000000",
            cep_end="20999999",
            defaults=dict(neighborhood="Centro/RJ", shipping_rate=Decimal("12.50")),
        )
        shipment_scenarios = [
            (ShipmentStatusEnum.PREPARING, OrderStatusEnum.PROCESSING),
            (ShipmentStatusEnum.SHIPPED, OrderStatusEnum.SHIPPED),
            (ShipmentStatusEnum.DELIVERED, OrderStatusEnum.DELIVERED),
            (ShipmentStatusEnum.RETURNED, OrderStatusEnum.CANCELED),
        ]
        for shipment_status, order_status in shipment_scenarios:
            order = orders_by_status[order_status]
            await get_or_create(
                session,
                Shipment,
                order_id=order.id,
                defaults=dict(
                    local_cep_id=local_range.id,
                    provider="SEED-LOGISTICS",
                    tracking_code=f"TRACK-{shipment_status.value}",
                    shipping_cost=order.shipping_fee,
                    status=shipment_status,
                    shipped_at=(now if shipment_status != ShipmentStatusEnum.PREPARING else None),
                    delivered_at=(now if shipment_status == ShipmentStatusEnum.DELIVERED else None),
                ),
            )

        # --- Reembolsos em todos os estados ---
        refund_order = orders_by_status[OrderStatusEnum.CANCELED]
        refund_transaction = transactions_by_status[TransactionStatusEnum.REFUNDED]
        for refund_status in RefundStatusEnum:
            await get_or_create(
                session,
                Refund,
                order_id=refund_order.id,
                reason=f"SEED-{refund_status.value}",
                defaults=dict(
                    transaction_id=refund_transaction.id,
                    amount_refunded=Decimal("5.00"),
                    status=refund_status,
                    completed_at=(now if refund_status == RefundStatusEnum.COMPLETED else None),
                ),
            )

        # --- Auditoria da integração ERP ---
        await get_or_create(
            session,
            ERPWebhookLog,
            event_type="stock.updated",
            related_sku="DET-5L-UN",
            defaults=dict(
                payload={"sku": "DET-5L-UN", "stock": 120},
                status="PROCESSED",
            ),
        )

        await session.flush()
        await validate_seed(session)
        await session.commit()

    print("\nSeed concluído e validado: todas as entidades e enums estão representados.")
    print("\nLogins pra testar:")
    print("  admin      -> admin@atacadaocenter.com.br / Admin123!")
    print("  cliente 1  -> cliente1@example.com / Cliente123!  (já com carrinho e pedidos)")
    print("  cliente 2  -> cliente2@example.com / Cliente123!")
    print("\nCupons: BEMVINDO10 (10% acima de R$50) | FRETEGRATIS (frete grátis acima de R$150)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Popula o banco com dados de teste.")
    parser.add_argument(
        "--create-tables",
        action="store_true",
        help=(
            "Roda Base.metadata.create_all() antes de popular "
            "(atalho pra quem ainda não rodou as migrations)."
        ),
    )
    args = parser.parse_args()
    asyncio.run(seed(create_tables=args.create_tables))
