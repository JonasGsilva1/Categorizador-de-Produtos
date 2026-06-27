"""
Configurações centralizadas da aplicação.
Carrega variáveis de ambiente via Pydantic BaseSettings.
"""

import logging
from functools import lru_cache

from pydantic import ValidationError
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Configurações da aplicação carregadas de variáveis de ambiente."""

    # --- Banco de Dados ---
    database_url: str

    # --- Provedores de IA (Gemini) ---
    gemini_api_key: str = ""
    
    # --- Provedores de IA (OpenRouter) ---
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3-8b-instruct:free"

    # --- Autenticação ---
    supabase_jwt_secret: str = ""
    supabase_url: str = ""

    # --- Funil ---
    similarity_threshold: float = 0.98
    llm_confidence_threshold: int = 95
    embedding_batch_size: int = 10
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 1536
    llm_model: str = "gemini-2.5-flash"

    # --- CORS ---
    frontend_url: str = "http://localhost:3000"

    # --- Servidor ---
    port: int = 8000

    # --- Armazenamento ---
    temp_storage_path: str = "/tmp"

    # --- Segurança ---
    environment: str = "development"  # "production" em Railway
    rate_limit_per_minute: int = 60   # Requests gerais por IP
    upload_rate_limit_per_minute: int = 5  # Uploads por IP
    allowed_hosts: str = "*"  # Configurar em prod para *.up.railway.app (separado por vírgulas)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache
def get_settings() -> Settings:
    """Retorna instância em cache das configurações."""
    try:
        return Settings()
    except ValidationError as excecao:
        ausentes = [
            ".".join(str(part) for part in erro.get("loc", ()))
            for erro in excecao.errors()
            if erro.get("type") == "missing"
        ]
        if ausentes:
            logger.error(
                "Variáveis de ambiente obrigatórias ausentes no Railway: %s",
                ", ".join(ausentes),
            )
        raise
