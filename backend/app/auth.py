"""
Autenticação Supabase JWT.
Verifica o token enviado pelo frontend para proteger as rotas.
"""

import logging
import jwt
from fastapi import HTTPException, Security
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

    if not settings.supabase_jwt_secret:
        logger.error("[AUTH] SUPABASE_JWT_SECRET não configurado!")
        raise HTTPException(status_code=500, detail="Erro de configuração do servidor.")

    if not token or len(token) < 20:
        logger.warning("[AUTH] Token vazio ou muito curto recebido.")
        raise HTTPException(status_code=401, detail="Token inválido.")

    try:
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
        raise HTTPException(status_code=401, detail="Token expirado. Faça login novamente.")
    except jwt.InvalidTokenError as e:
        logger.warning("[AUTH] Token invalido: %s", str(e))
        raise HTTPException(status_code=401, detail="Token invalido.")
