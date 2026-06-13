"""
Orquestrador do Funil de 3 Camadas.

Processa uma lista de produtos sequencialmente através das 3 camadas:
1. Camada 1: Validação Determinística (apenas EAN Local)
2. Camada 2: Inteligência Artificial (pgvector + LLM)
3. Camada 3: Filtro de Segurança (Confiança do LLM >= 95)
"""

import logging
import asyncio
import asyncpg
from app.models import ProductInput, ProductOutput
from app.services.layer1_deterministic import layer1_lookup
from app.services.layer2_ai import layer2_ai, save_to_history
from app.services.layer3_filter import layer3_filter

logger = logging.getLogger(__name__)


class FunnelMetrics:
    """Contadores de métricas do processamento do funil."""

    def __init__(self):
        self.total: int = 0
        self.layer1_ean: int = 0
        self.layer2_vector: int = 0
        self.layer2_llm_approved: int = 0
        self.layer2_llm_pending: int = 0
        self.errors: int = 0

    def summary(self) -> dict:
        return {
            "total_processado": self.total,
            "camada1_ean": self.layer1_ean,
            "camada2_busca_vetorial": self.layer2_vector,
            "camada2_llm_aprovado": self.layer2_llm_approved,
            "camada2_llm_pendente_revisao": self.layer2_llm_pending,
            "erros": self.errors,
        }


async def process_single_product(
    product: ProductInput,
    pool: asyncpg.Pool,
    metrics: FunnelMetrics,
) -> ProductOutput:
    """
    Processa um único produto pelo funil completo de 3 camadas.
    """
    try:
        # =====================================================
        # CAMADA 1: Validação Determinística
        # =====================================================
        result = await layer1_lookup(product, pool)
        if result is not None:
            metrics.layer1_ean += 1
            logger.info(
                f"[Linha {product.row_index}] Camada 1 ✓ EAN → "
                f"{result.grupo}/{result.subgrupo}"
            )
            return result

        # =====================================================
        # CAMADA 2: Inteligência Artificial
        # =====================================================
        embedding, vector_match, llm_result = await layer2_ai(product, pool)

        # 2a. Match vetorial encontrado (similaridade >= 0.98)
        if vector_match is not None:
            metrics.layer2_vector += 1
            logger.info(
                f"[Linha {product.row_index}] Camada 2 ✓ Busca Vetorial "
                f"(sim={vector_match.similarity:.4f}) → "
                f"{vector_match.grupo}/{vector_match.subgrupo}"
            )
            return ProductOutput(
                row_index=product.row_index,
                descricao=product.descricao,
                ean=product.ean,
                ncm=product.ncm,
                grupo=vector_match.grupo,
                subgrupo=vector_match.subgrupo,
                origem="Busca Vetorial",
                status="Aprovado",
            )

        # 2b. Classificação via LLM
        if llm_result is None:
            metrics.errors += 1
            logger.warning(f"[Linha {product.row_index}] LLM falhou → Pendente de Revisão")
            return ProductOutput(
                row_index=product.row_index,
                descricao=product.descricao,
                ean=product.ean,
                ncm=product.ncm,
                grupo="",
                subgrupo="",
                origem="Erro",
                status="Pendente de Revisão",
            )

        # =====================================================
        # CAMADA 3: Filtro de Segurança e Auto-Save
        # =====================================================
        output = layer3_filter(product, llm_result)

        if output.status == "Aprovado":
            metrics.layer2_llm_approved += 1
            logger.info(
                f"[Linha {product.row_index}] Camada 3 ✓ LLM Aprovado "
                f"(confiança={llm_result.grau_de_confianca}%) → "
                f"{output.grupo}/{output.subgrupo}"
            )
            try:
                # Auto-Save no Supabase (product_history) com o embedding da descrição
                await save_to_history(
                    product, output.grupo, output.subgrupo,
                    embedding, "LLM", pool,
                )
            except Exception as e:
                logger.warning(f"[Linha {product.row_index}] Erro ao salvar no histórico: {e}")
        else:
            metrics.layer2_llm_pending += 1
            logger.info(
                f"[Linha {product.row_index}] Camada 3 ✗ LLM Baixa Confiança "
                f"(confiança={llm_result.grau_de_confianca}%) → Pendente de Revisão"
            )

        return output

    except Exception as e:
        metrics.errors += 1
        logger.error(f"[Linha {product.row_index}] Erro no processamento: {e}", exc_info=True)
        return ProductOutput(
            row_index=product.row_index,
            descricao=product.descricao,
            ean=product.ean,
            ncm=product.ncm,
            grupo="",
            subgrupo="",
            origem="Erro",
            status="Pendente de Revisão",
        )


async def process_products(
    products: list[ProductInput],
    pool: asyncpg.Pool,
    concurrency: int = 5,
) -> tuple[list[ProductOutput], dict]:
    """
    Processa uma lista de produtos pelo funil com concorrência controlada.
    """
    metrics = FunnelMetrics()
    metrics.total = len(products)
    semaphore = asyncio.Semaphore(concurrency)

    async def process_with_semaphore(product: ProductInput) -> ProductOutput:
        async with semaphore:
            return await process_single_product(product, pool, metrics)

    logger.info(f"Iniciando processamento de {len(products)} produtos (concorrência={concurrency})")

    tasks = [process_with_semaphore(p) for p in products]
    results = await asyncio.gather(*tasks)

    results_sorted = sorted(results, key=lambda r: r.row_index)

    summary = metrics.summary()
    logger.info(f"Processamento concluído. Métricas: {summary}")

    return results_sorted, summary
