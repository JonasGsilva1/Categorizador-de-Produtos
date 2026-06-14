"""
Cliente Google Gemini para geração de embeddings.
Suporta chamadas assíncronas para o modelo gemini-embedding-001.
"""

import logging
import asyncio
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
                if attempt < max_retries:
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
