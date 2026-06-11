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

    # --- Database ---
    database_url: str

    # --- AI Providers (Gemini) ---
    gemini_api_key: str

    # --- Auth ---
    supabase_jwt_secret: str

    # --- Funil ---
    similarity_threshold: float = 0.98
    llm_confidence_threshold: int = 95
    embedding_batch_size: int = 50
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 1536
    llm_model: str = "gemini-2.5-flash"

    # --- CORS ---
    frontend_url: str = "http://localhost:3000"

    # --- Server ---
    port: int = 8000

    # --- Storage ---
    temp_storage_path: str = "/tmp"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache
def get_settings() -> Settings:
    """Retorna instância cacheada das configurações."""
    try:
        return Settings()
    except ValidationError as exc:
        missing = [
            ".".join(str(part) for part in err.get("loc", ()))
            for err in exc.errors()
            if err.get("type") == "missing"
        ]
        if missing:
            logger.error(
                "Variáveis de ambiente obrigatórias ausentes no Railway: %s",
                ", ".join(missing),
            )
        raise
