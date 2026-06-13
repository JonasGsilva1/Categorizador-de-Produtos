"""
Gerenciador de conexão assíncrona com PostgreSQL via asyncpg.
Cria e gerencia o pool de conexões durante o ciclo de vida da aplicação.
"""

import logging
import ssl

import asyncpg
from fastapi import HTTPException

from app.config import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


def _normalize_dsn(url: str) -> str:
    """Normaliza URL para asyncpg (postgres:// → postgresql://)."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _needs_ssl(dsn: str) -> bool:
    return (
        "supabase.co" in dsn
        or "sslmode=require" in dsn.lower()
        or "ssl=true" in dsn.lower()
    )


async def create_pool() -> asyncpg.Pool:
    """Cria o pool de conexões com o PostgreSQL/Supabase."""
    global _pool
    settings = get_settings()
    dsn = _normalize_dsn(settings.database_url)

    connect_kwargs: dict = {
        "dsn": dsn,
        "min_size": 1,
        "max_size": 10,
        "command_timeout": 60,
        "statement_cache_size": 0,  # Necessário para Supabase Pooler (PgBouncer)
    }

    if _needs_ssl(dsn):
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connect_kwargs["ssl"] = ssl_ctx

    logger.info("Conectando ao PostgreSQL...")
    _pool = await asyncpg.create_pool(**connect_kwargs)

    try:
        async with _pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception as exc:
        logger.warning(
            "Extensão vector não pôde ser criada (habilite no painel Supabase): %s",
            exc,
        )

    logger.info("Pool PostgreSQL pronto.")
    return _pool


async def close_pool() -> None:
    """Fecha o pool de conexões."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def is_pool_ready() -> bool:
    return _pool is not None


def get_pool() -> asyncpg.Pool:
    """Retorna o pool de conexões ativo."""
    if _pool is None:
        raise RuntimeError("Pool de conexões não inicializado. Chame create_pool() primeiro.")
    return _pool


def require_pool() -> asyncpg.Pool:
    """Retorna o pool ou HTTP 503 com mensagem clara."""
    try:
        return get_pool()
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Erro de DB: {str(e)}",
        )
