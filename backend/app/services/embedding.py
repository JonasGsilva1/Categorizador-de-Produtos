"""
Cliente Google Gemini para geração de embeddings.
Suporta chamadas assíncronas para o modelo gemini-embedding-001.

Rate Limiting:
  O tier gratuito do Gemini permite 100 requests/minuto para embeddings.
  Este módulo implementa controle de taxa para evitar 429 RESOURCE_EXHAUSTED.
"""

import logging
import asyncio
import re
import time
from google import genai
from google.genai import errors as genai_errors
from app.config import get_settings

logger = logging.getLogger(__name__)

# Cliente singleton
_client: genai.Client | None = None

# ── Rate Limiter ──────────────────────────────────────────────────────────────
# Limite conservador: 80 req/min (margem de 20% sobre o limite de 100)
_RATE_LIMIT_RPM = 80
_MIN_INTERVAL = 60.0 / _RATE_LIMIT_RPM  # ~0.75s entre requests

_last_request_time: float = 0.0
_rate_lock = asyncio.Lock()


async def _wait_rate_limit() -> None:
    """Garante intervalo mínimo entre chamadas à API de embeddings."""
    global _last_request_time
    async with _rate_lock:
        now = time.monotonic()
        elapsed = now - _last_request_time
        if elapsed < _MIN_INTERVAL:
            wait = _MIN_INTERVAL - elapsed
            await asyncio.sleep(wait)
        _last_request_time = time.monotonic()


def _parse_retry_delay(error: genai_errors.ClientError) -> float | None:
    """
    Tenta extrair o retryDelay sugerido pela API a partir da mensagem de erro.
    Retorna o delay em segundos ou None se não encontrado.
    """
    error_str = str(error)
    # Procura padrões como "retry in 10.15007533s" ou "retryDelay: 10s"
    match = re.search(r'retry\s*(?:in|Delay["\s:]*)\s*([\d.]+)\s*s', error_str, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


def _get_client() -> genai.Client:
    """Retorna o cliente Gemini (singleton)."""
    global _client
    if _client is None:
        settings = get_settings()
        # Inicializa o cliente com a chave da API
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def generate_embedding(text: str) -> list[float]:
    """
    Gera embedding para um texto único usando Gemini.
    Usa o cliente assíncrono (client.aio) com rate limiting.
    """
    settings = get_settings()
    client = _get_client()

    clean_text = text.strip().replace("\n", " ")
    if not clean_text:
        return [0.0] * settings.embedding_dimensions

    max_retries = 5
    base_delay = 10

    for attempt in range(1, max_retries + 1):
        try:
            await _wait_rate_limit()
            response = await client.aio.models.embed_content(
                model=settings.embedding_model,
                contents=clean_text,
                config={"output_dimensionality": settings.embedding_dimensions}
            )
            return response.embeddings[0].values

        except genai_errors.ClientError as e:
            if e.code == 429 and attempt < max_retries:
                api_delay = _parse_retry_delay(e)
                delay = api_delay if api_delay else base_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"Rate limit (429) ao gerar embedding. "
                    f"Tentativa {attempt}/{max_retries}. Aguardando {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
            elif attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"Client Error ({e.code}) ao gerar embedding. "
                    f"Tentativa {attempt}/{max_retries}. Aguardando {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"Erro ao gerar embedding após {max_retries} tentativas: {e}")
                return [0.0] * settings.embedding_dimensions

        except Exception as e:
            logger.error(f"Erro inesperado ao gerar embedding: {e}")
            return [0.0] * settings.embedding_dimensions

    return [0.0] * settings.embedding_dimensions


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Gera embeddings em lote para múltiplos textos usando Gemini.
    Inclui rate limiting e retry inteligente com backoff.
    """
    settings = get_settings()
    client = _get_client()
    batch_size = settings.embedding_batch_size
    all_embeddings: list[list[float]] = []
    total_batches = (len(texts) + batch_size - 1) // batch_size

    for batch_idx, i in enumerate(range(0, len(texts), batch_size)):
        batch = texts[i:i + batch_size]
        clean_batch = [t.strip().replace("\n", " ") if t.strip() else "vazio" for t in batch]

        max_retries = 5
        base_delay = 12  # Ligeiramente acima do retryDelay típico de ~10s
        batch_success = False

        for attempt in range(1, max_retries + 1):
            try:
                await _wait_rate_limit()

                # Gemini suporta passar uma lista de strings
                response = await client.aio.models.embed_content(
                    model=settings.embedding_model,
                    contents=clean_batch,
                    config={"output_dimensionality": settings.embedding_dimensions}
                )
                # Extrair os valores
                batch_embeddings = [emb.values for emb in response.embeddings]
                all_embeddings.extend(batch_embeddings)
                batch_success = True

                logger.debug(
                    f"Embedding batch {batch_idx + 1}/{total_batches} "
                    f"({len(batch)} textos) concluído."
                )
                break

            except genai_errors.ClientError as e:
                if e.code == 429:
                    # Rate limit — usar delay da API se disponível
                    api_delay = _parse_retry_delay(e)
                    delay = api_delay if api_delay else base_delay * (2 ** (attempt - 1))
                    # Adicionar margem de segurança ao delay da API
                    if api_delay:
                        delay += 2.0

                    if attempt < max_retries:
                        logger.warning(
                            f"Rate limit (429) no batch {batch_idx + 1}/{total_batches}. "
                            f"Tentativa {attempt}/{max_retries}. "
                            f"Aguardando {delay:.1f}s antes de retry..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"Rate limit persistente no batch {batch_idx + 1} "
                            f"após {max_retries} tentativas: {e}"
                        )
                elif attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"Client Error ({e.code}) no Gemini Embeddings. "
                        f"Tentativa {attempt}/{max_retries}. "
                        f"Aguardando {delay}s antes de retry..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Erro ao gerar embeddings após {max_retries} tentativas: {e}"
                    )

            except Exception as e:
                logger.error(
                    f"Erro inesperado ao gerar embeddings para batch {batch_idx + 1}: {e}"
                )
                break

        if not batch_success:
            all_embeddings.extend(
                [[0.0] * settings.embedding_dimensions] * len(batch)
            )

    return all_embeddings
