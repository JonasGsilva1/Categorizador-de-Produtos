"""
Autenticação Supabase JWT.
Usa o cliente oficial do Supabase (supabase-py) para validar tokens.
Suporta HS256, RS256 e ES256 automaticamente.
"""

import logging
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

seguranca = HTTPBearer()

# Cliente Supabase (inicialização preguiçosa para não quebrar se variáveis não existirem)
_cliente_supabase = None

def obter_cliente_supabase():
    """Retorna cliente Supabase inicializado com URL e anon key."""
    global _cliente_supabase
    if _cliente_supabase is not None:
        return _cliente_supabase
    
    from supabase import create_client
    import os
    
    url = os.getenv("SUPABASE_URL", "")
    chave = os.getenv("SUPABASE_ANON_KEY", "")
    
    if not url or not chave:
        logger.warning("[AUTH] SUPABASE_URL ou SUPABASE_ANON_KEY não configurados.")
        return None
    
    try:
        _cliente_supabase = create_client(url, chave)
        logger.info("[AUTH] Cliente Supabase inicializado.")
        return _cliente_supabase
    except Exception as excecao:
        logger.error(f"[AUTH] Falha ao inicializar cliente Supabase: {excecao}")
        return None


def verify_supabase_token(
    credenciais: HTTPAuthorizationCredentials = Security(seguranca)
) -> dict:
    """
    Valida o token JWT do Supabase usando o cliente oficial.
    Retorna os dados do usuário (user.id, user.email, etc).
    """
    token = credenciais.credentials
    
    if not token or len(token) < 20:
        logger.warning("[AUTH] Token vazio ou muito curto recebido.")
        raise HTTPException(status_code=401, detail="Token inválido.")
    
    cliente = obter_cliente_supabase()
    if cliente is None:
        raise HTTPException(
            status_code=500,
            detail="Erro de configuração: variáveis SUPABASE_URL/ANON_KEY não configuradas."
        )
    
    try:
        # O método get_user faz a validação automática do token
        resultado = cliente.auth.get_user(token)
        
        if resultado and resultado.user:
            logger.debug(f"[AUTH] Token validado para user_id: {resultado.user.id}")
            return {"user_id": resultado.user.id, "email": resultado.user.email}
        
        raise HTTPException(status_code=401, detail="Token inválido.")
        
    except Exception as excecao:
        logger.warning(f"[AUTH] Token inválido: {excecao}")
        raise HTTPException(status_code=401, detail="Token inválido.")
