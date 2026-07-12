import asyncio
from sqlalchemy import select
# Adapte os imports abaixo para a realidade do teu projeto "EcommerceAtacadao"
from core.db import AsyncSessionLocal # Tua fábrica de sessões assíncronas
from models import Role # O teu modelo de Role/Perfil

async def seed_roles():
    print("Iniciando o seed de Roles...")
    
    # As roles que precisamos no sistema
    roles_to_create = ["admin", "customer"]

    async with AsyncSessionLocal() as session:
        for role_name in roles_to_create:
            # Verifica se a role já existe no banco
            query = select(Role).where(Role.name == role_name)
            result = await session.execute(query)
            existing_role = result.scalars().first()

            if existing_role:
                print(f"La role '{role_name}' já existe. Saltando...")
            else:
                # Se não existe, a gente cria e adiciona na sessão
                new_role = Role(name=role_name)
                session.add(new_role)
                print(f"Role '{role_name}' preparada para inserção.")

        # Commita tudo de uma vez no final
        try:
            await session.commit()
            print("¡Excelente! Seed de roles finalizado com sucesso.")
        except Exception as e:
            await session.rollback()
            print(f"Ocurrió un error ao salvar no banco: {e}")

if __name__ == "__main__":
    # Roda o loop assíncrono
    asyncio.run(seed_roles())