"""
Cliente OpenRouter para categorização de produtos em lotes via LLM.

Estratégia de custo zero:
- Pool de modelos gratuitos com rotação automática em caso de rate-limit (429).
- Backoff adaptativo baseado no header Retry-After / metadata do OpenRouter.
- Controle de throttle global compartilhado entre sub-lotes.
"""

import logging
import json
import asyncio
import time
import httpx
from typing import Optional

from app.config import get_settings
from app.services.llm import ProdutoCategorizado, TAXONOMIA_PERMITIDA

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Pool de modelos gratuitos do OpenRouter (ordem de preferência)
# ──────────────────────────────────────────────────────────────────────────────
MODELOS_GRATUITOS: list[str] = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-235b-a22b:free",
    "deepseek/deepseek-r1-0528:free",
    "qwen/qwen3-30b-a3b:free",
    "google/gemma-3-27b-it:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "google/gemma-3-12b-it:free",
]

# Modelos que suportam response_format json_object
_MODELOS_COM_JSON_MODE = {"llama", "qwen", "openai", "deepseek", "mistral"}


def _suporta_json_mode(modelo: str) -> bool:
    """Verifica se o modelo suporta json_object response_format."""
    modelo_lower = modelo.lower()
    return any(tag in modelo_lower for tag in _MODELOS_COM_JSON_MODE)


# ──────────────────────────────────────────────────────────────────────────────
# Estado de throttle global — compartilhado entre chamadas sequenciais
# ──────────────────────────────────────────────────────────────────────────────
class ThrottleState:
    """Rastreia cooldowns por modelo para evitar martelar modelos limitados."""

    def __init__(self):
        # modelo -> timestamp (epoch) a partir do qual pode ser usado novamente
        self._cooldown_until: dict[str, float] = {}

    def marcar_rate_limit(self, modelo: str, segundos: int) -> None:
        self._cooldown_until[modelo] = time.monotonic() + segundos

    def disponivel(self, modelo: str) -> bool:
        limite = self._cooldown_until.get(modelo, 0)
        return time.monotonic() >= limite

    def segundos_restantes(self, modelo: str) -> float:
        limite = self._cooldown_until.get(modelo, 0)
        restante = limite - time.monotonic()
        return max(0, restante)


# Instância global de throttle (vive durante o processo)
_throttle = ThrottleState()


def _extrair_retry_after(response: httpx.Response) -> int:
    """
    Extrai o tempo de espera recomendado do OpenRouter.
    Tenta o header HTTP primeiro, depois o corpo JSON.
    Retorna um valor em segundos (mínimo 10, máximo 120).
    """
    # 1. Header HTTP Retry-After
    header_val = response.headers.get("Retry-After", "").strip()
    if header_val.isdigit():
        return max(10, min(120, int(header_val) + 3))

    # 2. Corpo JSON → error.metadata.retry_after_seconds
    try:
        err_json = response.json()
        if isinstance(err_json, dict) and "error" in err_json:
            meta = err_json["error"].get("metadata", {})
            retry_raw = meta.get("retry_after_seconds")
            if retry_raw is not None:
                return max(10, min(120, int(float(retry_raw)) + 3))
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # 3. Fallback conservador
    return 30


# ──────────────────────────────────────────────────────────────────────────────
# Função principal: classifica um lote com rotação de modelos
# ──────────────────────────────────────────────────────────────────────────────
async def classify_batch_openrouter(
    lote_produtos: list[dict],
) -> dict[int, ProdutoCategorizado]:
    """
    Classifica um lote de produtos via OpenRouter.

    Estratégia:
    1. Tenta o modelo configurado (settings.openrouter_model).
    2. Se 429, marca cooldown e tenta o próximo modelo gratuito disponível.
    3. Se todos estiverem em cooldown, espera o menor cooldown e retenta.
    4. Máximo de 8 tentativas totais (contando rotações de modelo).

    Retorna dicionário {id_linha: ProdutoCategorizado}.
    """
    settings = get_settings()
    api_key = settings.openrouter_api_key

    if not api_key:
        logger.error("OpenRouter API Key não configurada.")
        return {}

    # Montar a fila de modelos: o configurado primeiro, depois os fallbacks
    modelo_principal = settings.openrouter_model
    fila_modelos = [modelo_principal]
    for m in MODELOS_GRATUITOS:
        if m != modelo_principal:
            fila_modelos.append(m)

    # Construir prompt (independe do modelo)
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

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.frontend_url,
        "X-Title": "Categorizador de Produtos",
    }

    MAX_TENTATIVAS = 8  # tentativas totais (contando rotações de modelo)

    async with httpx.AsyncClient(timeout=180.0) as client:
        for tentativa in range(1, MAX_TENTATIVAS + 1):
            # ── Escolher modelo disponível ────────────────────────────────
            modelo_escolhido = None
            for m in fila_modelos:
                if _throttle.disponivel(m):
                    modelo_escolhido = m
                    break

            if modelo_escolhido is None:
                # Todos em cooldown — esperar o menor tempo restante
                esperas = {m: _throttle.segundos_restantes(m) for m in fila_modelos}
                modelo_menor_espera = min(esperas, key=esperas.get)
                tempo_espera = esperas[modelo_menor_espera]
                logger.warning(
                    f"Todos os modelos em cooldown. Aguardando {tempo_espera:.0f}s "
                    f"até {modelo_menor_espera} liberar..."
                )
                await asyncio.sleep(tempo_espera + 1)
                modelo_escolhido = modelo_menor_espera

            # ── Montar payload ────────────────────────────────────────────
            payload = {
                "model": modelo_escolhido,
                "messages": [
                    {"role": "system", "content": prompt_sistema},
                    {
                        "role": "user",
                        "content": f"PRODUTOS A CLASSIFICAR:\n{lista_itens_prompt}",
                    },
                ],
                "temperature": 0.1,
            }

            if _suporta_json_mode(modelo_escolhido):
                payload["response_format"] = {"type": "json_object"}

            # ── Enviar requisição ─────────────────────────────────────────
            try:
                logger.info(
                    f"[Tentativa {tentativa}/{MAX_TENTATIVAS}] Enviando {len(lote_produtos)} itens "
                    f"para modelo '{modelo_escolhido}'..."
                )
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                # ── Rate limit (429) → rotacionar modelo ─────────────────
                if response.status_code == 429:
                    retry_after = _extrair_retry_after(response)
                    _throttle.marcar_rate_limit(modelo_escolhido, retry_after)
                    logger.warning(
                        f"429 em '{modelo_escolhido}'. Cooldown de {retry_after}s. "
                        f"Tentativa {tentativa}/{MAX_TENTATIVAS}. Rotacionando modelo..."
                    )
                    # Pequena pausa antes de tentar próximo modelo (evita burst)
                    await asyncio.sleep(2)
                    continue

                # ── Outros erros HTTP ─────────────────────────────────────
                if response.status_code != 200:
                    logger.error(
                        f"OpenRouter respondeu {response.status_code} com modelo "
                        f"'{modelo_escolhido}': {response.text[:500]}"
                    )
                    if tentativa < MAX_TENTATIVAS:
                        await asyncio.sleep(5)
                        continue
                    return {}

                # ── Sucesso — parsear resposta ────────────────────────────
                data = response.json()

                if "choices" not in data or not data["choices"]:
                    logger.error(
                        f"Resposta sem 'choices' do modelo '{modelo_escolhido}': "
                        f"{json.dumps(data)[:400]}"
                    )
                    if tentativa < MAX_TENTATIVAS:
                        await asyncio.sleep(3)
                        continue
                    return {}

                content = data["choices"][0]["message"]["content"].strip()
                logger.debug(f"Resposta bruta ({modelo_escolhido}): {content[:300]}...")

                # Limpar markdown code fences se presentes
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

                # Modelos de raciocínio (DeepSeek-R1, etc.) podem incluir bloco <think>
                if "<think>" in content:
                    # Remover todo o bloco <think>...</think>
                    import re
                    content = re.sub(
                        r"<think>.*?</think>", "", content, flags=re.DOTALL
                    ).strip()

                try:
                    resultado_json = json.loads(content)
                    produtos_raw = resultado_json.get("produtos", [])
                    if not isinstance(produtos_raw, list):
                        if isinstance(resultado_json, list):
                            produtos_raw = resultado_json
                        else:
                            logger.error(
                                f"Chave 'produtos' não é lista. JSON: {content[:300]}"
                            )
                            produtos_raw = []
                except json.JSONDecodeError as erro_json:
                    logger.error(
                        f"JSON inválido do modelo '{modelo_escolhido}': {erro_json}. "
                        f"Conteúdo: {content[:300]}"
                    )
                    if tentativa < MAX_TENTATIVAS:
                        # Tentar outro modelo (talvez um com JSON mode melhor)
                        _throttle.marcar_rate_limit(modelo_escolhido, 60)
                        await asyncio.sleep(2)
                        continue
                    return {}

                # ── Montar mapeamento validado ────────────────────────────
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
                        else:
                            logger.warning(
                                f"Item {id_linha} ignorado (grupo/subgrupo vazio): {item}"
                            )
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Falha ao interpretar item {item}: {e}")

                logger.info(
                    f"✓ Lote OK via '{modelo_escolhido}': "
                    f"{len(mapeamento)}/{len(lote_produtos)} classificados."
                )
                return mapeamento

            except httpx.TimeoutException:
                logger.error(
                    f"Timeout no modelo '{modelo_escolhido}' (tentativa {tentativa}). "
                    f"Marcando cooldown de 30s."
                )
                _throttle.marcar_rate_limit(modelo_escolhido, 30)
                if tentativa < MAX_TENTATIVAS:
                    await asyncio.sleep(2)
                    continue
                return {}

            except httpx.HTTPError as erro_http:
                logger.error(
                    f"Erro HTTP ({modelo_escolhido}): {erro_http}. "
                    f"Resposta: {getattr(erro_http, 'response', 'N/A')}"
                )
                if tentativa < MAX_TENTATIVAS:
                    await asyncio.sleep(5)
                    continue
                return {}

            except Exception as e:
                logger.error(
                    f"Erro inesperado ({modelo_escolhido}): {e}", exc_info=True
                )
                return {}

    logger.error("Esgotadas todas as tentativas para o lote.")
    return {}
