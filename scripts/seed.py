"""
Seed de dados pra testar a conexão entre o front e o back.

Cria: roles, usuários (1 admin + 2 clientes), categorias, produtos com
variantes (peso/dimensões preenchidos pra cotação de frete funcionar),
imagens (URLs de placeholder, nenhuma imagem real), faixas de preço,
avaliações, perguntas, endereços, cupons, um carrinho já com item, e
pedidos em status diferentes (pendente/enviado/cancelado) pra dar pra ver
a tela de pedidos populada sem precisar clicar em nada antes.

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
    PricingTier,
    Product,
    ProductImage,
    ProductQuestion,
    ProductReview,
    ProductVariant,
    product_category_table,
)
from src.models.enums import DiscountTypeEnum, OrderStatusEnum, PaymentMethodEnum, UserTypeEnum
from src.models.identity import Address, Role, User
from src.models.operations import Transaction
from src.models.sales import Cart, CartItem, Coupon, Order, OrderItem, OrderStatusHistory


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

        # --- Pedidos em status diferentes ---
        async def create_order(
            user: User,
            status: OrderStatusEnum,
            items_specs: list[tuple[str, int]],
            address: Address,
        ) -> None:
            subtotal = sum(variants_by_code[sku].base_price * qty for sku, qty in items_specs)
            order = Order(
                user_id=user.id,
                status=status,
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
                session.add(
                    OrderItem(
                        order_id=order.id,
                        variant_id=variant.id,
                        quantity=qty,
                        unit_price_snapshot=variant.base_price,
                        base_price_snapshot=variant.base_price,
                        product_name_snapshot=variant.product.name,
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

            session.add(
                Transaction(
                    order_id=order.id,
                    payment_method=PaymentMethodEnum.PIX,
                    amount=order.total_amount,
                    installments=1,
                )
            )
            session.add(
                OrderStatusHistory(
                    order_id=order.id,
                    old_status=None,
                    new_status=status,
                    changed_by_user_id=user.id,
                )
            )

        existing_orders = await session.execute(select(Order).filter_by(user_id=customer1.id))
        if not existing_orders.scalars().first():
            await create_order(
                customer1, OrderStatusEnum.PENDING_PAYMENT, [("CAFE-500-UN", 3)], address1
            )
            await create_order(
                customer1,
                OrderStatusEnum.SHIPPED,
                [("REFRI-COLA-2L-FD6", 2), ("AGUA-500-FD12", 1)],
                address1,
            )
            await create_order(
                customer1, OrderStatusEnum.CANCELED, [("SAB-BARRA-KIT12", 1)], address1
            )

        await session.commit()

    print("\nSeed concluído.")
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
