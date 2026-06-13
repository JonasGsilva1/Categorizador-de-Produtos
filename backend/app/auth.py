"""
Autenticação Supabase JWT.
Usa o cliente oficial do Supabase (supabase-py) para validar tokens.
Suporta HS256, RS256 e ES256 automaticamente.
"""

import logging
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

security = HTTPBearer()

# Cliente Supabase (lazy init para não crashar se variáveis não existirem)
_supabase_client = None

def get_supabase_client():
    """Retorna cliente Supabase inicializado com URL e anon key."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    
    from supabase import create_client
    import os
    
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_ANON_KEY", "")
    
    if not url or not key:
        logger.warning("[AUTH] SUPABASE_URL ou SUPABASE_ANON_KEY não configurados.")
        return None
    
    try:
        _supabase_client = create_client(url, key)
        logger.info("[AUTH] Cliente Supabase inicializado.")
        return _supabase_client
    except Exception as e:
        logger.error(f"[AUTH] Falha ao inicializar cliente Supabase: {e}")
        return None


def verify_supabase_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """
    Valida o token JWT do Supabase usando o cliente oficial.
    Retorna os dados do usuário (user.id, user.email, etc).
    """
    token = credentials.credentials
    
    if not token or len(token) < 20:
        logger.warning("[AUTH] Token vazio ou muito curto recebido.")
        raise HTTPException(status_code=401, detail="Token inválido.")
    
    client = get_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=500,
            detail="Erro de configuração: variáveis SUPABASE_URL/ANON_KEY não configuradas."
        )
    
    try:
        # O método get_user faz a validação automática do token
        result = client.auth.get_user(token)
        
        if result and result.user:
            logger.debug(f"[AUTH] Token validado para user_id: {result.user.id}")
            return {"user_id": result.user.id, "email": result.user.email}
        
        raise HTTPException(status_code=401, detail="Token inválido.")
        
    except Exception as e:
        logger.warning(f"[AUTH] Token invalido: {e}")
        raise HTTPException(status_code=401, detail="Token inválido.")
