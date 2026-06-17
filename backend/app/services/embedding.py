"""
Cliente Google Gemini para geração de embeddings.
Suporta chamadas assíncronas para o modelo gemini-embedding-001.
"""

import logging
import asyncio
import re
from google import genai
from google.genai import errors as genai_errors
from app.config import get_settings

logger = logging.getLogger(__name__)

# Cliente singleton
_client: genai.Client | None = None

def _get_client() -> genai.Client:
    """Retorna o cliente Gemini (singleton)."""
    global _client
    if _client is None:
        settings = get_settings()
        # Inicializa o cliente com a chave da API
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _extract_retry_delay(error_message: str) -> float:
    """
    Extrai o tempo de espera exigido pelo servidor a partir da mensagem de erro.
    Cobre dois formatos retornados pela API:
      - Texto: "Please retry in 10.15007533s" (decimais ignoradas)
      - Dicionário: "'retryDelay': '53s'"
    Retorna o delay em segundos + 1s de margem de segurança.
    Se não encontrar, retorna 60s como fallback fixo.
    """
    # Formato dicionário: 'retryDelay': '53s'
    match = re.search(r"'retryDelay':\s*'(\d+)s'", error_message)
    if match:
        return int(match.group(1)) + 1

    # Formato texto: Please retry in 10.15007533s (captura apenas a parte inteira)
    match = re.search(r"retry in (\d+)", error_message, re.IGNORECASE)
    if match:
        return int(match.group(1)) + 1

    return 60


async def generate_embedding(text: str) -> list[float]:
    """
    Gera embedding para um texto único usando Gemini.
    Usa o cliente assíncrono (client.aio).
    """
    settings = get_settings()
    client = _get_client()

    clean_text = text.strip().replace("\n", " ")
    if not clean_text:
        return [0.0] * settings.embedding_dimensions

    try:
        response = await client.aio.models.embed_content(
            model=settings.embedding_model,
            contents=clean_text,
            config={"output_dimensionality": settings.embedding_dimensions}
        )
        return response.embeddings[0].values
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            delay = _extract_retry_delay(error_str)
            logger.warning(
                f"Rate limit (429/RESOURCE_EXHAUSTED) ao gerar embedding. "
                f"Aguardando {delay}s antes de retry..."
            )
            await asyncio.sleep(delay)
            try:
                response = await client.aio.models.embed_content(
                    model=settings.embedding_model,
                    contents=clean_text,
                    config={"output_dimensionality": settings.embedding_dimensions}
                )
                return response.embeddings[0].values
            except Exception as retry_error:
                logger.error(f"Erro ao gerar embedding após retry: {retry_error}")
                return [0.0] * settings.embedding_dimensions
        else:
            logger.error(f"Erro ao gerar embedding: {e}")
            return [0.0] * settings.embedding_dimensions


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Gera embeddings em lote para múltiplos textos usando Gemini.
    """
    settings = get_settings()
    client = _get_client()
    batch_size = settings.embedding_batch_size
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        clean_batch = [t.strip().replace("\n", " ") if t.strip() else "vazio" for t in batch]

        max_retries = 3
        base_delay = 10
        batch_success = False

        for attempt in range(1, max_retries + 1):
            try:
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
                break
                
            except genai_errors.ClientError as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    delay = _extract_retry_delay(error_str)
                    logger.warning(
                        f"Rate limit (429/RESOURCE_EXHAUSTED) no batch {i}. "
                        f"Tentativa {attempt}/{max_retries}. "
                        f"Aguardando {delay}s antes de retry..."
                    )
                    await asyncio.sleep(delay)
                elif attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"Client Error ({e.code}) no Gemini Embeddings. Tentativa {attempt}/{max_retries}. "
                        f"Aguardando {delay}s antes de retry..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Erro ao gerar embeddings após {max_retries} tentativas: {e}")
                    
            except Exception as e:
                logger.error(f"Erro inesperado ao gerar embeddings para batch {i}: {e}")
                break

        if not batch_success:
            all_embeddings.extend([[0.0] * settings.embedding_dimensions] * len(batch))

    return all_embeddings
