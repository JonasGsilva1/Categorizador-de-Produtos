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
from app.models import RespostaSaude

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
    # Inicialização (Startup)
    logger.info("🚀 Iniciando Categorizador Inteligente...")
    configuracoes = get_settings()
    logger.info(f"   Frontend URL (CORS): {configuracoes.frontend_url}")
    logger.info(f"   Threshold Similaridade: {configuracoes.similarity_threshold}")
    logger.info(f"   PORT (Railway): {os.getenv('PORT', 'não definido')}")

    # Garante que a pool seja criada com sucesso, senão a aplicação não iniciará.
    await create_pool()
    logger.info("   ✅ Pool de conexões PostgreSQL criado")

    yield

    # Desligamento (Shutdown)
    logger.info("🛑 Encerrando aplicação...")
    await close_pool()
    logger.info("   ✅ Pool de conexões fechado")


# --- App ---
_configuracoes = get_settings()
_eh_prod = _configuracoes.environment.lower() == "production"

app = FastAPI(
    title="Categorizador Inteligente de Produtos",
    description=(
        "API para categorização inteligente de produtos em lote "
        "usando uma arquitetura híbrida de funil de 3 camadas: "
        "EAN/NCM → Busca Vetorial/LLM → Revisão Humana."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _eh_prod else "/docs",
    redoc_url=None if _eh_prod else "/redoc",
    openapi_url=None if _eh_prod else "/openapi.json"
)

# --- Middlewares de Hardening e Segurança ---
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from app.middlewares import SecurityHeadersMiddleware, RequestIDMiddleware, RateLimitMiddleware

# Ordem dos Middlewares: de fora pra dentro (são executados de baixo pra cima no código)
# 1. Trusted Host (O mais básico, rejeita hosts inválidos antes de tudo)
# O Vercel faz proxy server-side, então o header Host que chega no Railway pode ser:
#   - o próprio domínio do Railway (requisições diretas)
#   - o domínio do Vercel (quando o Next.js Route Handler faz fetch para cá)
# Por isso sempre incluímos ambos. Se ALLOWED_HOSTS=* o middleware aceita qualquer host.
_hosts_crus = [h.strip() for h in _configuracoes.allowed_hosts.split(",") if h.strip()]

# Garante que domínios essenciais sempre estão presentes, independente da env var
_hosts_essenciais = [
    "localhost",
    "127.0.0.1",
    "categorizador-production.up.railway.app",
    "categorizador-de-produtos.vercel.app",
    "*.up.railway.app",
    "*.vercel.app",
]

if "*" in _hosts_crus:
    # Se curinga (wildcard) total, passa direto — permite tudo
    _hosts_permitidos = ["*"]
else:
    _hosts_permitidos = list(set(_hosts_crus + _hosts_essenciais))

app.add_middleware(TrustedHostMiddleware, allowed_hosts=_hosts_permitidos)

# 2. CORS (Executado depois do Trusted Host)

# 3. Security Headers (CSP, HSTS, etc)
app.add_middleware(SecurityHeadersMiddleware)

# 4. Rate Limiter (Protege rotas de brute force/DDoS)
app.add_middleware(RateLimitMiddleware)

# 5. Request ID (Para LGPD / Rastreabilidade)
app.add_middleware(RequestIDMiddleware)

# --- CORS ---
# Usa função preguicosa (lazy) para não quebrar no import se as variáveis de ambiente não existirem
def _obter_origens_cors():
    try:
        cfg = get_settings()
        return list({
            cfg.frontend_url,
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
    allow_origins=_obter_origens_cors(),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"], # Bloqueia PUT, DELETE
    allow_headers=["Authorization", "Content-Type", "Accept"], # Bloqueia headers maliciosos
    expose_headers=[
        "Content-Disposition",
        "X-Metrics-Total",
        "X-Metrics-Aprovados",
        "X-Metrics-Pendentes",
        "X-Processing-Time",
    ],
)

# --- Roteadores (Routers) ---
from app.routers import categorize, feedback

app.include_router(categorize.router)
app.include_router(feedback.router)


# --- Manipulador Global de Exceções (LGPD) ---
from fastapi.responses import JSONResponse
import traceback

@app.exception_handler(Exception)
async def manipulador_excecao_global(request, excecao):
    """
    Impede que stacktraces ou detalhes internos do DB/App vazem para o cliente.
    Loga tudo internamente, mas retorna erro genérico 500.
    """
    id_requisicao = getattr(request.state, 'req_id', 'unknown')
    logger.error(f"[ReqID: {id_requisicao}] Erro interno não tratado: {excecao}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno no servidor. Tente novamente mais tarde.", "req_id": id_requisicao}
    )

# --- Verificação de Saúde (Health Check) ---
@app.get("/health", response_model=RespostaSaude, tags=["Sistema"])
async def verificacao_saude():
    """Verifica se a API está funcionando."""
    try:
        status_db = "connected" if is_pool_ready() else "unavailable"
        return RespostaSaude(
            status="ok" if status_db == "connected" else "degraded",
            database=status_db,
        )
    except Exception as excecao:
        logger.error(f"Erro na verificação de saúde: {excecao}")
        return RespostaSaude(status="error", database="error")


@app.get("/", tags=["Sistema"])
async def root():
    """Raiz da API — informações básicas."""
    return {
        "service": "Categorizador Inteligente de Produtos",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
