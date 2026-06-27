"""
Cliente OpenRouter para categorização de produtos em lotes via LLM.
"""

import logging
import json
import asyncio
import httpx
from typing import List, Optional
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.llm import ProdutoCategorizado, TAXONOMIA_PERMITIDA

logger = logging.getLogger(__name__)

async def classify_batch_openrouter(lote_produtos: list[dict]) -> dict[int, ProdutoCategorizado]:
    """
    Classifica um lote de produtos enviando-os de uma vez à API do OpenRouter.
    `lote_produtos` deve ser uma lista de dicionários contendo id_linha, descricao (e ncm opcional).
    Retorna um dicionário mapeando o id_linha para o seu respectivo ProdutoCategorizado.
    """
    settings = get_settings()
    api_key = settings.openrouter_api_key
    model = settings.openrouter_model

    if not api_key:
        logger.error("OpenRouter API Key não configurada.")
        return {}

    # Construir o payload textual dos itens do lote
    itens_texto = []
    for p in lote_produtos:
        texto = f"ID_LINHA: {p['id_linha']} | Descrição: {p['descricao']}"
        if p.get('ncm'):
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

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.frontend_url,
        "X-Title": "Categorizador de Produtos"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": f"PRODUTOS A CLASSIFICAR:\n{lista_itens_prompt}"}
        ],
        "temperature": 0.1,
    }

    # Tratamento específico para modelos que suportam JSON mode explicitamente no OpenRouter
    if "llama" in model.lower() or "openai" in model.lower():
         payload["response_format"] = {"type": "json_object"}

    max_tentativas = 3
    atraso_base = 5

    async with httpx.AsyncClient(timeout=60.0) as client:
        for tentativa in range(1, max_tentativas + 1):
            try:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 429:
                    atraso = atraso_base * tentativa
                    logger.warning(f"Rate limit OpenRouter. Tentativa {tentativa}/{max_tentativas}. Aguardando {atraso}s...")
                    await asyncio.sleep(atraso)
                    continue
                    
                response.raise_for_status()
                data = response.json()
                
                content = data["choices"][0]["message"]["content"].strip()
                
                # Remover block markdown de código se a IA insistir em adicionar
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
                        # Caso a IA retorne um array direto
                        if isinstance(resultado_json, list):
                            produtos_raw = resultado_json
                        else:
                            logger.error("A chave 'produtos' não é uma lista ou não foi encontrada.")
                            produtos_raw = []
                except json.JSONDecodeError as erro_json:
                    logger.error(f"Resposta não é JSON válido: {erro_json}. Conteúdo: {content[:200]}")
                    if tentativa < max_tentativas:
                        await asyncio.sleep(atraso_base)
                        continue
                    return {}

                # Montar mapeamento
                mapeamento: dict[int, ProdutoCategorizado] = {}
                for item in produtos_raw:
                    try:
                        id_linha = item.get("id_linha")
                        if id_linha is None: continue
                        id_linha = int(id_linha)
                        
                        grupo = str(item.get("grupo", "")).strip()
                        subgrupo = str(item.get("subgrupo", "")).strip()
                        confianca = int(item.get("grau_de_confianca", 0))
                        
                        if grupo and subgrupo:
                            mapeamento[id_linha] = ProdutoCategorizado(
                                id_linha=id_linha,
                                grupo=grupo,
                                subgrupo=subgrupo,
                                grau_de_confianca=min(100, max(0, confianca))
                            )
                    except (ValueError, TypeError):
                        pass

                logger.info(f"OpenRouter: Lote processado. {len(mapeamento)}/{len(lote_produtos)} classificados.")
                return mapeamento

            except httpx.HTTPError as erro_http:
                logger.error(f"Erro HTTP OpenRouter: {erro_http}")
                if tentativa < max_tentativas:
                    await asyncio.sleep(atraso_base * tentativa)
                else:
                    return {}
            except Exception as e:
                logger.error(f"Erro inesperado na chamada OpenRouter: {e}")
                return {}

    return {}
