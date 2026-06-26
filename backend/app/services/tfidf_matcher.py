"""
Camada 2 do Funil: Matcher TF-IDF local.

Substitui completamente embeddings Gemini + busca pgvector.
Carrega product_history do banco, treina TfidfVectorizer em memória e serve
buscas por cosine similarity — sem nenhuma chamada a APIs externas.

Cache global com TTL de 5 minutos; invalidação forçada disponível para o
endpoint de feedback usar após cada retroalimentação.
"""

import asyncio
import logging
import time

import asyncpg
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache global (módulo-level, compartilhado entre coroutines)
# ---------------------------------------------------------------------------
_vetorizador: TfidfVectorizer | None = None
_matriz = None        # matriz esparsa scipy (n_docs × vocab)
_registros: list[dict] = []  # [{"grupo": str, "subgrupo": str, "descricao": str}]
_trava = asyncio.Lock()
_ultimo_carregamento: float = 0.0
TTL_CACHE: int = 300  # segundos — recarregar a cada 5 minutos


async def load_index(pool_db: asyncpg.Pool, forcar: bool = False) -> None:
    """
    Carrega ou recarrega o índice TF-IDF a partir de product_history.

    A trava (lock) garante que apenas uma coroutine carregue o índice por vez.
    Chamadas concorrentes aguardam e reutilizam o índice recém-carregado.

    Args:
        pool_db:  Pool asyncpg ativo.
        forcar: Se True, ignora o TTL e reconstrói o índice imediatamente.
               Use após upserts de feedback para manter coerência.
    """
    global _vetorizador, _matriz, _registros, _ultimo_carregamento

    async with _trava:
        agora = time.monotonic()
        if not forcar and _vetorizador is not None and (agora - _ultimo_carregamento) < TTL_CACHE:
            return  # cache ainda válido

        logger.info("Carregando índice TF-IDF de product_history...")

        async with pool_db.acquire() as conexao:
            linhas = await conexao.fetch(
                """
                SELECT descricao, grupo, subgrupo
                FROM product_history
                WHERE grupo IS NOT NULL AND grupo != ''
                  AND subgrupo IS NOT NULL AND subgrupo != ''
                """
            )

        if not linhas:
            logger.warning("product_history vazio — índice TF-IDF não criado.")
            return

        _registros = [
            {
                "descricao": r["descricao"],
                "grupo": r["grupo"],
                "subgrupo": r["subgrupo"],
            }
            for r in linhas
        ]
        textos = [r["descricao"] for r in _registros]

        _vetorizador = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            strip_accents="unicode",
            lowercase=True,
        )
        _matriz = _vetorizador.fit_transform(textos)
        _ultimo_carregamento = time.monotonic()

        logger.info(
            f"Índice TF-IDF construído: {len(_registros)} documentos, "
            f"{_matriz.shape[1]} features."
        )


async def tfidf_search(
    descricao: str,
    pool_db: asyncpg.Pool,
    limite: float = 0.65,
) -> dict | None:
    """
    Busca o produto mais similar no índice TF-IDF por similaridade de cosseno.

    Args:
        descricao: Descrição do produto a classificar.
        pool_db:      Pool asyncpg para recarregar o índice se necessário.
        limite: Similaridade mínima para aceitar a correspondência (padrão 0.65).

    Returns:
        Dict ``{"grupo": str, "subgrupo": str, "similarity": float}``
        ou None se nenhuma correspondência atingir o limite.
    """
    global _vetorizador, _matriz, _registros

    if _vetorizador is None:
        await load_index(pool_db)

    if _vetorizador is None or _matriz is None or not _registros:
        logger.debug("Índice TF-IDF indisponível — pulando Camada 2.")
        return None

    vetor = _vetorizador.transform([descricao])
    similaridades: np.ndarray = cosine_similarity(vetor, _matriz).flatten()

    melhor_indice = int(np.argmax(similaridades))
    melhor_pontuacao = float(similaridades[melhor_indice])

    if melhor_pontuacao >= limite:
        correspondencia = _registros[melhor_indice]
        logger.debug(
            f"TF-IDF match: sim={melhor_pontuacao:.4f} → "
            f"{correspondencia['grupo']}/{correspondencia['subgrupo']} "
            f"(ref: '{correspondencia['descricao'][:60]}')"
        )
        return {
            "grupo": correspondencia["grupo"],
            "subgrupo": correspondencia["subgrupo"],
            "similarity": melhor_pontuacao,
        }

    logger.debug(f"TF-IDF sem correspondência acima de {limite}: melhor={melhor_pontuacao:.4f}")
    return None


def invalidate_cache() -> None:
    """
    Invalida o cache TF-IDF de forma síncrona (zera _ultimo_carregamento).

    Útil quando o load_index com force=True não pode ser aguardado.
    O próximo tfidf_search recarregará o índice automaticamente.
    """
    global _ultimo_carregamento
    _ultimo_carregamento = 0.0
    logger.info("Cache TF-IDF invalidado.")
