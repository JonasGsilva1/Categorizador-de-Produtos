"""
Cliente Google Gemini para classificação de produtos em lotes via LLM com Structured Outputs.
Usa gemini-1.5-flash com TypedDict Schema.
"""

import logging
import json
import asyncio
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.api_core import exceptions as google_exceptions
from app.config import get_settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    """Retorna o cliente Gemini (singleton)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client

# =============================================================
# Modelos Pydantic para Structured Outputs (response_schema)
# =============================================================
# NOTA: Usamos Pydantic BaseModel em vez de TypedDict porque o SDK
# google-genai requer modelos Pydantic para response_schema.
# TypedDict não é convertido corretamente para OpenAPI 3.0.

class ProdutoCategorizado(BaseModel):
    id_linha: int = Field(description="Índice da linha na planilha original")
    grupo: str = Field(description="Grupo/categoria principal do produto")
    subgrupo: str = Field(description="Subcategoria do produto")
    grau_de_confianca: int = Field(
        ge=0, le=100,
        description="Grau de confiança da classificação (0-100%)"
    )

class RespostaLote(BaseModel):
    produtos: List[ProdutoCategorizado] = Field(
        description="Lista de produtos categorizados"
    )

TAXONOMIA_PERMITIDA = """
OPÇÕES VÁLIDAS DE GRUPOS E SUBGRUPOS:
- Bazar e Utilidades: Utensílios de Cozinha, Recipientes de Plástico, Vidros e Taças, Panelas, Garrafas Térmicas, Talheres
- Móveis: Cadeiras e Poltronas, Mesas, Colchões e Camas, Armários e Roupeiros, Estantes e Racks
- Decoração: Espelhos, Relógios de Parede, Vasos, Quadros
- Lazer e Camping: Piscinas e Acessórios, Caixas Térmicas, Barracas, Cadeiras de Praia
- Ferramentas e Ferragens: Elétricas, Manuais, Medição, Ferragens e Cadeados
- Materiais de Construção: Pintura, Hidráulica, Elétrica
- Eletro e Eletrônicos: Eletroportáteis, Cabos e Carregadores, Áudio e Som, Acessórios de Celular, Pilhas e Baterias
- Limpeza: Utensílios de Limpeza (Vassouras/Rodos), Produtos Químicos, Lixeiras e Cestos, Organização
- Bebidas: Vinhos, Cervejas, Refrigerantes, Sucos e Chás, Água, Destilados e Ice, Energéticos
- Alimentos (Mercearia): Biscoitos e Salgadinhos, Doces e Sobremesas, Conservas e Molhos, Grãos e Massas, Óleos e Temperos, Pipoca
- Frios e Congelados: Carnes e Aves, Sorvetes e Picolés, Pratos Prontos
- Higiene e Cuidados Pessoais: Cabelo, Sabonetes, Desodorantes, Higiene Oral, Cosméticos, Absorventes
- Automotivo e Moto: Capacetes, Acessórios Moto, Acessórios Carro
- Brinquedos: Bonecas, Carrinhos e Pistas, Jogos de Tabuleiro, Pelúcias, Praia e Piscina Infantil
- Vestuário e Calçados: Chinelos e Sandálias, Peças Íntimas, Roupas, Capas de Chuva
- Tabacaria: Cigarros, Isqueiros e Fósforos, Acessórios
- Cama, Mesa e Banho: Toalhas, Tapetes, Cortinas e Varões
- Padaria e Lanchonete: Pães e Salgados, Bolos e Tortas, Refeições Prontas, Lanches Rápidos
"""

def _validate_produto(item: dict, id_linha_esperado: int) -> Optional[ProdutoCategorizado]:
    """
    Valida e sanitiza um item individual da resposta do LLM.
    Retorna None se o item for inválido.
    """
    try:
        id_linha = item.get("id_linha")
        if id_linha is None:
            logger.warning(f"Resposta do LLM omitiu id_linha no item: {item}")
            return None

        id_linha = int(id_linha)
        grupo = str(item.get("grupo", "")).strip()
        subgrupo = str(item.get("subgrupo", "")).strip()
        confianca = int(item.get("grau_de_confianca", 0))

        # Sanitizar confiança para o range [0, 100]
        confianca = max(0, min(100, confianca))

        if not grupo or not subgrupo:
            logger.warning(
                f"[Linha {id_linha}] LLM retornou grupo/subgrupo vazio → será tratado como erro"
            )
            return None

        return ProdutoCategorizado(
            id_linha=id_linha,
            grupo=grupo,
            subgrupo=subgrupo,
            grau_de_confianca=confianca,
        )
    except (ValueError, TypeError) as e:
        logger.warning(f"Erro de validação no item {id_linha_esperado}: {e}")
        return None


async def classify_products_batch(products_chunk: list[dict]) -> dict[int, ProdutoCategorizado]:
    """
    Classifica um lote de produtos enviando-os de uma vez ao Gemini.
    `products_chunk` deve ser uma lista de dicionários contendo id_linha, descricao e ncm.
    Retorna um dicionário mapeando o id_linha para o seu respectivo ProdutoCategorizado.

    Implementa retry com backoff exponencial para erros de rate limiting (429).
    """
    client = _get_client()

    # Construir o payload textual dos itens do lote
    itens_texto = []
    for p in products_chunk:
        texto = f"ID_LINHA: {p['id_linha']} | Descrição: {p['descricao']}"
        if p.get('ncm'):
            texto += f" | NCM: {p['ncm']}"
        itens_texto.append(texto)

    lista_itens_prompt = "\n".join(itens_texto)

    system_prompt = f"""Você é um classificador determinístico de dados de varejo.
Abaixo está uma lista de produtos para categorizar em lote.

REGRA 1: A Descrição é a ÚNICA fonte da verdade. Ignore o NCM se for industrial ou divergente.
REGRA 2: Você DEVE classificar escolhendo estritamente entre estas opções:\n{TAXONOMIA_PERMITIDA}
Não invente categorias. Se o produto for óbvio e estiver na lista, atribua confiança entre 85 e 100.
Certifique-se de manter exatamente o mesmo id_linha fornecido para cada produto."""

    # Retry com backoff exponencial para 429
    max_retries = 3
    base_delay = 10  # segundos

    for attempt in range(1, max_retries + 1):
        try:
            response = await client.aio.models.generate_content(
                model="gemini-1.5-flash",
                contents=[
                    {"role": "user", "parts": [{"text": f"{system_prompt}\n\nPRODUTOS A CLASSIFICAR:\n{lista_itens_prompt}"}]}
                ],
                config={
                    "response_mime_type": "application/json",
                    "response_schema": RespostaLote,
                    "temperature": 0.1,
                }
            )

            data = json.loads(response.text)
            produtos_raw = data.get("produtos", [])

            # Montar o mapeamento com validação individual
            mapeamento: dict[int, ProdutoCategorizado] = {}
            for item in produtos_raw:
                validado = _validate_produto(item, item.get("id_linha", -1))
                if validado:
                    mapeamento[validado["id_linha"]] = validado

            # Log de itens ausentes na resposta
            ids_esperados = {p["id_linha"] for p in products_chunk}
            ids_retornados = set(mapeamento.keys())
            ausentes = ids_esperados - ids_retornados
            if ausentes:
                logger.warning(
                    f"LLM não retornou classificação para {len(ausentes)} itens do lote: {sorted(ausentes)}"
                )

            logger.info(
                f"Lote processado: {len(mapeamento)}/{len(products_chunk)} itens classificados"
            )
            return mapeamento

        except google_exceptions.ResourceExhausted as e:
            # Erro 429 — Rate Limit
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))  # 10s, 20s, 40s
                logger.warning(
                    f"Rate Limit (429) no Gemini. Tentativa {attempt}/{max_retries}. "
                    f"Aguardando {delay}s antes de retry..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"Rate Limit persistente após {max_retries} tentativas. "
                    f"Lote de {len(products_chunk)} itens descartado."
                )
                return {}

        except google_exceptions.GoogleAPIError as e:
            logger.error(f"Erro da API do Gemini: {e}")
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.info(f"Retry em {delay}s...")
                await asyncio.sleep(delay)
            else:
                return {}

        except json.JSONDecodeError as e:
            logger.error(f"Resposta do Gemini não é JSON válido: {e}")
            return {}

        except Exception as e:
            logger.error(f"Erro inesperado ao classificar lote no Gemini: {e}", exc_info=True)
            return {}

    return {}  # Fallback (não deveria chegar aqui)
