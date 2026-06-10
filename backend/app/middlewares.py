"""
Middlewares de Segurança (Cybersecurity).
Injeta Security Headers contra as vulnerabilidades web mais comuns.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # HSTS: Força o uso de HTTPS pelo navegador (1 ano)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
        # Previne MIME Sniffing (impede que o navegador tente adivinhar o tipo do arquivo e execute malwares)
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Previne Clickjacking (impede a aplicação de ser embutida em iframes de outros sites)
        response.headers["X-Frame-Options"] = "DENY"
        
        # Previne Cross-Site Scripting (XSS)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Oculta a tecnologia do servidor para dificultar fingerprinting (embora o Uvicorn adicione server, podemos sobrepor)
        response.headers["Server"] = "Hidden"

        return response
