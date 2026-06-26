"""
Camada 3 do Funil: Filtro de Segurança.

Aplica o limiar de confiança sobre a resposta do LLM mapeada do lote:
- Confiança >= 85: Aprovado (preenche grupo/subgrupo)
- Confiança < 85: Pendente de Revisão (deixa grupo/subgrupo em branco)
"""

import logging
from app.models import ProdutoEntrada, ProdutoSaida

logger = logging.getLogger(__name__)


def layer3_filter(
    produto: ProdutoEntrada,
    resultado_llm: dict | object,
) -> ProdutoSaida:
    """
    Aplica o filtro de segurança (>= 85) no resultado do lote.
    Aceita tanto dicts quanto objetos Pydantic (ProdutoCategorizado).
    """
    limite = 85
    
    # Suporte a dict e Pydantic model
    def _obter(objeto, chave, padrao=None):
        if isinstance(objeto, dict):
            return objeto.get(chave, padrao)
        return getattr(objeto, chave, padrao)
    
    # Extrair os campos
    grupo = _obter(resultado_llm, "grupo", "")
    subgrupo = _obter(resultado_llm, "subgrupo", "")
    grau_de_confianca = _obter(resultado_llm, "grau_de_confianca", 0)

    if grau_de_confianca >= limite:
        logger.debug(
            f"LLM aprovado: confiança={grau_de_confianca}% "
            f"→ {grupo}/{subgrupo}"
        )
        return ProdutoSaida(
            row_index=produto.row_index,
            descricao=produto.descricao,
            ean=produto.ean,
            ncm=produto.ncm,
            grupo=grupo,
            subgrupo=subgrupo,
            origem="LLM",
            status="Aprovado",
        )
    else:
        logger.debug(
            f"LLM baixa confiança: {grau_de_confianca}% < {limite}% "
            f"→ Pendente de Revisão"
        )
        return ProdutoSaida(
            row_index=produto.row_index,
            descricao=produto.descricao,
            ean=produto.ean,
            ncm=produto.ncm,
            grupo="",
            subgrupo="",
            origem="LLM (Baixa Confiança)",
            status="Pendente de Revisão",
        )
