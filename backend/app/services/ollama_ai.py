"""
Serviço de categorização via Ollama local (compatível com API OpenAI).
"""

import logging
import json
import httpx
from typing import Optional
from app.config import get_settings
from app.services.llm import ProdutoCategorizado, TAXONOMIA_PERMITIDA

logger = logging.getLogger(__name__)

async def classify_batch_ollama(lote_produtos: list[dict]) -> dict[int, ProdutoCategorizado]:
    """
    Classifica um lote de produtos via Ollama local.
    """
    settings = get_settings()
    
    # Construir prompt
    itens_texto = []
    for p in lote_produtos:
        texto = f"ID_LINHA: {p['id_linha']} | Descrição: {p['descricao']}"
        if p.get("ncm"):
            texto += f" | NCM: {p['ncm']}"
        itens_texto.append(texto)

    lista_itens_prompt = "\n".join(itens_texto)

    prompt_sistema = f"""Você é um classificador determinístico de dados de varejo.
Abaixo está uma lista de produtos para categorizar em lote.

REGRA 1: A Descrição é a ÚNICA fonte da verdade. Ignore o NCM se for industrial ou divergente.
REGRA 2: Você DEVE classificar escolhendo estritamente entre estas opções:\n{TAXONOMIA_PERMITIDA}
REGRA 3: Responda APENAS com um objeto JSON válido, contendo uma chave "produtos" que é uma lista de objetos.
Cada objeto deve ter:
- "id_linha": número inteiro (deve ser exatamente o mesmo fornecido)
- "grupo": string exata de um dos grupos permitidos
- "subgrupo": string exata de um dos subgrupos permitidos
- "grau_de_confianca": inteiro de 0 a 100

Não inclua formatação markdown (```json) ou texto extra, apenas o JSON puro."""

    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {
                "role": "user",
                "content": f"PRODUTOS A CLASSIFICAR:\n{lista_itens_prompt}",
            },
        ],
        "temperature": 0.1,
    }

    # Modelos Qwen2.5 e Llama 3.1 locais suportam json_object
    payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            logger.info(f"Enviando {len(lote_produtos)} itens para Ollama local ({settings.ollama_model})...")
            
            response = await client.post(
                settings.ollama_base_url,
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            
            if "choices" not in data or not data["choices"]:
                logger.error(f"Resposta vazia do Ollama: {data}")
                return {}

            content = data["choices"][0]["message"]["content"].strip()
            
            # Limpar formatações comuns de markdown
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            try:
                resultado_json = json.loads(content)
                produtos_raw = resultado_json.get("produtos", [])
                if not isinstance(produtos_raw, list):
                    if isinstance(resultado_json, list):
                        produtos_raw = resultado_json
                    else:
                        produtos_raw = []
            except json.JSONDecodeError as err:
                logger.error(f"Ollama não retornou JSON válido: {err}. Resposta: {content[:300]}")
                return {}

            mapeamento: dict[int, ProdutoCategorizado] = {}
            for item in produtos_raw:
                try:
                    id_linha = item.get("id_linha")
                    if id_linha is None:
                        continue
                    id_linha = int(id_linha)

                    grupo = str(item.get("grupo", "")).strip()
                    subgrupo = str(item.get("subgrupo", "")).strip()
                    confianca = int(item.get("grau_de_confianca", 0))

                    if grupo and subgrupo:
                        mapeamento[id_linha] = ProdutoCategorizado(
                            id_linha=id_linha,
                            grupo=grupo,
                            subgrupo=subgrupo,
                            grau_de_confianca=min(100, max(0, confianca)),
                        )
                except (ValueError, TypeError) as e:
                    logger.warning(f"Falha ao interpretar item: {e}")

            logger.info(f"✓ {len(mapeamento)}/{len(lote_produtos)} classificados localmente.")
            return mapeamento

        except httpx.TimeoutException:
            logger.error("Timeout na API local do Ollama.")
            return {}
        except Exception as e:
            logger.error(f"Erro inesperado no Ollama: {e}", exc_info=True)
            return {}
