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

    # Garante que a pool seja criada com sucesso, senão a aplicação não iniciará.
    await create_pool()
    logger.info("   ✅ Pool de conexões PostgreSQL criado")

    yield

    # Shutdown
    logger.info("🛑 Encerrando aplicação...")
    await close_pool()
    logger.info("   ✅ Pool de conexões fechado")


# --- App ---
_settings = get_settings()
_is_prod = _settings.environment.lower() == "production"

app = FastAPI(
    title="Categorizador Inteligente de Produtos",
    description=(
        "API para categorização inteligente de produtos em lote "
        "usando uma arquitetura híbrida de funil de 3 camadas: "
        "EAN/NCM → Busca Vetorial/LLM → Revisão Humana."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json"
)

# --- Hardening & Security Middlewares ---
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from app.middlewares import SecurityHeadersMiddleware, RequestIDMiddleware, RateLimitMiddleware

# Ordem dos Middlewares: de fora pra dentro (são executados de baixo pra cima no código)
# 1. Trusted Host (O mais básico, rejeita hosts inválidos antes de tudo)
# O Vercel faz proxy server-side, então o header Host que chega no Railway pode ser:
#   - o próprio domínio do Railway (requisições diretas)
#   - o domínio do Vercel (quando o Next.js Route Handler faz fetch para cá)
# Por isso sempre incluímos ambos. Se ALLOWED_HOSTS=* o middleware aceita qualquer host.
_raw_hosts = [h.strip() for h in _settings.allowed_hosts.split(",") if h.strip()]

# Garante que domínios essenciais sempre estão presentes, independente da env var
_essential_hosts = [
    "localhost",
    "127.0.0.1",
    "categorizador-production.up.railway.app",
    "categorizador-de-produtos.vercel.app",
    "*.up.railway.app",
    "*.vercel.app",
]

if "*" in _raw_hosts:
    # Se wildcard total, passa direto — permite tudo
    _allowed_hosts = ["*"]
else:
    _allowed_hosts = list(set(_raw_hosts + _essential_hosts))

app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)

# 2. CORS (Executado depois do Trusted Host)

# 3. Security Headers (CSP, HSTS, etc)
app.add_middleware(SecurityHeadersMiddleware)

# 4. Rate Limiter (Protege rotas de brute force/DDoS)
app.add_middleware(RateLimitMiddleware)

# 5. Request ID (Para LGPD / Rastreabilidade)
app.add_middleware(RequestIDMiddleware)

# --- CORS ---
# Usa funcao lazy para nao crashar no import se as env vars nao existirem
def _get_cors_origins():
    try:
        s = get_settings()
        return list({
            s.frontend_url,
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://categorizador.vercel.app",
            "https://categorizador-production.up.railway.app",
        })
    except Exception:
        return [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://categorizador.vercel.app",
            "https://categorizador-production.up.railway.app",
        ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
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
from app.routers import categorize, feedback

app.include_router(categorize.router)
app.include_router(feedback.router)


# --- Global Exception Handler (LGPD) ---
from fastapi.responses import JSONResponse
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Impede que stacktraces ou detalhes internos do DB/App vazem para o cliente.
    Loga tudo internamente, mas retorna erro genérico 500.
    """
    req_id = getattr(request.state, 'req_id', 'unknown')
    logger.error(f"[ReqID: {req_id}] Erro interno não tratado: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno no servidor. Tente novamente mais tarde.", "req_id": req_id}
    )

# --- Health Check ---
@app.get("/health", response_model=HealthResponse, tags=["Sistema"])
async def health_check():
    """Verifica se a API esta funcionando."""
    try:
        db_status = "connected" if is_pool_ready() else "unavailable"
        return HealthResponse(
            status="ok" if db_status == "connected" else "degraded",
            database=db_status,
        )
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthResponse(status="error", database="error")


@app.get("/", tags=["Sistema"])
async def root():
    """Raiz da API — informações básicas."""
    return {
        "service": "Categorizador Inteligente de Produtos",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
