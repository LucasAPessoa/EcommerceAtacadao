"""Executa manualmente o job de manutenção de pagamentos.

Uso:
    python -m scripts.run_payment_maintenance [--batch-size 50]

Usa o banco configurado em DATABASE_URL e o Mercado Pago configurado no ambiente.
"""

import argparse
import asyncio
import logging

from src.core.db import AsyncSessionLocal, engine
from src.services.sales.payment_maintenance_service import PaymentMaintenanceService


async def main(batch_size: int) -> None:
    try:
        result = await PaymentMaintenanceService(AsyncSessionLocal).run(batch_size=batch_size)
    finally:
        await engine.dispose()
    print(result.as_dict())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=50)
    asyncio.run(main(parser.parse_args().batch_size))
