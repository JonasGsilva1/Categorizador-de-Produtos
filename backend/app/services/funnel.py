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

from app.models import ProdutoEntrada, ProdutoSaida
from app.services.layer1_deterministic import layer1_lookup
from app.services.tfidf_matcher import load_index, tfidf_search
from app.services.keyword_classifier import classify_by_keywords

logger = logging.getLogger(__name__)

# Tipo do callback de progresso: recebe (linhas_processadas, aprovados, pendentes, erros)
CallbackDeProgresso = Callable[[int, int, int, int], Awaitable[None]]


class MetricasDoFunil:
    """Contadores de métricas do funil. Mantém a mesma interface usada pelo job_manager."""

    def __init__(self):
        self.total: int = 0
        self.camada1_ean: int = 0        # inclui NCM (Camada 1A/1B)
        self.camada2_vetor: int = 0     # TF-IDF (Camada 2)
        self.camada2_llm_aprovado: int = 0  # Palavras-chave (Camada 3)
        self.camada2_llm_pendente: int = 0   # Pendente de Revisão
        self.erros: int = 0

    @property
    def resolvidos(self) -> int:
        return (
            self.camada1_ean
            + self.camada2_vetor
            + self.camada2_llm_aprovado
            + self.camada2_llm_pendente
            + self.erros
        )

    @property
    def aprovados(self) -> int:
        return self.camada1_ean + self.camada2_vetor + self.camada2_llm_aprovado

    def summary(self) -> dict:
        """
        Retorna o sumário no formato esperado pelo job_manager.py.
        Os nomes dos campos são mantidos idênticos à versão anterior para compatibilidade.
        """
        return {
            "total_processado": self.total,
            "camada1_ean": self.camada1_ean,
            "camada2_busca_vetorial": self.camada2_vetor,
            "camada2_llm_aprovado": self.camada2_llm_aprovado,
            "camada2_llm_pendente_revisao": self.camada2_llm_pendente,
            "erros": self.erros,
        }


async def process_products(
    produtos: list[ProdutoEntrada],
    pool_db: asyncpg.Pool,
    concorrencia: int = 5,
    ao_progredir: CallbackDeProgresso | None = None,
) -> tuple[list[ProdutoSaida], dict]:
    """
    Processa a lista de produtos pelo funil local/determinístico.

    Etapas:
      1. Pré-carrega o índice TF-IDF (uma única vez; cache em memória).
      2. Para cada produto, tenta Camada 1 → Camada 2 → Camada 3 → Pendente.
      3. Reporta progresso após cada lote via ao_progredir (para o job_manager).

    Args:
        produtos:    Lista de ProdutoEntrada lidos da planilha.
        pool_db:        Pool asyncpg ativo.
        concorrencia: Parâmetro mantido para compatibilidade; controla o semáforo DB.
        ao_progredir: Callback async chamado após cada lote.

    Returns:
        Tupla (resultados ordenados por row_index, dicionário de métricas).
    """
    metricas = MetricasDoFunil()
    metricas.total = len(produtos)
    resultados: list[ProdutoSaida] = []

    semaforo_db = asyncio.Semaphore(4)

    # Pré-carregar índice TF-IDF antes de processar
    logger.info("Pré-carregando índice TF-IDF...")
    await load_index(pool_db)

    logger.info(
        f"Iniciando funil local para {len(produtos)} produto(s) "
        f"(Camadas: 1-EAN/NCM → 2-TF-IDF → 3-Palavras-chave)"
    )

    tamanho_lote = 50
    for inicio_lote in range(0, len(produtos), tamanho_lote):
        lote = produtos[inicio_lote : inicio_lote + tamanho_lote]
        numero_lote = inicio_lote // tamanho_lote + 1
        logger.info(
            f"Lote {numero_lote} — {len(lote)} produto(s) "
            f"(total processado até agora: {metricas.resolvidos})"
        )

        for produto in lote:
            # ── Camada 1: EAN + NCM ──────────────────────────────────────────
            try:
                async with semaforo_db:
                    resultado_camada1 = await layer1_lookup(produto, pool_db)
            except Exception as excecao:
                logger.error(
                    f"[Linha {produto.row_index}] Erro na Camada 1: {excecao}",
                    exc_info=True,
                )
                metricas.erros += 1
                resultados.append(
                    ProdutoSaida(
                        row_index=produto.row_index,
                        descricao=produto.descricao,
                        ean=produto.ean,
                        ncm=produto.ncm,
                        grupo="",
                        subgrupo="",
                        origem="Erro",
                        status="Pendente de Revisão",
                    )
                )
                continue

            if resultado_camada1:
                metricas.camada1_ean += 1
                logger.info(
                    f"[Linha {produto.row_index}] Camada 1 ✓ {resultado_camada1.origem} "
                    f"→ {resultado_camada1.grupo}/{resultado_camada1.subgrupo}"
                )
                resultados.append(resultado_camada1)
                continue

            # ── Camada 2: TF-IDF ─────────────────────────────────────────────
            try:
                resultado_tfidf = await tfidf_search(produto.descricao, pool_db)
            except Exception as excecao:
                logger.warning(
                    f"[Linha {produto.row_index}] Erro na Camada 2 (TF-IDF): {excecao}",
                    exc_info=True,
                )
                resultado_tfidf = None

            if resultado_tfidf:
                metricas.camada2_vetor += 1
                logger.info(
                    f"[Linha {produto.row_index}] Camada 2 ✓ TF-IDF "
                    f"(sim={resultado_tfidf['similarity']:.3f}) "
                    f"→ {resultado_tfidf['grupo']}/{resultado_tfidf['subgrupo']}"
                )
                resultados.append(
                    ProdutoSaida(
                        row_index=produto.row_index,
                        descricao=produto.descricao,
                        ean=produto.ean,
                        ncm=produto.ncm,
                        grupo=resultado_tfidf["grupo"],
                        subgrupo=resultado_tfidf["subgrupo"],
                        origem="TF-IDF",
                        status="Aprovado",
                    )
                )
                continue

            # ── Camada 3: Palavras-chave ──────────────────────────────────────
            try:
                resultado_palavras_chave = classify_by_keywords(produto.descricao)
            except Exception as excecao:
                logger.warning(
                    f"[Linha {produto.row_index}] Erro na Camada 3 (Palavras-chave): {excecao}",
                    exc_info=True,
                )
                resultado_palavras_chave = None

            if resultado_palavras_chave:
                metricas.camada2_llm_aprovado += 1
                logger.info(
                    f"[Linha {produto.row_index}] Camada 3 ✓ Palavras-chave "
                    f"→ {resultado_palavras_chave['grupo']}/{resultado_palavras_chave['subgrupo']}"
                )
                resultados.append(
                    ProdutoSaida(
                        row_index=produto.row_index,
                        descricao=produto.descricao,
                        ean=produto.ean,
                        ncm=produto.ncm,
                        grupo=resultado_palavras_chave["grupo"],
                        subgrupo=resultado_palavras_chave["subgrupo"],
                        origem="Palavras-chave",
                        status="Aprovado",
                    )
                )
                continue

            # ── Pendente de Revisão ───────────────────────────────────────────
            metricas.camada2_llm_pendente += 1
            logger.info(
                f"[Linha {produto.row_index}] Nenhuma camada classificou "
                f"'{produto.descricao[:50]}' → Pendente de Revisão"
            )
            resultados.append(
                ProdutoSaida(
                    row_index=produto.row_index,
                    descricao=produto.descricao,
                    ean=produto.ean,
                    ncm=produto.ncm,
                    grupo="",
                    subgrupo="",
                    origem="Não classificado",
                    status="Pendente de Revisão",
                )
            )

        # Reportar progresso ao final de cada lote
        if ao_progredir:
            await ao_progredir(
                metricas.resolvidos,
                metricas.aprovados,
                metricas.camada2_llm_pendente,
                metricas.erros,
            )

    sumario = metricas.summary()
    logger.info(f"Funil concluído. Métricas: {sumario}")
    return sorted(resultados, key=lambda r: r.row_index), sumario
