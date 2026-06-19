"""
Orquestrador do Funil de Categorização — Arquitetura local/determinística.

Nova ordem de processamento (sem dependência de APIs externas no caminho crítico):

  Camada 1A  EAN exato         → layer1_deterministic.layer1_lookup (inclui NCM 1B)
  Camada 2   TF-IDF local      → tfidf_matcher.tfidf_search
  Camada 3   Palavras-chave    → keyword_classifier.classify_by_keywords
  Fallback   Pendente de Revisão

O Gemini (embedding + LLM) não é chamado neste fluxo.
Os imports dos módulos antigos são mantidos nos respectivos arquivos para uso opcional.
"""

import logging
import asyncio
from typing import Callable, Awaitable
import asyncpg

from app.models import ProductInput, ProductOutput
from app.services.layer1_deterministic import layer1_lookup
from app.services.tfidf_matcher import load_index, tfidf_search
from app.services.keyword_classifier import classify_by_keywords

logger = logging.getLogger(__name__)

# Tipo do callback de progresso: recebe (processed_rows, aprovados, pendentes, erros)
ProgressCallback = Callable[[int, int, int, int], Awaitable[None]]


class FunnelMetrics:
    """Contadores de métricas do funil. Mantém a mesma interface usada pelo job_manager."""

    def __init__(self):
        self.total: int = 0
        self.layer1_ean: int = 0        # inclui NCM (Camada 1A/1B)
        self.layer2_vector: int = 0     # TF-IDF (Camada 2)
        self.layer2_llm_approved: int = 0  # Palavras-chave (Camada 3)
        self.layer2_llm_pending: int = 0   # Pendente de Revisão
        self.errors: int = 0

    @property
    def resolved(self) -> int:
        return (
            self.layer1_ean
            + self.layer2_vector
            + self.layer2_llm_approved
            + self.layer2_llm_pending
            + self.errors
        )

    @property
    def aprovados(self) -> int:
        return self.layer1_ean + self.layer2_vector + self.layer2_llm_approved

    def summary(self) -> dict:
        """
        Retorna o sumário no formato esperado pelo job_manager.py.
        Os nomes dos campos são mantidos idênticos à versão anterior.
        """
        return {
            "total_processado": self.total,
            "camada1_ean": self.layer1_ean,
            "camada2_busca_vetorial": self.layer2_vector,
            "camada2_llm_aprovado": self.layer2_llm_approved,
            "camada2_llm_pendente_revisao": self.layer2_llm_pending,
            "erros": self.errors,
        }


async def process_products(
    products: list[ProductInput],
    pool: asyncpg.Pool,
    concurrency: int = 5,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[ProductOutput], dict]:
    """
    Processa a lista de produtos pelo funil local/determinístico.

    Etapas:
      1. Pré-carrega o índice TF-IDF (uma única vez; cache em memória).
      2. Para cada produto, tenta Camada 1 → Camada 2 → Camada 3 → Pendente.
      3. Reporta progresso após cada lote via on_progress (para o job_manager).

    Args:
        products:    Lista de ProductInput lidos da planilha.
        pool:        Pool asyncpg ativo.
        concurrency: Parâmetro mantido para compatibilidade; controla o semáforo DB.
        on_progress: Callback async chamado após cada lote.

    Returns:
        Tupla (resultados ordenados por row_index, dicionário de métricas).
    """
    metrics = FunnelMetrics()
    metrics.total = len(products)
    results: list[ProductOutput] = []

    db_semaphore = asyncio.Semaphore(4)

    # Pré-carregar índice TF-IDF antes de processar
    logger.info("Pré-carregando índice TF-IDF...")
    await load_index(pool)

    logger.info(
        f"Iniciando funil local para {len(products)} produto(s) "
        f"(Camadas: 1-EAN/NCM → 2-TF-IDF → 3-Keywords)"
    )

    batch_size = 50
    for batch_start in range(0, len(products), batch_size):
        batch = products[batch_start : batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        logger.info(
            f"Lote {batch_num} — {len(batch)} produto(s) "
            f"(total processado até agora: {metrics.resolved})"
        )

        for product in batch:
            # ── Camada 1: EAN + NCM ──────────────────────────────────────────
            try:
                async with db_semaphore:
                    l1_result = await layer1_lookup(product, pool)
            except Exception as exc:
                logger.error(
                    f"[Linha {product.row_index}] Erro na Camada 1: {exc}",
                    exc_info=True,
                )
                metrics.errors += 1
                results.append(
                    ProductOutput(
                        row_index=product.row_index,
                        descricao=product.descricao,
                        ean=product.ean,
                        ncm=product.ncm,
                        grupo="",
                        subgrupo="",
                        origem="Erro",
                        status="Pendente de Revisão",
                    )
                )
                continue

            if l1_result:
                metrics.layer1_ean += 1
                logger.info(
                    f"[Linha {product.row_index}] Camada 1 ✓ {l1_result.origem} "
                    f"→ {l1_result.grupo}/{l1_result.subgrupo}"
                )
                results.append(l1_result)
                continue

            # ── Camada 2: TF-IDF ─────────────────────────────────────────────
            try:
                tfidf_result = await tfidf_search(product.descricao, pool)
            except Exception as exc:
                logger.warning(
                    f"[Linha {product.row_index}] Erro na Camada 2 (TF-IDF): {exc}",
                    exc_info=True,
                )
                tfidf_result = None

            if tfidf_result:
                metrics.layer2_vector += 1
                logger.info(
                    f"[Linha {product.row_index}] Camada 2 ✓ TF-IDF "
                    f"(sim={tfidf_result['similarity']:.3f}) "
                    f"→ {tfidf_result['grupo']}/{tfidf_result['subgrupo']}"
                )
                results.append(
                    ProductOutput(
                        row_index=product.row_index,
                        descricao=product.descricao,
                        ean=product.ean,
                        ncm=product.ncm,
                        grupo=tfidf_result["grupo"],
                        subgrupo=tfidf_result["subgrupo"],
                        origem="TF-IDF",
                        status="Aprovado",
                    )
                )
                continue

            # ── Camada 3: Palavras-chave ──────────────────────────────────────
            try:
                kw_result = classify_by_keywords(product.descricao)
            except Exception as exc:
                logger.warning(
                    f"[Linha {product.row_index}] Erro na Camada 3 (Keywords): {exc}",
                    exc_info=True,
                )
                kw_result = None

            if kw_result:
                metrics.layer2_llm_approved += 1
                logger.info(
                    f"[Linha {product.row_index}] Camada 3 ✓ Palavras-chave "
                    f"→ {kw_result['grupo']}/{kw_result['subgrupo']}"
                )
                results.append(
                    ProductOutput(
                        row_index=product.row_index,
                        descricao=product.descricao,
                        ean=product.ean,
                        ncm=product.ncm,
                        grupo=kw_result["grupo"],
                        subgrupo=kw_result["subgrupo"],
                        origem="Palavras-chave",
                        status="Aprovado",
                    )
                )
                continue

            # ── Pendente de Revisão ───────────────────────────────────────────
            metrics.layer2_llm_pending += 1
            logger.info(
                f"[Linha {product.row_index}] Nenhuma camada classificou "
                f"'{product.descricao[:50]}' → Pendente de Revisão"
            )
            results.append(
                ProductOutput(
                    row_index=product.row_index,
                    descricao=product.descricao,
                    ean=product.ean,
                    ncm=product.ncm,
                    grupo="",
                    subgrupo="",
                    origem="Não classificado",
                    status="Pendente de Revisão",
                )
            )

        # Reportar progresso ao final de cada lote
        if on_progress:
            await on_progress(
                metrics.resolved,
                metrics.aprovados,
                metrics.layer2_llm_pending,
                metrics.errors,
            )

    summary = metrics.summary()
    logger.info(f"Funil concluído. Métricas: {summary}")
    return sorted(results, key=lambda r: r.row_index), summary
