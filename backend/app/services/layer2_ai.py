"""
Camada 2 do Funil: Inteligência Artificial.

1. Converte descrição em embedding
2. Busca por similaridade de cosseno no pgvector (threshold rigoroso > 0.98) APENAS por Descrição
3. Se não encontrou match vetorial, classifica via LLM
"""

import logging
import asyncpg
from app.models import ProductInput, VectorMatch, LLMClassification
from app.services.embedding import generate_embedding
from app.services.llm import classify_products_batch

logger = logging.getLogger(__name__)


async def vector_search(
    embedding: list[float],
    pool: asyncpg.Pool,
    threshold: float = 0.98,
) -> VectorMatch | None:
    """
    Executa busca por similaridade de cosseno no pgvector ignorando NCM.
    
    Returns:
        VectorMatch se similaridade >= 0.98, None caso contrário.
    """
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 
                id,
                descricao,
                grupo,
                subgrupo,
                (1 - (embedding <=> $1::vector)) AS similarity
            FROM product_history
            WHERE (1 - (embedding <=> $1::vector)) >= $2
            ORDER BY embedding <=> $1::vector ASC
            LIMIT 1
            """,
            embedding_str,
            threshold,
        )

    if row:
        match = VectorMatch(
            id=row["id"],
            descricao=row["descricao"],
            grupo=row["grupo"],
            subgrupo=row["subgrupo"],
            similarity=float(row["similarity"]),
        )
        logger.debug(
            f"Vector match encontrado: sim={match.similarity:.4f} → "
            f"{match.grupo}/{match.subgrupo} (ref: '{match.descricao[:50]}...')"
        )
        return match

    return None


async def save_to_history(
    product: ProductInput,
    grupo: str,
    subgrupo: str,
    embedding: list[float],
    origem: str,
    pool: asyncpg.Pool,
) -> None:
    """
    Salva o produto categorizado no histórico com embedding para aprendizado futuro.
    Faz upsert baseado na descrição normalizada.
    """
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO product_history (descricao, ean, ncm, grupo, subgrupo, embedding, origem)
            VALUES ($1, $2, $3, $4, $5, $6::vector, $7)
            ON CONFLICT ((LOWER(descricao)))
            DO UPDATE SET 
                grupo = EXCLUDED.grupo,
                subgrupo = EXCLUDED.subgrupo,
                embedding = EXCLUDED.embedding,
                origem = EXCLUDED.origem,
                updated_at = NOW()
            """,
            product.descricao,
            product.ean,
            product.ncm,
            grupo,
            subgrupo,
            embedding_str,
            origem,
        )


async def layer2_ai(
    product: ProductInput,
    pool: asyncpg.Pool,
) -> tuple[list[float], VectorMatch | None, LLMClassification | None]:
    """
    Executa a Camada 2 do funil:
    1. Gera embedding da descrição
    2. Busca vetorial no histórico
    3. Se não encontrou, classifica via LLM
    """
    embedding = await generate_embedding(product.descricao)

    match = await vector_search(embedding, pool, threshold=0.98)
    if match:
        return embedding, match, None

    # NOTA: layer2_ai não é mais chamado pelo funnel.py.
    # O processamento em lote é feito via classify_products_batch em funnel.py.
    # Mantido aqui apenas para referência histórica.
    raise NotImplementedError("layer2_ai foi substituído pelo processamento em lote do funnel.py")
