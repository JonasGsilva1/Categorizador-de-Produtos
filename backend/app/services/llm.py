"""
Cliente Google Gemini para classificação de produtos via LLM com Structured Outputs.
Usa gemini-1.5-flash com Pydantic Schema.
"""

import logging
from google import genai
from pydantic import BaseModel, Field
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

class GeminiClassificationSchema(BaseModel):
    grupo: str = Field(description="Grupo/categoria principal do produto")
    subgrupo: str = Field(description="Subcategoria mais específica do produto")
    grau_de_confianca: int = Field(description="Grau de confiança na classificação, de 0 a 100")

SYSTEM_PROMPT = """Você é um especialista em categorização de produtos de varejo e supermercado brasileiro.
A [Descrição] é a única fonte da verdade; ignore o [NCM] se for divergente ou industrial. Para produtos óbvios (utilidades, alimentos), o 'grau_de_confianca' deve ser obrigatoriamente > 95.
Sua tarefa é classificar produtos em Grupo e Subgrupo com base na descrição fornecida."""

async def classify_product(descricao: str, ncm: str = "") -> LLMClassification:
    """
    Classifica um produto usando Gemini com Structured Outputs.
    """
    settings = get_settings()
    client = _get_client()

    user_message = f"Descrição do produto: {descricao}"
    if ncm:
        user_message += f"\nCódigo NCM: {ncm}"

    try:
        response = await client.aio.models.generate_content(
            model="gemini-1.5-flash",
            contents=[
                {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_message}"}]}
            ],
            config={
                "response_mime_type": "application/json",
                "response_schema": GeminiClassificationSchema,
                "temperature": 0.1,
            }
        )

        if response.parsed:
            parsed = response.parsed
            return LLMClassification(
                grupo=parsed.grupo,
                subgrupo=parsed.subgrupo,
                grau_de_confianca=max(0, min(100, parsed.grau_de_confianca)),
            )
        else:
            import json
            data = json.loads(response.text)
            return LLMClassification(
                grupo=data.get("grupo", ""),
                subgrupo=data.get("subgrupo", ""),
                grau_de_confianca=data.get("grau_de_confianca", 0),
            )

    except Exception as e:
        logger.error(f"Erro ao classificar produto '{descricao}': {e}")
        return LLMClassification(grupo="", subgrupo="", grau_de_confianca=0)
