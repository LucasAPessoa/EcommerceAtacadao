from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from src.core.config import settings
from fastapi.responses import JSONResponse

from src.api.v1.endpoints.router import router

DATABASE_ERROR_MESSAGES = {
    "UniqueViolationError": "Já existe um registro com estes dados no sistema.",
    "ForeignKeyViolationError": "O registro associado não existe ou foi removido.",
    "NotNullViolationError": "Um campo obrigatório não foi preenchido no banco de dados.",
    "CheckViolationError": "Os dados fornecidos não atendem às regras de validação do banco."
}

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

# ==========================================
# TRATAMENTO DE ERROS GLOBAL (BaseResponse)
# ==========================================

@app.exception_handler(IntegrityError)
async def global_error_handler(request: Request, exc: IntegrityError):
    error_str = str(exc.orig) if exc.orig else str(exc)
    
    friendly_message = "Ocorreu um conflito de dados ao tentar salvar."
    
    for error_key, message in DATABASE_ERROR_MESSAGES.items():
        if error_key in error_str:
            friendly_message = message
            break 

    return JSONResponse(
        status_code=409,
        content={
            "status": "error",
            "message": friendly_message,
            "data": None,
            "errors": [error_str] 
        }
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