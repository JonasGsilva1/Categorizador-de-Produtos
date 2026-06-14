"""
Middlewares de Segurança e Proteção.
Implementa OWASP Headers, Rate Limiting in-memory e rastreabilidade (LGPD).
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
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # HSTS: Força HTTPS
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        # Previne MIME Sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Previne Clickjacking (Permitir do mesmo origin, ou bloqueio total se API)
        response.headers["X-Frame-Options"] = "DENY"
        # Previne XSS
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Esconde o servidor
        response.headers["Server"] = "Hidden"
        
        # --- Novos Headers de Segurança (OWASP Moderno) ---
        # CSP: API não deve executar scripts nem carregar iframes
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        # Previne acesso a recursos do dispositivo pelo browser
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Não vaza a URL da API em requests subsequentes
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Nao cachear respostas da API (proteção de dados Pessoais/LGPD)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
        response.headers["Pragma"] = "no-cache"

        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Injeta um ID único por requisição para rastreabilidade (Audit/LGPD)."""
    async def dispatch(self, request: Request, call_next):
        req_id = str(uuid.uuid4())
        request.state.req_id = req_id
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


# --- Rate Limiter In-Memory ---
# Usamos um dicionário simples. Para multi-instância no futuro, migrar para Redis.
_RATE_LIMITS = {}

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Protege contra DDoS e Brute Force limitando requests por IP."""
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        
        # Limpar registros antigos a cada request (simplificado para in-memory)
        # O ideal seria um background task, mas para evitar complexidade mantemos aqui
        now = time.time()
        
        # Obter IP real (lidando com proxy do Railway)
        client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1")
        client_ip = client_ip.split(",")[0].strip()
        
        # Definir limites baseados na rota
        path = request.url.path
        is_upload = path == "/api/categorize" and request.method == "POST"
        limit = settings.upload_rate_limit_per_minute if is_upload else settings.rate_limit_per_minute
        window = 60  # 1 minuto
        
        key = f"{client_ip}:{path}"
        
        # Inicializa se não existir
        if key not in _RATE_LIMITS:
            _RATE_LIMITS[key] = {"count": 0, "start_time": now}
            
        record = _RATE_LIMITS[key]
        
        # Resetar a janela de tempo se passou 1 minuto
        if now - record["start_time"] > window:
            record["count"] = 0
            record["start_time"] = now
            
        record["count"] += 1
        
        if record["count"] > limit:
            logger.warning(f"Rate limit excedido para IP {client_ip} em {path}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests. Tente novamente mais tarde."},
                headers={"Retry-After": str(window)}
            )
            
        return await call_next(request)
