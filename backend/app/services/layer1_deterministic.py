"""
Camada 1 do Funil: Validação Determinística.

Consulta tabelas relacionais de regras por EAN e NCM no Supabase.
- Match exato por EAN → retorna grupo/subgrupo imediatamente
- Match por prefixo de NCM (mais longo primeiro) → retorna grupo/subgrupo
"""

import logging
import asyncpg
from app.models import ProductInput, ProductOutput

logger = logging.getLogger(__name__)


async def lookup_by_ean(ean: str, pool: asyncpg.Pool) -> dict | None:
    """
    Busca categorização por EAN exato na tabela ean_rules.
    
    Returns:
        Dict com 'grupo' e 'subgrupo' se encontrado, None caso contrário.
    """
    if not ean or ean.strip() == "":
        return None

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT grupo, subgrupo FROM ean_rules WHERE ean = $1",
            ean.strip(),
        )

    if row:
        logger.debug(f"EAN match encontrado: {ean} → {row['grupo']}/{row['subgrupo']}")
        return {"grupo": row["grupo"], "subgrupo": row["subgrupo"]}

    return None


async def lookup_by_ncm(ncm: str, pool: asyncpg.Pool) -> dict | None:
    """
    Busca categorização por prefixo de NCM na tabela ncm_rules.
    Tenta match com o prefixo mais longo primeiro (8 → 6 → 4 → 2 dígitos).
    
    Returns:
        Dict com 'grupo' e 'subgrupo' se encontrado, None caso contrário.
    """
    if not ncm or ncm.strip() == "":
        return None

    clean_ncm = ncm.strip().replace(".", "").replace("-", "").replace("/", "")

    if not clean_ncm:
        return None

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT grupo, subgrupo 
            FROM ncm_rules 
            WHERE $1 LIKE ncm_prefix || '%'
            ORDER BY LENGTH(ncm_prefix) DESC 
            LIMIT 1
            """,
            clean_ncm,
        )

    if row:
        logger.debug(f"NCM match encontrado: {ncm} → {row['grupo']}/{row['subgrupo']}")
        return {"grupo": row["grupo"], "subgrupo": row["subgrupo"]}

    return None


async def layer1_lookup(product: ProductInput, pool: asyncpg.Pool) -> ProductOutput | None:
    """
    Executa a Camada 1 do funil: busca determinística por EAN e depois NCM.
    
    Returns:
        ProductOutput se encontrou match, None caso contrário.
    """
    # 1. Tentar EAN primeiro (mais específico)
    result = await lookup_by_ean(product.ean, pool)
    if result:
        return ProductOutput(
            row_index=product.row_index,
            descricao=product.descricao,
            ean=product.ean,
            ncm=product.ncm,
            grupo=result["grupo"],
            subgrupo=result["subgrupo"],
            origem="EAN/NCM",
            status="Aprovado",
        )

    # 2. Tentar NCM por prefixo
    result = await lookup_by_ncm(product.ncm, pool)
    if result:
        return ProductOutput(
            row_index=product.row_index,
            descricao=product.descricao,
            ean=product.ean,
            ncm=product.ncm,
            grupo=result["grupo"],
            subgrupo=result["subgrupo"],
            origem="EAN/NCM",
            status="Aprovado",
        )

    return None
