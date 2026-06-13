"""
Cliente Google Gemini para classificação de produtos via LLM com Structured Outputs.
Usa gemini-1.5-flash com TypedDict Schema para precisão cirúrgica de JSON.
"""

import logging
import json
from typing import TypedDict
from google import genai
from app.config import get_settings
from app.models import LLMClassification

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    """Retorna o cliente Gemini (singleton)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


# 1. Injeção de Taxonomia (Cardápio Fixo)
TAXONOMIA_PERMITIDA = [
    "Alimentos > Mercearia",
    "Alimentos > Perecíveis",
    "Bebidas > Alcoólicas",
    "Bebidas > Não Alcoólicas",
    "Limpeza > Limpeza da Casa",
    "Limpeza > Lavanderia",
    "Higiene > Cuidados Pessoais",
    "Higiene > Cabelos",
    "Pets > Cães e Gatos",
    "Bazar > Utilidades Domésticas"
]

# 2. Configuração Exata da API do Gemini (TypedDict)
class GeminiClassificationSchema(TypedDict):
    grupo: str
    subgrupo: str
    grau_de_confianca: int


# 3. O Novo Prompt do Gemini
SYSTEM_PROMPT = f"""Você é um classificador determinístico de dados de varejo.
REGRA 1: A Descrição é a ÚNICA fonte da verdade. Ignore o NCM se for industrial ou divergente.
REGRA 2: Você DEVE classificar escolhendo estritamente entre estas opções: {', '.join(TAXONOMIA_PERMITIDA)}. Não invente categorias. Se o produto for óbvio e estiver na lista, atribua confiança entre 85 e 100."""

async def classify_product(descricao: str, ncm: str = "") -> LLMClassification:
    """
    Classifica um produto usando Gemini com parâmetros exatos.
    """
    client = _get_client()

    user_message = f"Produto: {descricao}"
    if ncm:
        user_message += f" | NCM: {ncm}"

    try:
        response = await client.aio.models.generate_content(
            model="gemini-1.5-flash",
            contents=[
                {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_message}"}]}
            ],
            config={
                "response_mime_type": "application/json",
                "response_schema": GeminiClassificationSchema,
                "temperature": 0.1, # Zerando a criatividade
            }
        )

        data = json.loads(response.text)
        return LLMClassification(
            grupo=data.get("grupo", ""),
            subgrupo=data.get("subgrupo", ""),
            grau_de_confianca=int(data.get("grau_de_confianca", 0)),
        )

    except Exception as e:
        logger.error(f"Erro ao classificar produto '{descricao}': {e}")
        return LLMClassification(grupo="", subgrupo="", grau_de_confianca=0)
