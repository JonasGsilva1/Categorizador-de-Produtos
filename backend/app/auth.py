"""
Autenticação Supabase JWT.
Verifica o token enviado pelo frontend para proteger as rotas.
"""

import logging
import jwt
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import get_settings

logger = logging.getLogger(__name__)

security = HTTPBearer()

def verify_supabase_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """
    Verifica o token JWT do Supabase e retorna o user_id (sub).
    """
    token = credentials.credentials
    settings = get_settings()

    # --- DEBUG: remover após identificar o problema ---
    jwt_secret_preview = (settings.supabase_jwt_secret or "")[:8]
    logger.info(
        "[AUTH DEBUG] JWT secret configured: %s..., token prefix: %s..., token length: %d",
        jwt_secret_preview or "(VAZIO)",
        token[:20] if token else "(VAZIO)",
        len(token) if token else 0,
    )
    # --- FIM DEBUG ---

    if not settings.supabase_jwt_secret:
        logger.error("[AUTH] SUPABASE_JWT_SECRET está vazio ou não configurado no Railway!")
        raise HTTPException(status_code=500, detail="Erro de configuração: JWT secret não configurado no servidor.")

    try:
        # Decodificar JWT do Supabase usando a chave secreta
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token inválido: user_id ausente.")
            
        return user_id

    except jwt.ExpiredSignatureError:
        logger.warning("[AUTH] Token expirado.")
        raise HTTPException(status_code=401, detail="Token expirado.")
    except jwt.InvalidTokenError as e:
        logger.warning("[AUTH] Token inválido: %s", str(e))
        raise HTTPException(status_code=401, detail="Token inválido.")
