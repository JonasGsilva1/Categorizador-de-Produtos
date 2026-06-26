"""
Camada 2 do Funil: Inteligência Artificial.

1. Converte descrição em embedding
2. Busca por similaridade de cosseno no pgvector (threshold rigoroso > 0.98) APENAS por Descrição
3. Se não encontrou match vetorial, classifica via LLM
"""

import logging
import asyncpg
from app.models import ProdutoEntrada, ResultadoBuscaVetorial, ClassificacaoLLM
from app.services.embedding import generate_embedding
from app.services.llm import classify_products_batch

logger = logging.getLogger(__name__)


async def busca_vetorial(
    embedding: list[float],
    pool_db: asyncpg.Pool,
    limite: float = 0.98,
) -> ResultadoBuscaVetorial | None:
    """
    Executa busca por similaridade de cosseno no pgvector ignorando NCM.
    
    Returns:
        ResultadoBuscaVetorial se similaridade >= limite, None caso contrário.
    """
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    async with pool_db.acquire() as conexao:
        linha = await conexao.fetchrow(
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
            limite,
        )

    if linha:
        correspondencia = ResultadoBuscaVetorial(
            id=linha["id"],
            descricao=linha["descricao"],
            grupo=linha["grupo"],
            subgrupo=linha["subgrupo"],
            similarity=float(linha["similarity"]),
        )
        logger.debug(
            f"Correspondência de vetor encontrada: sim={correspondencia.similarity:.4f} → "
            f"{correspondencia.grupo}/{correspondencia.subgrupo} (ref: '{correspondencia.descricao[:50]}...')"
        )
        return correspondencia

    return None


async def salvar_no_historico(
    produto: ProdutoEntrada,
    grupo: str,
    subgrupo: str,
    embedding: list[float],
    origem: str,
    pool_db: asyncpg.Pool,
) -> None:
    """
    Salva o produto categorizado no histórico com embedding para aprendizado futuro.
    Faz upsert baseado na descrição normalizada.
    """
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    async with pool_db.acquire() as conexao:
        await conexao.execute(
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
            produto.descricao,
            produto.ean,
            produto.ncm,
            grupo,
            subgrupo,
            embedding_str,
            origem,
        )


async def layer2_ai(
    produto: ProdutoEntrada,
    pool_db: asyncpg.Pool,
) -> tuple[list[float], ResultadoBuscaVetorial | None, ClassificacaoLLM | None]:
    """
    Executa a Camada 2 do funil:
    1. Gera embedding da descrição
    2. Busca vetorial no histórico
    3. Se não encontrou, classifica via LLM
    """
    embedding = await generate_embedding(produto.descricao)

    correspondencia = await busca_vetorial(embedding, pool_db, limite=0.98)
    if correspondencia:
        return embedding, correspondencia, None

    # NOTA: layer2_ai não é mais chamado pelo funnel.py.
    # O processamento em lote é feito via classify_products_batch em funnel.py.
    # Mantido aqui apenas para referência histórica.
    raise NotImplementedError("layer2_ai foi substituído pelo processamento em lote do funnel.py")
