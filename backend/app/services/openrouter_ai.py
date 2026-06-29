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
# Atualizado em 2026-06-29 a partir de https://openrouter.ai/api/v1/models
# ──────────────────────────────────────────────────────────────────────────────
MODELOS_GRATUITOS: list[str] = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-coder:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "openai/gpt-oss-120b:free",
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
]

# Modelos que suportam response_format json_object
_MODELOS_COM_JSON_MODE = {"llama", "qwen", "openai", "deepseek", "mistral", "gemma", "nemotron", "hermes"}


def _suporta_json_mode(modelo: str) -> bool:
    """Verifica se o modelo suporta json_object response_format."""
    modelo_lower = modelo.lower()
    return any(tag in modelo_lower for tag in _MODELOS_COM_JSON_MODE)


# ──────────────────────────────────────────────────────────────────────────────
# Estado de throttle global — compartilhado entre chamadas sequenciais
# ──────────────────────────────────────────────────────────────────────────────
class ThrottleState:
    """Rastreia cooldowns e banimentos por modelo."""

    def __init__(self):
        # modelo -> timestamp (epoch) a partir do qual pode ser usado novamente
        self._cooldown_until: dict[str, float] = {}
        # modelos permanentemente banidos (404 = não existe mais como free)
        self._banidos: set[str] = set()

    def marcar_rate_limit(self, modelo: str, segundos: int) -> None:
        self._cooldown_until[modelo] = time.monotonic() + segundos

    def banir_permanente(self, modelo: str) -> None:
        """Marca modelo como permanentemente indisponível (ex: 404)."""
        self._banidos.add(modelo)
        logger.info(f"Modelo '{modelo}' banido permanentemente desta sessão.")

    def disponivel(self, modelo: str) -> bool:
        if modelo in self._banidos:
            return False
        limite = self._cooldown_until.get(modelo, 0)
        return time.monotonic() >= limite

    def segundos_restantes(self, modelo: str) -> float:
        if modelo in self._banidos:
            return float("inf")
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


def _recuperar_json_truncado(content: str) -> list[dict]:
    """
    Tenta recuperar itens válidos de um JSON truncado.

    Modelos free frequentemente cortam a resposta no meio do JSON quando
    atingem o limite de tokens. Esta função extrai todos os objetos de
    produto completos que aparecem antes do ponto de corte.

    Retorna lista de dicts (pode ser vazia se nada for recuperável).
    """
    import re

    # Estratégia 1: tentar fechar o JSON truncado manualmente
    # Se o JSON termina no meio de um objeto dentro do array "produtos",
    # removemos o último objeto incompleto e fechamos os colchetes/chaves.
    for suffix in ["}]}", "]}",  "}]}}"]:
        # Encontrar o último objeto completo (termina com })
        # e tentar fechar o array/objeto raiz
        last_complete = content.rfind("},")
        if last_complete > 0:
            tentativa = content[:last_complete + 1] + suffix
            try:
                parsed = json.loads(tentativa)
                produtos = parsed.get("produtos", [])
                if isinstance(produtos, list) and len(produtos) > 0:
                    return produtos
                if isinstance(parsed, list) and len(parsed) > 0:
                    return parsed
            except json.JSONDecodeError:
                continue

    # Estratégia 2: extrair objetos individuais via regex
    # Captura cada bloco { ... } que contém id_linha
    pattern = re.compile(
        r'\{\s*"id_linha"\s*:\s*\d+\s*,\s*'
        r'"grupo"\s*:\s*"[^"]*"\s*,\s*'
        r'"subgrupo"\s*:\s*"[^"]*"\s*,\s*'
        r'"grau_de_confianca"\s*:\s*\d+\s*\}',
        re.DOTALL,
    )
    matches = pattern.findall(content)
    if matches:
        recovered = []
        for m in matches:
            try:
                recovered.append(json.loads(m))
            except json.JSONDecodeError:
                continue
        return recovered

    return []


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

    # Filtrar modelos já banidos de sessões anteriores (se o processo ainda estiver rodando)
    fila_modelos = [m for m in fila_modelos if _throttle.disponivel(m) or m not in _throttle._banidos]

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

    MAX_TENTATIVAS = 12  # tentativas reais (não conta 404 de modelos inválidos)

    async with httpx.AsyncClient(timeout=180.0) as client:
        tentativa = 0
        while tentativa < MAX_TENTATIVAS:
            tentativa += 1

            # ── Escolher modelo disponível ────────────────────────────────
            modelo_escolhido = None
            for m in fila_modelos:
                if _throttle.disponivel(m):
                    modelo_escolhido = m
                    break

            if modelo_escolhido is None:
                # Filtrar modelos banidos antes de calcular esperas
                modelos_vivos = [m for m in fila_modelos if m not in _throttle._banidos]
                if not modelos_vivos:
                    logger.error("Todos os modelos foram banidos (404). Nenhum modelo free disponível.")
                    return {}

                esperas = {m: _throttle.segundos_restantes(m) for m in modelos_vivos}
                modelo_menor_espera = min(esperas, key=esperas.get)
                tempo_espera = esperas[modelo_menor_espera]
                logger.warning(
                    f"Todos os modelos em cooldown. Aguardando {tempo_espera:.0f}s "
                    f"até '{modelo_menor_espera}' liberar..."
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

                # ── Modelo não existe / não é free (404) → banir sem gastar tentativa
                if response.status_code == 404:
                    logger.warning(
                        f"Modelo '{modelo_escolhido}' não disponível (404). "
                        f"Removendo do pool e tentando próximo..."
                    )
                    _throttle.banir_permanente(modelo_escolhido)
                    tentativa -= 1  # NÃO contar como tentativa real
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
                try:
                    data = response.json()
                except json.JSONDecodeError as err:
                    logger.error(f"Erro inesperado ({modelo_escolhido}): Resposta não é JSON válido - {err}")
                    if tentativa < MAX_TENTATIVAS:
                        await asyncio.sleep(2)
                        continue
                    return {}

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
                    # ── Recuperação de JSON truncado ──────────────────────
                    # Modelos free frequentemente cortam a resposta no meio
                    # do JSON por limite de tokens. Tentamos salvar os itens
                    # completos que já foram retornados antes do corte.
                    produtos_raw = _recuperar_json_truncado(content)
                    if produtos_raw:
                        logger.warning(
                            f"JSON truncado de '{modelo_escolhido}'. "
                            f"Recuperados {len(produtos_raw)} itens do fragmento."
                        )
                    else:
                        logger.error(
                            f"JSON inválido de '{modelo_escolhido}' e sem itens "
                            f"recuperáveis: {erro_json}. Conteúdo: {content[:300]}"
                        )
                        if tentativa < MAX_TENTATIVAS:
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
