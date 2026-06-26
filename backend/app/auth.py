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
    Valida o token JWT do Supabase.
    Otimizado para usar PyJWT localmente (zero latência de rede) se a chave JWT
    estiver configurada. Faz fallback para a API do Supabase em caso de erro.
    """
    token = credenciais.credentials
    
    if not token or len(token) < 20:
        logger.warning("[AUTH] Token vazio ou muito curto recebido.")
        raise HTTPException(status_code=401, detail="Token inválido.")
    
    import os
    import jwt
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")
    
    # Tentativa 1: Validação Local Otimizada (sub-milissegundo, sem rede)
    if jwt_secret:
        try:
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
            user_id = payload.get("sub")
            email = payload.get("email", "")
            if user_id:
                return {"user_id": user_id, "email": email}
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expirado.")
        except Exception as excecao_jwt:
            logger.debug(f"[AUTH] Fallback para Supabase API após erro no PyJWT: {excecao_jwt}")
            # Se a validação local falhar (ex: chave errada), tenta o fallback.

    # Tentativa 2: Fallback (Requisição HTTP via SDK)
    cliente = obter_cliente_supabase()
    if cliente is None:
        raise HTTPException(
            status_code=500,
            detail="Erro de configuração: variáveis de autenticação não configuradas."
        )
    
    try:
        resultado = cliente.auth.get_user(token)
        if resultado and resultado.user:
            return {"user_id": resultado.user.id, "email": resultado.user.email}
        raise HTTPException(status_code=401, detail="Token inválido.")
    except Exception as excecao:
        logger.warning(f"[AUTH] Token inválido na API: {excecao}")
        raise HTTPException(status_code=401, detail="Token inválido.")
