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

# Cliente singleton (única instância)
_cliente: genai.Client | None = None

def _obter_cliente() -> genai.Client:
    """Retorna o cliente Gemini (singleton)."""
    global _cliente
    if _cliente is None:
        configuracoes = get_settings()
        # Inicializa o cliente com a chave da API
        _cliente = genai.Client(api_key=configuracoes.gemini_api_key)
    return _cliente


def _extrair_atraso_tentativa(mensagem_erro: str) -> float:
    """
    Extrai o tempo de espera exigido pelo servidor a partir da mensagem de erro.
    Cobre dois formatos retornados pela API:
      - Texto: "Please retry in 10.15007533s" (decimais ignoradas)
      - Dicionário: 'retryDelay': '53s' ou "retryDelay": "53s"
    Retorna o atraso em segundos + 1s de margem de segurança.
    Se não encontrar, retorna 60s como fallback fixo.
    """
    # Formato dicionário: 'retryDelay': '53s' ou "retryDelay": "53s"
    correspondencia = re.search(r"['\"]retryDelay['\"]:\s*['\"]?(\d+)s['\"]?", mensagem_erro)
    if correspondencia:
        return int(correspondencia.group(1)) + 1

    # Formato texto: Please retry in 10.15007533s (captura apenas a parte inteira)
    correspondencia = re.search(r"retry in (\d+)", mensagem_erro, re.IGNORECASE)
    if correspondencia:
        return int(correspondencia.group(1)) + 1

    return 60


async def generate_embedding(texto: str) -> list[float]:
    """
    Gera embedding para um texto único usando Gemini.
    Usa o cliente assíncrono (client.aio).
    """
    configuracoes = get_settings()
    cliente = _obter_cliente()

    texto_limpo = texto.strip().replace("\n", " ")
    if not texto_limpo:
        return [0.0] * configuracoes.embedding_dimensions

    try:
        resposta = await cliente.aio.models.embed_content(
            model=configuracoes.embedding_model,
            contents=texto_limpo,
            config={"output_dimensionality": configuracoes.embedding_dimensions}
        )
        return resposta.embeddings[0].values
    except Exception as excecao:
        erro_str = str(excecao)
        if "429" in erro_str or "RESOURCE_EXHAUSTED" in erro_str:
            atraso = _extrair_atraso_tentativa(erro_str)
            logger.warning(
                f"Limite de taxa (429/RESOURCE_EXHAUSTED) ao gerar embedding. "
                f"Aguardando {atraso}s antes de tentar novamente..."
            )
            await asyncio.sleep(atraso)
            try:
                resposta = await cliente.aio.models.embed_content(
                    model=configuracoes.embedding_model,
                    contents=texto_limpo,
                    config={"output_dimensionality": configuracoes.embedding_dimensions}
                )
                return resposta.embeddings[0].values
            except Exception as erro_tentativa:
                logger.error(f"Erro ao gerar embedding após tentativa: {erro_tentativa}")
                return [0.0] * configuracoes.embedding_dimensions
        else:
            logger.error(f"Erro ao gerar embedding: {excecao}")
            return [0.0] * configuracoes.embedding_dimensions


async def generate_embeddings_batch(textos: list[str]) -> list[list[float]]:
    """
    Gera embeddings em lote para múltiplos textos usando Gemini.

    Estratégia de limite de taxa (rate limit):
    - Para 429/RESOURCE_EXHAUSTED: tenta novamente indefinidamente respeitando o atraso
      indicado pela API (sem limite de tentativas), pois o item NÃO deve ser
      descartado — simplesmente a cota ainda não se renovou.
    - Para outros erros de cliente: até 3 tentativas com recuo exponencial.
    - Atraso fixo de 1s entre lotes para espaçar as chamadas e reduzir pressão.
    """
    configuracoes = get_settings()
    cliente = _obter_cliente()
    tamanho_lote = configuracoes.embedding_batch_size
    todos_embeddings: list[list[float]] = []

    for indice in range(0, len(textos), tamanho_lote):
        lote = textos[indice:indice + tamanho_lote]
        lote_limpo = [t.strip().replace("\n", " ") if t.strip() else "vazio" for t in lote]

        max_tentativas_cliente = 3
        atraso_base = 10
        sucesso_lote = False
        tentativas_erro_cliente = 0

        while not sucesso_lote:
            try:
                resposta = await cliente.aio.models.embed_content(
                    model=configuracoes.embedding_model,
                    contents=lote_limpo,
                    config={"output_dimensionality": configuracoes.embedding_dimensions}
                )
                embeddings_do_lote = [emb.values for emb in resposta.embeddings]
                todos_embeddings.extend(embeddings_do_lote)
                sucesso_lote = True

            except genai_errors.ClientError as erro_cliente:
                erro_str = str(erro_cliente)
                logger.debug(f"[DEBUG] String de erro bruta: {erro_str}")

                if "429" in erro_str or "RESOURCE_EXHAUSTED" in erro_str:
                    # Limite de taxa: espera o tempo que a API pediu e tenta novamente sempre
                    atraso = _extrair_atraso_tentativa(erro_str)
                    numero_lote = indice // tamanho_lote + 1
                    total_lotes = (len(textos) + tamanho_lote - 1) // tamanho_lote
                    logger.warning(
                        f"Limite de taxa no lote {numero_lote}/{total_lotes}. "
                        f"Aguardando {atraso}s conforme indicado pela API..."
                    )
                    await asyncio.sleep(atraso)
                    # Não incrementa tentativas_erro_cliente — limite de taxa não é erro fatal

                else:
                    tentativas_erro_cliente += 1
                    if tentativas_erro_cliente < max_tentativas_cliente:
                        atraso = atraso_base * (2 ** (tentativas_erro_cliente - 1))
                        logger.warning(
                            f"Erro de Cliente no lote {indice}. "
                            f"Tentativa {tentativas_erro_cliente}/{max_tentativas_cliente}. "
                            f"Aguardando {atraso}s..."
                        )
                        await asyncio.sleep(atraso)
                    else:
                        logger.error(
                            f"Erro ao gerar embeddings após {max_tentativas_cliente} "
                            f"tentativas no lote {indice}: {erro_cliente}"
                        )
                        break

            except Exception as excecao_inesperada:
                logger.error(f"Erro inesperado ao gerar embeddings para o lote {indice}: {excecao_inesperada}")
                break

        if not sucesso_lote:
            todos_embeddings.extend([[0.0] * configuracoes.embedding_dimensions] * len(lote))

        # Pequena pausa entre lotes para reduzir pressão sobre a cota
        if indice + tamanho_lote < len(textos):
            await asyncio.sleep(1)

    return todos_embeddings
