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
# Cache global (módulo-level, shared entre coroutines)
# ---------------------------------------------------------------------------
_vectorizer: TfidfVectorizer | None = None
_matrix = None        # scipy sparse matrix (n_docs × vocab)
_records: list[dict] = []  # [{"grupo": str, "subgrupo": str, "descricao": str}]
_lock = asyncio.Lock()
_last_loaded: float = 0.0
CACHE_TTL: int = 300  # segundos — recarregar a cada 5 minutos


async def load_index(pool: asyncpg.Pool, force: bool = False) -> None:
    """
    Carrega ou recarrega o índice TF-IDF a partir de product_history.

    O lock garante que apenas uma coroutine carregue o índice por vez.
    Chamadas concorrentes aguardam e reutilizam o índice recém-carregado.

    Args:
        pool:  Pool asyncpg ativo.
        force: Se True, ignora o TTL e reconstrói o índice imediatamente.
               Use após upserts de feedback para manter coerência.
    """
    global _vectorizer, _matrix, _records, _last_loaded

    async with _lock:
        now = time.monotonic()
        if not force and _vectorizer is not None and (now - _last_loaded) < CACHE_TTL:
            return  # cache ainda válido

        logger.info("Carregando índice TF-IDF de product_history...")

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT descricao, grupo, subgrupo
                FROM product_history
                WHERE grupo IS NOT NULL AND grupo != ''
                  AND subgrupo IS NOT NULL AND subgrupo != ''
                """
            )

        if not rows:
            logger.warning("product_history vazio — índice TF-IDF não criado.")
            return

        _records = [
            {
                "descricao": r["descricao"],
                "grupo": r["grupo"],
                "subgrupo": r["subgrupo"],
            }
            for r in rows
        ]
        texts = [r["descricao"] for r in _records]

        _vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            strip_accents="unicode",
            lowercase=True,
        )
        _matrix = _vectorizer.fit_transform(texts)
        _last_loaded = time.monotonic()

        logger.info(
            f"Índice TF-IDF construído: {len(_records)} documentos, "
            f"{_matrix.shape[1]} features."
        )


async def tfidf_search(
    descricao: str,
    pool: asyncpg.Pool,
    threshold: float = 0.65,
) -> dict | None:
    """
    Busca o produto mais similar no índice TF-IDF por cosine similarity.

    Args:
        descricao: Descrição do produto a classificar.
        pool:      Pool asyncpg para recarregar o índice se necessário.
        threshold: Similaridade mínima para aceitar o match (padrão 0.65).

    Returns:
        Dict ``{"grupo": str, "subgrupo": str, "similarity": float}``
        ou None se nenhum match atingir o threshold.
    """
    global _vectorizer, _matrix, _records

    if _vectorizer is None:
        await load_index(pool)

    if _vectorizer is None or _matrix is None or not _records:
        logger.debug("Índice TF-IDF indisponível — pulando Camada 2.")
        return None

    vec = _vectorizer.transform([descricao])
    sims: np.ndarray = cosine_similarity(vec, _matrix).flatten()

    best_idx = int(np.argmax(sims))
    best_score = float(sims[best_idx])

    if best_score >= threshold:
        match = _records[best_idx]
        logger.debug(
            f"TF-IDF match: sim={best_score:.4f} → "
            f"{match['grupo']}/{match['subgrupo']} "
            f"(ref: '{match['descricao'][:60]}')"
        )
        return {
            "grupo": match["grupo"],
            "subgrupo": match["subgrupo"],
            "similarity": best_score,
        }

    logger.debug(f"TF-IDF sem match acima de {threshold}: melhor={best_score:.4f}")
    return None


def invalidate_cache() -> None:
    """
    Invalida o cache TF-IDF de forma síncrona (zera _last_loaded).

    Útil quando o load_index com force=True não pode ser aguardado.
    O próximo tfidf_search recarregará o índice automaticamente.
    """
    global _last_loaded
    _last_loaded = 0.0
    logger.info("Cache TF-IDF invalidado.")
