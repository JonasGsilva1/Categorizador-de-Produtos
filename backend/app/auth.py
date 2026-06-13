"""
Autenticação Supabase JWT.
Suporta RS256 (JWKS) e HS256 (shared secret).
"""

import logging
import jwt
try:
    from jwt import PyJWKClient
    _HAS_JWKS = True
except ImportError:
    _HAS_JWKS = False
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import get_settings

logger = logging.getLogger(__name__)

security = HTTPBearer()

# Cache do cliente JWKS (RS256)
_jwks_client = None


def _get_jwks_client(supabase_url: str):
    global _jwks_client
    if not _HAS_JWKS:
        raise RuntimeError("PyJWKClient nao disponivel. Instale 'cryptography'.")
    if _jwks_client is None:
        jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url)
    return _jwks_client


def verify_supabase_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """
    Verifica o token JWT do Supabase.
    Tenta RS256 (JWKS) primeiro, depois HS256 (shared secret).
    Retorna o user_id (sub).
    """
    token = credentials.credentials
    settings = get_settings()

    if not token or len(token) < 20:
        logger.warning("[AUTH] Token vazio ou muito curto recebido.")
        raise HTTPException(status_code=401, detail="Token invalido.")

    errors = []

    # --- Tentativa 1: RS256/ES256 via JWKS ---
    if _HAS_JWKS and settings.supabase_url:
        try:
            jwks_client = _get_jwks_client(settings.supabase_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            # Tenta RS256 e ES256 (Supabase pode usar qualquer um)
            for algo in ["RS256", "ES256"]:
                try:
                    payload = jwt.decode(
                        token,
                        signing_key.key,
                        algorithms=[algo],
                        options={"verify_aud": False},
                    )
                    user_id = payload.get("sub")
                    if user_id:
                        logger.debug(f"[AUTH] Token validado via {algo} (JWKS).")
                        return user_id
                except jwt.InvalidTokenError:
                    continue
            errors.append("JWKS: token rejeitado por RS256 e ES256")
        except Exception as e:
            errors.append(f"JWKS: {e}")
    else:
        if not _HAS_JWKS:
            logger.debug("[AUTH] PyJWKClient nao disponivel, pulando JWKS.")
        if not settings.supabase_url:
            logger.debug("[AUTH] SUPABASE_URL nao configurado, pulando JWKS.")

    # --- Tentativa 2: HS256 via shared secret ---
    if settings.supabase_jwt_secret:
        try:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
            user_id = payload.get("sub")
            if user_id:
                logger.debug("[AUTH] Token validado via HS256 (secret).")
                return user_id
        except Exception as e:
            errors.append(f"HS256: {e}")
    else:
        logger.warning("[AUTH] SUPABASE_JWT_SECRET nao configurado — tentando apenas RS256.")

    # --- Falhou em ambos ---
    logger.warning("[AUTH] Token invalido. Erros: %s", "; ".join(errors))
    # Verificar se é token expirado para dar mensagem mais útil
    for err in errors:
        if "ExpiredSignature" in err or "expired" in err.lower():
            raise HTTPException(status_code=401, detail="Token expirado. Faca login novamente.")
    raise HTTPException(status_code=401, detail="Token invalido.")
