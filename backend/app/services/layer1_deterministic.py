"""
Camada 1 do Funil: Validação Determinística.

1A. Consulta tabela product_history por EAN exato.
1B. Consulta tabela ncm_rules via função match_ncm_rule() para fallback por NCM.

Ambas as rotas retornam resultado imediato sem chamadas a APIs externas.
"""

import logging
import asyncpg
from app.models import ProdutoEntrada, ProdutoSaida

logger = logging.getLogger(__name__)


async def buscar_por_ean(ean: str, pool_db: asyncpg.Pool) -> dict | None:
    """
    Busca categorização por EAN exato na tabela product_history.

    Returns:
        Dict com 'grupo' e 'subgrupo', ou None se não encontrado.
    """
    if not ean or ean.strip() == "":
        return None

    async with pool_db.acquire() as conexao:
        linha = await conexao.fetchrow(
            """
            SELECT grupo, subgrupo
            FROM product_history
            WHERE ean = $1 AND ean != ''
            LIMIT 1
            """,
            ean.strip(),
        )

    if linha:
        logger.debug(
            f"EAN correspondente encontrado no histórico: {ean} → {linha['grupo']}/{linha['subgrupo']}"
        )
        return {"grupo": linha["grupo"], "subgrupo": linha["subgrupo"]}

    return None


async def buscar_por_ncm(ncm: str, pool_db: asyncpg.Pool) -> dict | None:
    """
    Busca categorização por NCM usando a função match_ncm_rule() do banco.

    A função aceita NCMs parciais (prefixos) e retorna a correspondência mais específica.
    NCMs inválidos (vazio, '0', '00000000') são ignorados.

    Returns:
        Dict com 'grupo' e 'subgrupo', ou None se não encontrado.
    """
    if not ncm:
        return None

    ncm_limpo = ncm.strip()
    if ncm_limpo in ("", "0", "00", "00000000"):
        return None

    try:
        async with pool_db.acquire() as conexao:
            linha = await conexao.fetchrow(
                "SELECT grupo, subgrupo FROM match_ncm_rule($1)",
                ncm_limpo,
            )

        if linha:
            logger.debug(
                f"NCM correspondente encontrado: {ncm_limpo} → {linha['grupo']}/{linha['subgrupo']}"
            )
            return {"grupo": linha["grupo"], "subgrupo": linha["subgrupo"]}

    except Exception as excecao:
        # Não interrompe o fluxo — NCM é apenas um fallback
        logger.warning(f"Erro ao consultar match_ncm_rule({ncm_limpo!r}): {excecao}")

    return None


async def layer1_lookup(produto: ProdutoEntrada, pool_db: asyncpg.Pool) -> ProdutoSaida | None:
    """
    Executa a Camada 1 do funil: busca determinística por EAN e, em seguida, por NCM.

    1A — EAN exato no product_history.
    1B — NCM via match_ncm_rule() nas ncm_rules.

    Returns:
        ProdutoSaida com status 'Aprovado' e origem 'EAN' ou 'NCM', ou None.
    """
    # 1A: EAN
    resultado = await buscar_por_ean(produto.ean, pool_db)
    if resultado:
        return ProdutoSaida(
            row_index=produto.row_index,
            descricao=produto.descricao,
            ean=produto.ean,
            ncm=produto.ncm,
            grupo=resultado["grupo"],
            subgrupo=resultado["subgrupo"],
            origem="EAN",
            status="Aprovado",
        )

    # 1B: NCM
    resultado = await buscar_por_ncm(produto.ncm, pool_db)
    if resultado:
        return ProdutoSaida(
            row_index=produto.row_index,
            descricao=produto.descricao,
            ean=produto.ean,
            ncm=produto.ncm,
            grupo=resultado["grupo"],
            subgrupo=resultado["subgrupo"],
            origem="NCM",
            status="Aprovado",
        )

    return None
