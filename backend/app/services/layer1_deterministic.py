"""
Camada 1 do Funil: Validação Determinística.

Consulta a tabela de histórico por EAN exato no Supabase.
- Match exato por EAN → retorna grupo/subgrupo imediatamente
- Ignora NCM
"""

import logging
import asyncpg
from app.models import ProductInput, ProductOutput

logger = logging.getLogger(__name__)


async def lookup_by_ean(ean: str, pool: asyncpg.Pool) -> dict | None:
    """
    Busca categorização por EAN exato na tabela product_history.
    """
    if not ean or ean.strip() == "":
        return None

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT grupo, subgrupo 
            FROM product_history 
            WHERE ean = $1 AND ean != ''
            LIMIT 1
            """,
            ean.strip(),
        )

    if row:
        logger.debug(f"EAN match encontrado no histórico: {ean} → {row['grupo']}/{row['subgrupo']}")
        return {"grupo": row["grupo"], "subgrupo": row["subgrupo"]}

    return None


async def layer1_lookup(product: ProductInput, pool: asyncpg.Pool) -> ProductOutput | None:
    """
    Executa a Camada 1 do funil: busca determinística por EAN.
    """
    result = await lookup_by_ean(product.ean, pool)
    if result:
        return ProductOutput(
            row_index=product.row_index,
            descricao=product.descricao,
            ean=product.ean,
            ncm=product.ncm,
            grupo=result["grupo"],
            subgrupo=result["subgrupo"],
            origem="EAN",
            status="Aprovado",
        )

    return None
