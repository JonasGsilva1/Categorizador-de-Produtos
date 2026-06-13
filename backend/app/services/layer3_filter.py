"""
Camada 3 do Funil: Filtro de Segurança.

Aplica o limiar de confiança sobre a resposta do LLM mapeada do lote:
- Confiança >= 85: Aprovado (preenche grupo/subgrupo)
- Confiança < 85: Pendente de Revisão (deixa grupo/subgrupo em branco)
"""

import logging
from app.models import ProductInput, ProductOutput

logger = logging.getLogger(__name__)


def layer3_filter(
    product: ProductInput,
    llm_result_dict: dict,
) -> ProductOutput:
    """
    Aplica o filtro de segurança (>= 85) no dicionário de resposta do lote.
    """
    threshold = 85
    
    # Extrair os campos do dicionário
    grupo = llm_result_dict.get("grupo", "")
    subgrupo = llm_result_dict.get("subgrupo", "")
    grau_de_confianca = llm_result_dict.get("grau_de_confianca", 0)

    if grau_de_confianca >= threshold:
        logger.debug(
            f"LLM aprovado: confiança={grau_de_confianca}% "
            f"→ {grupo}/{subgrupo}"
        )
        return ProductOutput(
            row_index=product.row_index,
            descricao=product.descricao,
            ean=product.ean,
            ncm=product.ncm,
            grupo=grupo,
            subgrupo=subgrupo,
            origem="LLM",
            status="Aprovado",
        )
    else:
        logger.debug(
            f"LLM baixa confiança: {grau_de_confianca}% < {threshold}% "
            f"→ Pendente de Revisão"
        )
        return ProductOutput(
            row_index=product.row_index,
            descricao=product.descricao,
            ean=product.ean,
            ncm=product.ncm,
            grupo="",
            subgrupo="",
            origem="LLM (Baixa Confiança)",
            status="Pendente de Revisão",
        )
