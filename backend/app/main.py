"""
Aplicação principal FastAPI — Categorizador Inteligente de Produtos.

Configura CORS, lifecycle hooks, routers e health check.
"""

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.database import create_pool, close_pool, is_pool_ready
from app.models import HealthResponse
from app.routers import categorize, feedback

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle: inicializa e finaliza recursos da aplicação."""
    # Startup
    logger.info("🚀 Iniciando Categorizador Inteligente...")
    settings = get_settings()
    logger.info(f"   Frontend URL (CORS): {settings.frontend_url}")
    logger.info(f"   Modelo de Embedding: {settings.embedding_model} ({settings.embedding_dimensions}d)")
    logger.info(f"   Modelo LLM: {settings.llm_model}")
    logger.info(f"   Threshold Similaridade: {settings.similarity_threshold}")
    logger.info(f"   Threshold Confiança LLM: {settings.llm_confidence_threshold}%")
    logger.info(f"   PORT (Railway): {os.getenv('PORT', 'não definido')}")

    try:
        await create_pool()
        logger.info("   ✅ Pool de conexões PostgreSQL criado")
    except Exception:
        logger.exception(
            "   ❌ Falha ao conectar ao PostgreSQL — /health responde, mas a API de dados ficará indisponível"
        )

    yield

    # Shutdown
    logger.info("🛑 Encerrando aplicação...")
    await close_pool()
    logger.info("   ✅ Pool de conexões fechado")


# --- App ---
app = FastAPI(
    title="Categorizador Inteligente de Produtos",
    description=(
        "API para categorização inteligente de produtos em lote "
        "usando uma arquitetura híbrida de funil de 3 camadas: "
        "EAN/NCM → Busca Vetorial/LLM → Revisão Humana."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# --- Hardening & Security Middlewares ---
from app.middlewares import SecurityHeadersMiddleware

app.add_middleware(SecurityHeadersMiddleware)

settings = get_settings()
origins = list({
    settings.frontend_url,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
})

# CORS Restrito — inclui regex para deploys Vercel (*.vercel.app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"], # Bloqueia PUT, DELETE, PATCH
    allow_headers=["Authorization", "Content-Type", "Accept"], # Bloqueia headers maliciosos
    expose_headers=[
        "Content-Disposition",
        "X-Metrics-Total",
        "X-Metrics-Aprovados",
        "X-Metrics-Pendentes",
        "X-Processing-Time",
    ],
)

# --- Routers ---
app.include_router(categorize.router)
app.include_router(feedback.router)


# --- Health Check ---
@app.get("/health", response_model=HealthResponse, tags=["Sistema"])
async def health_check():
    """Verifica se a API está funcionando."""
    db_status = "connected" if is_pool_ready() else "unavailable"
    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        database=db_status,
    )


@app.get("/", tags=["Sistema"])
async def root():
    """Raiz da API — informações básicas."""
    return {
        "service": "Categorizador Inteligente de Produtos",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
