from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.config import settings

from src.api.v1.endpoints.router import router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API Orquestradora para E-commerce e Integrações",
    docs_url="/api/docs",   # Move o Swagger para uma rota mais limpa
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # TODO: Ajustar para permitir apenas origens confiáveis em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health", tags=["System"])
async def health_check():
    """Retorna o status vital da API."""
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION
    }


# from src.api.v1.router import api_router
app.include_router(router, prefix="/api/v1")