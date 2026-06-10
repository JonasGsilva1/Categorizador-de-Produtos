"""
Cliente Google Gemini para classificação de produtos via LLM com Structured Outputs.
Usa gemini-2.5-flash com Pydantic Schema.
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

# Schema Pydantic para o Gemini (Structured Output)
class GeminiClassificationSchema(BaseModel):
    grupo: str = Field(description="Grupo/categoria principal do produto (ex: Alimentos, Bebidas, Limpeza, Higiene, Pets, Bazar)")
    subgrupo: str = Field(description="Subcategoria mais específica do produto (ex: Biscoitos, Refrigerantes, Detergentes)")
    grau_de_confianca: int = Field(description="Grau de confiança na classificação, de 0 a 100 (percentual)")

SYSTEM_PROMPT = """Você é um especialista em categorização de produtos de varejo e supermercado brasileiro.
Sua tarefa é classificar produtos em Grupo e Subgrupo com base na descrição fornecida.
Regras:
1. O "grupo" deve ser uma categoria ampla.
2. O "subgrupo" deve ser uma subcategoria específica.
3. O "grau_de_confianca" reflete o quão certo você está (0-100).
4. Use terminologia padrão do varejo brasileiro.
5. Considere o código NCM fornecido como contexto adicional."""

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
            model=settings.llm_model,
            contents=[
                {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_message}"}]}
            ],
            config={
                "response_mime_type": "application/json",
                "response_schema": GeminiClassificationSchema,
                "temperature": 0.1,
            }
        )

        # O SDK moderno suporta o parsing automático quando response_schema é fornecido
        if response.parsed:
            parsed = response.parsed
            return LLMClassification(
                grupo=parsed.grupo,
                subgrupo=parsed.subgrupo,
                grau_de_confianca=max(0, min(100, parsed.grau_de_confianca)),
            )
        else:
            # Fallback se response.parsed falhar (JSON em response.text)
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
