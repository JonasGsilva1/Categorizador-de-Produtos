"""
Middlewares de Segurança e Proteção.
Implementa OWASP Headers, Rate Limiting em memória e rastreabilidade (LGPD).
"""

import time
import uuid
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import get_settings

logger = logging.getLogger(__name__)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware que adiciona cabeçalhos de segurança (OWASP) em todas as respostas."""
    async def dispatch(self, request: Request, call_next):
        resposta = await call_next(request)
        
        # HSTS: Força HTTPS
        resposta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        # Previne MIME Sniffing
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        # Previne Clickjacking (Permitir do mesmo origin, ou bloqueio total se API)
        resposta.headers["X-Frame-Options"] = "DENY"
        # Previne XSS
        resposta.headers["X-XSS-Protection"] = "1; mode=block"
        # Esconde o servidor
        resposta.headers["Server"] = "Hidden"
        
        # --- Novos Cabeçalhos de Segurança (OWASP Moderno) ---
        # CSP: API não deve executar scripts nem carregar iframes
        resposta.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        # Previne acesso a recursos do dispositivo pelo browser
        resposta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Não vaza a URL da API em requests subsequentes
        resposta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Não cachear respostas da API (proteção de dados Pessoais/LGPD)
        resposta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
        resposta.headers["Pragma"] = "no-cache"

        return resposta


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Injeta um ID único por requisição para rastreabilidade (Auditoria/LGPD)."""
    async def dispatch(self, request: Request, call_next):
        id_requisicao = str(uuid.uuid4())
        request.state.req_id = id_requisicao
        
        resposta = await call_next(request)
        resposta.headers["X-Request-ID"] = id_requisicao
        return resposta


# --- Limitador de Taxa (Rate Limiter) em Memória ---
# Usamos um dicionário simples. Para múltiplas instâncias no futuro, migrar para Redis.
_LIMITES_TAXA = {}

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Protege contra DDoS e Brute Force limitando requisições por IP."""
    async def dispatch(self, request: Request, call_next):
        configuracoes = get_settings()
        
        # Limpar registros antigos a cada request (simplificado para em memória)
        # O ideal seria uma tarefa em background, mas para evitar complexidade mantemos aqui
        agora = time.time()
        
        # Obter IP real (lidando com proxy do Railway)
        ip_cliente = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1")
        ip_cliente = ip_cliente.split(",")[0].strip()
        
        # Definir limites baseados na rota
        caminho = request.url.path
        eh_upload = caminho == "/api/categorize" and request.method == "POST"
        limite = configuracoes.upload_rate_limit_per_minute if eh_upload else configuracoes.rate_limit_per_minute
        janela = 60  # 1 minuto
        
        chave = f"{ip_cliente}:{caminho}"
        
        # Inicializa se não existir
        if chave not in _LIMITES_TAXA:
            _LIMITES_TAXA[chave] = {"contagem": 0, "inicio": agora}
            
        registro = _LIMITES_TAXA[chave]
        
        # Resetar a janela de tempo se passou 1 minuto
        if agora - registro["inicio"] > janela:
            registro["contagem"] = 0
            registro["inicio"] = agora
            
        registro["contagem"] += 1
        
        if registro["contagem"] > limite:
            logger.warning(f"Limite de taxa excedido para IP {ip_cliente} em {caminho}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Muitas requisições. Tente novamente mais tarde."},
                headers={"Retry-After": str(janela)}
            )
            
        return await call_next(request)
