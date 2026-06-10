"""
Autenticação Supabase JWT.
Verifica o token enviado pelo frontend para proteger as rotas.
"""

import jwt
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import get_settings

security = HTTPBearer()

def verify_supabase_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """
    Verifica o token JWT do Supabase e retorna o user_id (sub).
    """
    token = credentials.credentials
    settings = get_settings()

    try:
        # Decodificar JWT do Supabase usando a chave secreta
        # (Em produção, o correto é validar o JWT usando a Supabase JWT Secret)
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
        raise HTTPException(status_code=401, detail="Token expirado.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")
