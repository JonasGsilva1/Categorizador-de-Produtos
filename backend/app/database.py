"""
Gerenciador de conexão assíncrona com PostgreSQL via asyncpg.
Cria e gerencia o pool de conexões durante o ciclo de vida da aplicação.
"""

import asyncpg
from app.config import get_settings

# Pool global de conexões
_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    """Cria o pool de conexões com o PostgreSQL/Supabase."""
    global _pool
    settings = get_settings()

    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
        command_timeout=60,
        statement_cache_size=0,  # Necessário para Supabase Pooler (PgBouncer)
    )

    # Registrar tipo vector do pgvector
    async with _pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    return _pool


async def close_pool() -> None:
    """Fecha o pool de conexões."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Retorna o pool de conexões ativo."""
    if _pool is None:
        raise RuntimeError("Pool de conexões não inicializado. Chame create_pool() primeiro.")
    return _pool
