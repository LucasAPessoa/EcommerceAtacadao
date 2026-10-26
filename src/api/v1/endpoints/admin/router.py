from fastapi import APIRouter, Depends

from src.api.v1.endpoints.admin.dashboard import router as dashboard_router
from src.api.v1.endpoints.admin.orders import router as orders_router
from src.api.v1.endpoints.admin.products import router as products_router
from src.core.sec import require_role

# Autorização no router: vale para toda rota /admin/*, antes de qualquer leitura.
admin_router = APIRouter(prefix="/admin", dependencies=[Depends(require_role(["admin"]))])

admin_router.include_router(products_router)
admin_router.include_router(orders_router)
admin_router.include_router(dashboard_router)
