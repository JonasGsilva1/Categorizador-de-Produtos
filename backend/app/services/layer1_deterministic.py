"""
Camada 1 do Funil: Validação Determinística.

1A. Consulta tabela product_history por EAN exato.
1B. Consulta tabela ncm_rules via função match_ncm_rule() para fallback por NCM.

Ambas as rotas retornam resultado imediato sem chamadas a APIs externas.
"""

import logging
import asyncpg
from app.models import ProductInput, ProductOutput

logger = logging.getLogger(__name__)


async def lookup_by_ean(ean: str, pool: asyncpg.Pool) -> dict | None:
    """
    Busca categorização por EAN exato na tabela product_history.

    Returns:
        Dict com 'grupo' e 'subgrupo', ou None se não encontrado.
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
        logger.debug(
            f"EAN match encontrado no histórico: {ean} → {row['grupo']}/{row['subgrupo']}"
        )
        return {"grupo": row["grupo"], "subgrupo": row["subgrupo"]}

    return None


async def lookup_by_ncm(ncm: str, pool: asyncpg.Pool) -> dict | None:
    """
    Busca categorização por NCM usando a função match_ncm_rule() do banco.

    A função aceita NCMs parciais (prefixos) e retorna o match mais específico.
    NCMs inválidos (vazio, '0', '00000000') são ignorados.

    Returns:
        Dict com 'grupo' e 'subgrupo', ou None se não encontrado.
    """
    if not ncm:
        return None

    ncm_clean = ncm.strip()
    if ncm_clean in ("", "0", "00", "00000000"):
        return None

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT grupo, subgrupo FROM match_ncm_rule($1)",
                ncm_clean,
            )

        if row:
            logger.debug(
                f"NCM match encontrado: {ncm_clean} → {row['grupo']}/{row['subgrupo']}"
            )
            return {"grupo": row["grupo"], "subgrupo": row["subgrupo"]}

    except Exception as e:
        # Não interrompe o fluxo — NCM é apenas um fallback
        logger.warning(f"Erro ao consultar match_ncm_rule({ncm_clean!r}): {e}")

    return None


async def layer1_lookup(product: ProductInput, pool: asyncpg.Pool) -> ProductOutput | None:
    """
    Executa a Camada 1 do funil: busca determinística por EAN e, em seguida, por NCM.

    1A — EAN exato no product_history.
    1B — NCM via match_ncm_rule() nas ncm_rules.

    Returns:
        ProductOutput com status 'Aprovado' e origem 'EAN' ou 'NCM', ou None.
    """
    # 1A: EAN
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

    # 1B: NCM
    result = await lookup_by_ncm(product.ncm, pool)
    if result:
        return ProductOutput(
            row_index=product.row_index,
            descricao=product.descricao,
            ean=product.ean,
            ncm=product.ncm,
            grupo=result["grupo"],
            subgrupo=result["subgrupo"],
            origem="NCM",
            status="Aprovado",
        )

    return None
