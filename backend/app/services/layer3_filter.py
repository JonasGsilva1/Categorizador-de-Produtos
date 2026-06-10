"""
Camada 3 do Funil: Filtro de Segurança.

Aplica o limiar de confiança sobre a resposta do LLM:
- Confiança >= 95%: Aprovado (preenche grupo/subgrupo)
- Confiança < 95%: Pendente de Revisão (deixa grupo/subgrupo em branco)
"""

import logging
from app.config import get_settings
from app.models import ProductInput, ProductOutput, LLMClassification

logger = logging.getLogger(__name__)


def layer3_filter(
    product: ProductInput,
    llm_result: LLMClassification,
) -> ProductOutput:
    """
    Aplica o filtro de segurança baseado no grau de confiança do LLM.
    
    Args:
        product: Produto original
        llm_result: Resultado da classificação do LLM
    
    Returns:
        ProductOutput com status Aprovado ou Pendente de Revisão
    """
    settings = get_settings()
    threshold = settings.llm_confidence_threshold

    if llm_result.grau_de_confianca >= threshold:
        logger.debug(
            f"LLM aprovado: confiança={llm_result.grau_de_confianca}% "
            f"→ {llm_result.grupo}/{llm_result.subgrupo}"
        )
        return ProductOutput(
            row_index=product.row_index,
            descricao=product.descricao,
            ean=product.ean,
            ncm=product.ncm,
            grupo=llm_result.grupo,
            subgrupo=llm_result.subgrupo,
            origem="LLM",
            status="Aprovado",
        )
    else:
        logger.debug(
            f"LLM baixa confiança: {llm_result.grau_de_confianca}% < {threshold}% "
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
