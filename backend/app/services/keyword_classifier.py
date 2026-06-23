"""
Camada 3 do Funil: Classificador determinístico por palavras-chave.

Arquitetura de pontuação com vetos contextuais:

  1. Para cada regra que casa com a descrição, acumula um score (bigramas valem
     mais que unigramas — mais específicos).
  2. Antes de retornar o candidato com maior score, verifica se algum VETO
     contextual bloqueia aquele grupo/subgrupo para a descrição atual.
  3. Vetos garantem que "concha de macarrão" não vá para Alimentos porque
     "concha" é um utensílio que cancela o match de "macarrao".

Isso resolve o problema de bag-of-words onde tokens de conteúdo
(macarrão, frango, tomate) sobrepõem tokens de objeto (concha, forma, molho).
"""

import re
import unicodedata
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

@dataclass
class Rule:
    """Uma regra de classificação com peso e vetos opcionais."""
    grupo: str
    subgrupo: str
    score: int = 1          # unigramas=1, bigramas=2, trigramas=3
    veto_if: set[str] = field(default_factory=set)
    # Se qualquer termo de veto_if estiver na descrição normalizada,
    # esta regra é ignorada mesmo que o termo principal case.


# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Remove acentos, lowercase, substitui pontuação por espaço."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Vetos globais — tokens que indicam "objeto físico" e bloqueiam Alimentos/Frios
# ---------------------------------------------------------------------------

# Qualquer regra de Alimentos/Frios que encontrar esses tokens na descrição
# será cancelada, pois o produto é claramente um utensílio ou recipiente.
_UTENSILIO_TOKENS = {
    "concha", "espatula", "colher", "garfo", "faca", "talher",
    "panela", "frigideira", "forma", "assadeira", "escorredor",
    "ralador", "descascador", "abridor", "saca-rolhas", "sacador",
    "tabua", "tabuleiro", "espremedor", "peneira", "coador",
    "pote", "vasilha", "recipiente", "jarra", "garrafa", "squeeze",
    "copo", "taca", "caneca", "xicara", "bule", "chaleira",
    "molheira", "galheteiro", "porta", "suporte",
    "pegador", "pinça", "pinca", "servidor", "servico",
    "jogo", "kit", "conjunto", "utensilio", "utensilios",
}

# Tokens que indicam "embalagem comercial de alimento" — fortalecem Alimentos
_ALIMENTO_CONTEXTO = {
    "pacote", "kg", "g", "gramas", "litro", "ml", "lata", "caixa",
    "sachê", "sache", "unidade", "pct", "500g", "1kg", "250g",
}


# ---------------------------------------------------------------------------
# Dicionário principal — KEYWORD_RULES
# Formato: termo → Rule(grupo, subgrupo, score, veto_if)
# Bigramas definidos ANTES de unigramas para ganhar em caso de empate de score.
# ---------------------------------------------------------------------------

KEYWORD_RULES: dict[str, Rule] = {

    # ═══════════════════════════════════════════════════════════════════════
    # BEBIDAS
    # ═══════════════════════════════════════════════════════════════════════

    # Vinhos
    "vinho tinto":      Rule("Bebidas", "Vinhos", 2),
    "vinho branco":     Rule("Bebidas", "Vinhos", 2),
    "vinho rose":       Rule("Bebidas", "Vinhos", 2),
    "vinho verde":      Rule("Bebidas", "Vinhos", 2),
    "vinho suave":      Rule("Bebidas", "Vinhos", 2),
    "espumante":        Rule("Bebidas", "Vinhos", 1),
    "vinho":            Rule("Bebidas", "Vinhos", 1),

    # Cervejas
    "cerveja":          Rule("Bebidas", "Cervejas", 1),
    "heineken":         Rule("Bebidas", "Cervejas", 1),
    "skol":             Rule("Bebidas", "Cervejas", 1),
    "brahma":           Rule("Bebidas", "Cervejas", 1),
    "itaipava":         Rule("Bebidas", "Cervejas", 1),
    "budweiser":        Rule("Bebidas", "Cervejas", 1),
    "amstel":           Rule("Bebidas", "Cervejas", 1),
    "stella artois":    Rule("Bebidas", "Cervejas", 2),
    "petra":            Rule("Bebidas", "Cervejas", 1),

    # Refrigerantes
    "refrigerante":     Rule("Bebidas", "Refrigerantes", 1),
    "coca cola":        Rule("Bebidas", "Refrigerantes", 2),
    "pepsi":            Rule("Bebidas", "Refrigerantes", 1),
    "guarana":          Rule("Bebidas", "Refrigerantes", 1),
    "fanta":            Rule("Bebidas", "Refrigerantes", 1),
    "sprite":           Rule("Bebidas", "Refrigerantes", 1),
    "schweppes":        Rule("Bebidas", "Refrigerantes", 1),

    # Sucos e Chás
    "suco de":          Rule("Bebidas", "Sucos e Chás", 2),
    "nectar de":        Rule("Bebidas", "Sucos e Chás", 2),
    "cha gelado":       Rule("Bebidas", "Sucos e Chás", 2),
    "cha verde":        Rule("Bebidas", "Sucos e Chás", 2),
    "cha preto":        Rule("Bebidas", "Sucos e Chás", 2),
    "powerade":         Rule("Bebidas", "Sucos e Chás", 1),
    "gatorade":         Rule("Bebidas", "Sucos e Chás", 1),
    "suco":             Rule("Bebidas", "Sucos e Chás", 1),
    "nectar":           Rule("Bebidas", "Sucos e Chás", 1),
    "isotônico":        Rule("Bebidas", "Sucos e Chás", 1),
    "isotonico":        Rule("Bebidas", "Sucos e Chás", 1),

    # Água
    "agua mineral":     Rule("Bebidas", "Água", 2),
    "agua com gas":     Rule("Bebidas", "Água", 3),
    "agua sem gas":     Rule("Bebidas", "Água", 3),
    "agua":             Rule("Bebidas", "Água", 1),

    # Destilados e Ice
    "whisky":           Rule("Bebidas", "Destilados e Ice", 1),
    "whiskey":          Rule("Bebidas", "Destilados e Ice", 1),
    "vodka":            Rule("Bebidas", "Destilados e Ice", 1),
    "cachaca":          Rule("Bebidas", "Destilados e Ice", 1),
    "rum":              Rule("Bebidas", "Destilados e Ice", 1),
    "gin":              Rule("Bebidas", "Destilados e Ice", 1),
    "tequila":          Rule("Bebidas", "Destilados e Ice", 1),
    "licor":            Rule("Bebidas", "Destilados e Ice", 1),
    "conhaque":         Rule("Bebidas", "Destilados e Ice", 1),
    "destilado":        Rule("Bebidas", "Destilados e Ice", 1),

    # Energéticos
    "energetico":       Rule("Bebidas", "Energéticos", 1),
    "red bull":         Rule("Bebidas", "Energéticos", 2),
    "monster":          Rule("Bebidas", "Energéticos", 1),
    "tnt energy":       Rule("Bebidas", "Energéticos", 2),
    "burn":             Rule("Bebidas", "Energéticos", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # LIMPEZA
    # ═══════════════════════════════════════════════════════════════════════

    "vassoura":             Rule("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 1),
    "rodo":                 Rule("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 1),
    "esponja de limpeza":   Rule("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 2),
    "balde":                Rule("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 1),
    "pano de chao":         Rule("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 2),
    "flanela":              Rule("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 1),
    "mop":                  Rule("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 1),
    "esponja":              Rule("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 1),
    "luva de borracha":     Rule("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 2),
    "detergente":           Rule("Limpeza", "Produtos Químicos", 1),
    "desinfetante":         Rule("Limpeza", "Produtos Químicos", 1),
    "alvejante":            Rule("Limpeza", "Produtos Químicos", 1),
    "sabao em po":          Rule("Limpeza", "Produtos Químicos", 2),
    "sabao liquido":        Rule("Limpeza", "Produtos Químicos", 2),
    "amaciante":            Rule("Limpeza", "Produtos Químicos", 1),
    "multiuso":             Rule("Limpeza", "Produtos Químicos", 1),
    "limpa vidro":          Rule("Limpeza", "Produtos Químicos", 2),
    "ajax":                 Rule("Limpeza", "Produtos Químicos", 1),
    "omo":                  Rule("Limpeza", "Produtos Químicos", 1),
    "ariel":                Rule("Limpeza", "Produtos Químicos", 1),
    "tira mofo":            Rule("Limpeza", "Produtos Químicos", 2),
    "cloro":                Rule("Limpeza", "Produtos Químicos", 1),
    "hipoclorito":          Rule("Limpeza", "Produtos Químicos", 1),
    "lixeira":              Rule("Limpeza", "Lixeiras e Cestos", 1),
    "cesto de lixo":        Rule("Limpeza", "Lixeiras e Cestos", 2),
    "cesto":                Rule("Limpeza", "Lixeiras e Cestos", 1),
    "organizador":          Rule("Limpeza", "Organização", 1),
    "organizador de cozinha": Rule("Limpeza", "Organização", 3),
    "organizador plastico": Rule("Limpeza", "Organização", 2),

    # ═══════════════════════════════════════════════════════════════════════
    # ALIMENTOS — todos com veto_if=_UTENSILIO_TOKENS
    # ═══════════════════════════════════════════════════════════════════════

    # Biscoitos e Salgadinhos
    "biscoito":         Rule("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _UTENSILIO_TOKENS),
    "bolacha":          Rule("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _UTENSILIO_TOKENS),
    "salgadinho":       Rule("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _UTENSILIO_TOKENS),
    "chips":            Rule("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _UTENSILIO_TOKENS),
    "amendoim":         Rule("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _UTENSILIO_TOKENS),
    "batatinha":        Rule("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _UTENSILIO_TOKENS),
    "snack":            Rule("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _UTENSILIO_TOKENS),
    "torrada":          Rule("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _UTENSILIO_TOKENS),

    # Doces e Sobremesas
    "chocolate":        Rule("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _UTENSILIO_TOKENS),
    "bala":             Rule("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _UTENSILIO_TOKENS),
    "chiclete":         Rule("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _UTENSILIO_TOKENS),
    "pirulito":         Rule("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _UTENSILIO_TOKENS),
    "bombom":           Rule("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _UTENSILIO_TOKENS),
    "geleia":           Rule("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _UTENSILIO_TOKENS),
    "mel":              Rule("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _UTENSILIO_TOKENS),
    "doce de leite":    Rule("Alimentos (Mercearia)", "Doces e Sobremesas", 2, _UTENSILIO_TOKENS),
    "achocolatado":     Rule("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _UTENSILIO_TOKENS),

    # Conservas e Molhos — veto especial: "molheira" é utensílio
    "extrato de tomate": Rule("Alimentos (Mercearia)", "Conservas e Molhos", 3, _UTENSILIO_TOKENS),
    "molho de tomate":  Rule("Alimentos (Mercearia)", "Conservas e Molhos", 2, _UTENSILIO_TOKENS),
    "milho em lata":    Rule("Alimentos (Mercearia)", "Conservas e Molhos", 2, _UTENSILIO_TOKENS),
    "ervilha em lata":  Rule("Alimentos (Mercearia)", "Conservas e Molhos", 2, _UTENSILIO_TOKENS),
    "creme de leite":   Rule("Alimentos (Mercearia)", "Conservas e Molhos", 2, _UTENSILIO_TOKENS),
    "leite condensado": Rule("Alimentos (Mercearia)", "Conservas e Molhos", 2, _UTENSILIO_TOKENS),
    "atum":             Rule("Alimentos (Mercearia)", "Conservas e Molhos", 1, _UTENSILIO_TOKENS),
    "sardinha":         Rule("Alimentos (Mercearia)", "Conservas e Molhos", 1, _UTENSILIO_TOKENS),
    "conserva":         Rule("Alimentos (Mercearia)", "Conservas e Molhos", 1, _UTENSILIO_TOKENS),
    "molho":            Rule("Alimentos (Mercearia)", "Conservas e Molhos", 1, _UTENSILIO_TOKENS),

    # Grãos e Massas — veto forte: qualquer utensílio cancela
    "macarrao":         Rule("Alimentos (Mercearia)", "Grãos e Massas", 1, _UTENSILIO_TOKENS),
    "arroz":            Rule("Alimentos (Mercearia)", "Grãos e Massas", 1, _UTENSILIO_TOKENS),
    "feijao":           Rule("Alimentos (Mercearia)", "Grãos e Massas", 1, _UTENSILIO_TOKENS),
    "lentilha":         Rule("Alimentos (Mercearia)", "Grãos e Massas", 1, _UTENSILIO_TOKENS),
    "grao de bico":     Rule("Alimentos (Mercearia)", "Grãos e Massas", 2, _UTENSILIO_TOKENS),
    "fuba":             Rule("Alimentos (Mercearia)", "Grãos e Massas", 1, _UTENSILIO_TOKENS),
    "farinha de trigo": Rule("Alimentos (Mercearia)", "Grãos e Massas", 2, _UTENSILIO_TOKENS),
    "farinha de mandioca": Rule("Alimentos (Mercearia)", "Grãos e Massas", 3, _UTENSILIO_TOKENS),
    "aveia":            Rule("Alimentos (Mercearia)", "Grãos e Massas", 1, _UTENSILIO_TOKENS),
    "granola":          Rule("Alimentos (Mercearia)", "Grãos e Massas", 1, _UTENSILIO_TOKENS),
    "farinha":          Rule("Alimentos (Mercearia)", "Grãos e Massas", 1, _UTENSILIO_TOKENS),
    "massa":            Rule("Alimentos (Mercearia)", "Grãos e Massas", 1, _UTENSILIO_TOKENS),

    # Óleos e Temperos — "oleo" genérico veta utensílio
    "azeite":           Rule("Alimentos (Mercearia)", "Óleos e Temperos", 1, _UTENSILIO_TOKENS),
    "oleo de soja":     Rule("Alimentos (Mercearia)", "Óleos e Temperos", 2, _UTENSILIO_TOKENS),
    "oleo de girassol": Rule("Alimentos (Mercearia)", "Óleos e Temperos", 2, _UTENSILIO_TOKENS),
    "vinagre":          Rule("Alimentos (Mercearia)", "Óleos e Temperos", 1, _UTENSILIO_TOKENS),
    "sal refinado":     Rule("Alimentos (Mercearia)", "Óleos e Temperos", 2, _UTENSILIO_TOKENS),
    "pimenta do reino": Rule("Alimentos (Mercearia)", "Óleos e Temperos", 2, _UTENSILIO_TOKENS),
    "tempero pronto":   Rule("Alimentos (Mercearia)", "Óleos e Temperos", 2, _UTENSILIO_TOKENS),
    "caldo de":         Rule("Alimentos (Mercearia)", "Óleos e Temperos", 2, _UTENSILIO_TOKENS),
    "oleo":             Rule("Alimentos (Mercearia)", "Óleos e Temperos", 1, _UTENSILIO_TOKENS),
    "tempero":          Rule("Alimentos (Mercearia)", "Óleos e Temperos", 1, _UTENSILIO_TOKENS),

    # Pipoca
    "pipoca":           Rule("Alimentos (Mercearia)", "Pipoca", 1, _UTENSILIO_TOKENS),

    # ═══════════════════════════════════════════════════════════════════════
    # FRIOS E CONGELADOS — veto utensílios
    # ═══════════════════════════════════════════════════════════════════════

    "sorvete":              Rule("Frios e Congelados", "Sorvetes e Picolés", 1, _UTENSILIO_TOKENS),
    "picole":               Rule("Frios e Congelados", "Sorvetes e Picolés", 1, _UTENSILIO_TOKENS),
    "gelato":               Rule("Frios e Congelados", "Sorvetes e Picolés", 1, _UTENSILIO_TOKENS),
    "frango congelado":     Rule("Frios e Congelados", "Carnes e Aves", 2, _UTENSILIO_TOKENS),
    "carne bovina":         Rule("Frios e Congelados", "Carnes e Aves", 2, _UTENSILIO_TOKENS),
    "linguica":             Rule("Frios e Congelados", "Carnes e Aves", 1, _UTENSILIO_TOKENS),
    "salsicha":             Rule("Frios e Congelados", "Carnes e Aves", 1, _UTENSILIO_TOKENS),
    "presunto":             Rule("Frios e Congelados", "Carnes e Aves", 1, _UTENSILIO_TOKENS),
    "mussarela":            Rule("Frios e Congelados", "Carnes e Aves", 1, _UTENSILIO_TOKENS),
    "queijo":               Rule("Frios e Congelados", "Carnes e Aves", 1, _UTENSILIO_TOKENS),
    "frango":               Rule("Frios e Congelados", "Carnes e Aves", 1, _UTENSILIO_TOKENS),
    "carne":                Rule("Frios e Congelados", "Carnes e Aves", 1, _UTENSILIO_TOKENS),
    "lasanha congelada":    Rule("Frios e Congelados", "Pratos Prontos", 2, _UTENSILIO_TOKENS),
    "pizza congelada":      Rule("Frios e Congelados", "Pratos Prontos", 2, _UTENSILIO_TOKENS),
    "prato pronto":         Rule("Frios e Congelados", "Pratos Prontos", 2, _UTENSILIO_TOKENS),

    # ═══════════════════════════════════════════════════════════════════════
    # HIGIENE E CUIDADOS PESSOAIS
    # ═══════════════════════════════════════════════════════════════════════

    "shampoo":              Rule("Higiene e Cuidados Pessoais", "Cabelo", 1),
    "condicionador":        Rule("Higiene e Cuidados Pessoais", "Cabelo", 1),
    "creme de cabelo":      Rule("Higiene e Cuidados Pessoais", "Cabelo", 2),
    "tinta de cabelo":      Rule("Higiene e Cuidados Pessoais", "Cabelo", 2),
    "mascara capilar":      Rule("Higiene e Cuidados Pessoais", "Cabelo", 2),
    "sabonete":             Rule("Higiene e Cuidados Pessoais", "Sabonetes", 1),
    "sabao liquido para maos": Rule("Higiene e Cuidados Pessoais", "Sabonetes", 3),
    "desodorante":          Rule("Higiene e Cuidados Pessoais", "Desodorantes", 1),
    "antitranspirante":     Rule("Higiene e Cuidados Pessoais", "Desodorantes", 1),
    "escova de dente":      Rule("Higiene e Cuidados Pessoais", "Higiene Oral", 2),
    "pasta de dente":       Rule("Higiene e Cuidados Pessoais", "Higiene Oral", 2),
    "fio dental":           Rule("Higiene e Cuidados Pessoais", "Higiene Oral", 2),
    "enxaguante bucal":     Rule("Higiene e Cuidados Pessoais", "Higiene Oral", 2),
    "dentifricio":          Rule("Higiene e Cuidados Pessoais", "Higiene Oral", 1),
    "absorvente":           Rule("Higiene e Cuidados Pessoais", "Absorventes", 1),
    "fralda":               Rule("Higiene e Cuidados Pessoais", "Absorventes", 1),
    "lenco umedecido":      Rule("Higiene e Cuidados Pessoais", "Absorventes", 2),
    "creme hidratante":     Rule("Higiene e Cuidados Pessoais", "Cosméticos", 2),
    "maquiagem":            Rule("Higiene e Cuidados Pessoais", "Cosméticos", 1),
    "batom":                Rule("Higiene e Cuidados Pessoais", "Cosméticos", 1),
    "perfume":              Rule("Higiene e Cuidados Pessoais", "Cosméticos", 1),
    "protetor solar":       Rule("Higiene e Cuidados Pessoais", "Cosméticos", 2),
    "base maquiagem":       Rule("Higiene e Cuidados Pessoais", "Cosméticos", 2),
    "hidratante":           Rule("Higiene e Cuidados Pessoais", "Cosméticos", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # BAZAR E UTILIDADES — tokens de utensílio têm score alto
    # ═══════════════════════════════════════════════════════════════════════

    "panela de pressao":    Rule("Bazar e Utilidades", "Panelas", 2),
    "frigideira":           Rule("Bazar e Utilidades", "Panelas", 1),
    "wok":                  Rule("Bazar e Utilidades", "Panelas", 1),
    "cacarola":             Rule("Bazar e Utilidades", "Panelas", 1),
    "panela":               Rule("Bazar e Utilidades", "Panelas", 1),
    "pote plastico":        Rule("Bazar e Utilidades", "Recipientes de Plástico", 2),
    "vasilha plastica":     Rule("Bazar e Utilidades", "Recipientes de Plástico", 2),
    "pote hermetico":       Rule("Bazar e Utilidades", "Recipientes de Plástico", 2),
    "tupperware":           Rule("Bazar e Utilidades", "Recipientes de Plástico", 1),
    "pote":                 Rule("Bazar e Utilidades", "Recipientes de Plástico", 1),
    "vasilha":              Rule("Bazar e Utilidades", "Recipientes de Plástico", 1),
    "taca de vidro":        Rule("Bazar e Utilidades", "Vidros e Taças", 2),
    "copo de vidro":        Rule("Bazar e Utilidades", "Vidros e Taças", 2),
    "jarra de vidro":       Rule("Bazar e Utilidades", "Vidros e Taças", 2),
    "garrafa de vidro":     Rule("Bazar e Utilidades", "Vidros e Taças", 2),
    "escorredor de pratos": Rule("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "espatula de cozinha":  Rule("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "concha de servir":     Rule("Bazar e Utilidades", "Utensílios de Cozinha", 3),
    "concha":               Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "pegador de macarrao":  Rule("Bazar e Utilidades", "Utensílios de Cozinha", 3),
    "pegador de salada":    Rule("Bazar e Utilidades", "Utensílios de Cozinha", 3),
    "pegador":              Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "faca de cozinha":      Rule("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "tabua de corte":       Rule("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "colher de pau":        Rule("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "espatula":             Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "escorredor":           Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "ralador":              Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "descascador":          Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "abridor":              Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "espremedor":           Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "peneira":              Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "coador":               Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "colher":               Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "forma":                Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "assadeira":            Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "molheira":             Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "galheteiro":           Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "tabua":                Rule("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "porta tempero":        Rule("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "porta sal":            Rule("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "utensilios de cozinha": Rule("Bazar e Utilidades", "Utensílios de Cozinha", 3),
    "garrafa termica":      Rule("Bazar e Utilidades", "Garrafas Térmicas", 2),
    "squeeze":              Rule("Bazar e Utilidades", "Garrafas Térmicas", 1),
    "copo termico":         Rule("Bazar e Utilidades", "Garrafas Térmicas", 2),
    "jogo de talheres":     Rule("Bazar e Utilidades", "Talheres", 2),
    "colher de mesa":       Rule("Bazar e Utilidades", "Talheres", 2),
    "garfo":                Rule("Bazar e Utilidades", "Talheres", 1),
    "talher":               Rule("Bazar e Utilidades", "Talheres", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # MÓVEIS
    # ═══════════════════════════════════════════════════════════════════════

    "cadeira de escritorio": Rule("Móveis", "Cadeiras e Poltronas", 2),
    "poltrona":             Rule("Móveis", "Cadeiras e Poltronas", 1),
    "banqueta":             Rule("Móveis", "Cadeiras e Poltronas", 1),
    "cadeira":              Rule("Móveis", "Cadeiras e Poltronas", 1),
    "mesa de jantar":       Rule("Móveis", "Mesas", 2),
    "mesa de escritorio":   Rule("Móveis", "Mesas", 2),
    "mesa de centro":       Rule("Móveis", "Mesas", 2),
    "mesinha":              Rule("Móveis", "Mesas", 1),
    "mesa":                 Rule("Móveis", "Mesas", 1),
    "colchao":              Rule("Móveis", "Colchões e Camas", 1),
    "cama box":             Rule("Móveis", "Colchões e Camas", 2),
    "beliche":              Rule("Móveis", "Colchões e Camas", 1),
    "berco":                Rule("Móveis", "Colchões e Camas", 1),
    "cama":                 Rule("Móveis", "Colchões e Camas", 1),
    "guarda roupa":         Rule("Móveis", "Armários e Roupeiros", 2),
    "comoda":               Rule("Móveis", "Armários e Roupeiros", 1),
    "armario":              Rule("Móveis", "Armários e Roupeiros", 1),
    "estante de livros":    Rule("Móveis", "Estantes e Racks", 2),
    "rack de tv":           Rule("Móveis", "Estantes e Racks", 2),
    "prateleira":           Rule("Móveis", "Estantes e Racks", 1),
    "estante":              Rule("Móveis", "Estantes e Racks", 1),
    "rack":                 Rule("Móveis", "Estantes e Racks", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # DECORAÇÃO
    # ═══════════════════════════════════════════════════════════════════════

    "espelho decorativo":   Rule("Decoração", "Espelhos", 2),
    "espelho":              Rule("Decoração", "Espelhos", 1),
    "relogio de parede":    Rule("Decoração", "Relógios de Parede", 2),
    "relogio":              Rule("Decoração", "Relógios de Parede", 1),
    "vaso decorativo":      Rule("Decoração", "Vasos", 2),
    "cachepot":             Rule("Decoração", "Vasos", 1),
    "vaso":                 Rule("Decoração", "Vasos", 1),
    "quadro decorativo":    Rule("Decoração", "Quadros", 2),
    "poster":               Rule("Decoração", "Quadros", 1),
    "quadro":               Rule("Decoração", "Quadros", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # LAZER E CAMPING
    # ═══════════════════════════════════════════════════════════════════════

    "piscina infantil":     Rule("Lazer e Camping", "Piscinas e Acessórios", 2),
    "boia de piscina":      Rule("Lazer e Camping", "Piscinas e Acessórios", 2),
    "inflavel de piscina":  Rule("Lazer e Camping", "Piscinas e Acessórios", 2),
    "piscina":              Rule("Lazer e Camping", "Piscinas e Acessórios", 1),
    "caixa termica":        Rule("Lazer e Camping", "Caixas Térmicas", 2),
    "cooler":               Rule("Lazer e Camping", "Caixas Térmicas", 1),
    "isopor":               Rule("Lazer e Camping", "Caixas Térmicas", 1),
    "barraca de camping":   Rule("Lazer e Camping", "Barracas", 2),
    "barraca de praia":     Rule("Lazer e Camping", "Barracas", 2),
    "barraca":              Rule("Lazer e Camping", "Barracas", 1),
    "cadeira de praia":     Rule("Lazer e Camping", "Cadeiras de Praia", 2),
    "cadeira dobravel":     Rule("Lazer e Camping", "Cadeiras de Praia", 2),

    # ═══════════════════════════════════════════════════════════════════════
    # FERRAMENTAS E FERRAGENS
    # ═══════════════════════════════════════════════════════════════════════

    "furadeira":            Rule("Ferramentas e Ferragens", "Elétricas", 1),
    "esmerilhadeira":       Rule("Ferramentas e Ferragens", "Elétricas", 1),
    "parafusadeira":        Rule("Ferramentas e Ferragens", "Elétricas", 1),
    "serra circular":       Rule("Ferramentas e Ferragens", "Elétricas", 2),
    "lixadeira":            Rule("Ferramentas e Ferragens", "Elétricas", 1),
    "martelo":              Rule("Ferramentas e Ferragens", "Manuais", 1),
    "chave de fenda":       Rule("Ferramentas e Ferragens", "Manuais", 2),
    "alicate":              Rule("Ferramentas e Ferragens", "Manuais", 1),
    "chave inglesa":        Rule("Ferramentas e Ferragens", "Manuais", 2),
    "serrote":              Rule("Ferramentas e Ferragens", "Manuais", 1),
    "trena":                Rule("Ferramentas e Ferragens", "Medição", 1),
    "nivel de bolha":       Rule("Ferramentas e Ferragens", "Medição", 2),
    "paquimetro":           Rule("Ferramentas e Ferragens", "Medição", 1),
    "cadeado":              Rule("Ferramentas e Ferragens", "Ferragens e Cadeados", 1),
    "dobradica":            Rule("Ferramentas e Ferragens", "Ferragens e Cadeados", 1),
    "parafuso":             Rule("Ferramentas e Ferragens", "Ferragens e Cadeados", 1),
    "prego":                Rule("Ferramentas e Ferragens", "Ferragens e Cadeados", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # MATERIAIS DE CONSTRUÇÃO
    # ═══════════════════════════════════════════════════════════════════════

    "tinta latex":          Rule("Materiais de Construção", "Pintura", 2),
    "tinta acrilica":       Rule("Materiais de Construção", "Pintura", 2),
    "massa corrida":        Rule("Materiais de Construção", "Pintura", 2),
    "rolo de pintura":      Rule("Materiais de Construção", "Pintura", 2),
    "pincel de pintura":    Rule("Materiais de Construção", "Pintura", 2),
    "verniz":               Rule("Materiais de Construção", "Pintura", 1),
    "tinta":                Rule("Materiais de Construção", "Pintura", 1),
    "pincel":               Rule("Materiais de Construção", "Pintura", 1),
    "torneira":             Rule("Materiais de Construção", "Hidráulica", 1),
    "registro de agua":     Rule("Materiais de Construção", "Hidráulica", 2),
    "sifao":                Rule("Materiais de Construção", "Hidráulica", 1),
    "tubo pvc":             Rule("Materiais de Construção", "Hidráulica", 2),
    "cano":                 Rule("Materiais de Construção", "Hidráulica", 1),
    "fio eletrico":         Rule("Materiais de Construção", "Elétrica", 2),
    "cabo eletrico":        Rule("Materiais de Construção", "Elétrica", 2),
    "tomada eletrica":      Rule("Materiais de Construção", "Elétrica", 2),
    "interruptor":          Rule("Materiais de Construção", "Elétrica", 1),
    "disjuntor":            Rule("Materiais de Construção", "Elétrica", 1),
    "lampada led":          Rule("Materiais de Construção", "Elétrica", 2),
    "lampada":              Rule("Materiais de Construção", "Elétrica", 1),
    "led":                  Rule("Materiais de Construção", "Elétrica", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # ELETRO E ELETRÔNICOS
    # ═══════════════════════════════════════════════════════════════════════

    "liquidificador":       Rule("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "batedeira":            Rule("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "cafeteira":            Rule("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "sanduicheira":         Rule("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "ventilador":           Rule("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "ferro de passar":      Rule("Eletro e Eletrônicos", "Eletroportáteis", 2),
    "aspirador de po":      Rule("Eletro e Eletrônicos", "Eletroportáteis", 2),
    "micro-ondas":          Rule("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "multiprocessador":     Rule("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "airfryer":             Rule("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "cabo usb":             Rule("Eletro e Eletrônicos", "Cabos e Carregadores", 2),
    "cabo hdmi":            Rule("Eletro e Eletrônicos", "Cabos e Carregadores", 2),
    "carregador de celular": Rule("Eletro e Eletrônicos", "Cabos e Carregadores", 2),
    "carregador portatil":  Rule("Eletro e Eletrônicos", "Cabos e Carregadores", 2),
    "carregador":           Rule("Eletro e Eletrônicos", "Cabos e Carregadores", 1),
    "cabo":                 Rule("Eletro e Eletrônicos", "Cabos e Carregadores", 1),
    "caixa de som bluetooth": Rule("Eletro e Eletrônicos", "Áudio e Som", 3),
    "fone de ouvido":       Rule("Eletro e Eletrônicos", "Áudio e Som", 2),
    "headphone":            Rule("Eletro e Eletrônicos", "Áudio e Som", 1),
    "headset":              Rule("Eletro e Eletrônicos", "Áudio e Som", 1),
    "caixa de som":         Rule("Eletro e Eletrônicos", "Áudio e Som", 2),
    "capa de celular":      Rule("Eletro e Eletrônicos", "Acessórios de Celular", 2),
    "pelicula de celular":  Rule("Eletro e Eletrônicos", "Acessórios de Celular", 2),
    "suporte celular":      Rule("Eletro e Eletrônicos", "Acessórios de Celular", 2),
    "acessorio celular":    Rule("Eletro e Eletrônicos", "Acessórios de Celular", 2),
    "pelicula":             Rule("Eletro e Eletrônicos", "Acessórios de Celular", 1),
    "pilha alcalina":       Rule("Eletro e Eletrônicos", "Pilhas e Baterias", 2),
    "bateria recarregavel": Rule("Eletro e Eletrônicos", "Pilhas e Baterias", 2),
    "pilha":                Rule("Eletro e Eletrônicos", "Pilhas e Baterias", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # AUTOMOTIVO / BRINQUEDOS / VESTUÁRIO / TABACARIA / CAMA MESA BANHO / PADARIA
    # ═══════════════════════════════════════════════════════════════════════

    "capacete moto":        Rule("Automotivo e Moto", "Capacetes", 2),
    "capacete":             Rule("Automotivo e Moto", "Capacetes", 1),
    "boneca barbie":        Rule("Brinquedos", "Bonecas", 2),
    "boneca":               Rule("Brinquedos", "Bonecas", 1),
    "carrinho hot wheels":  Rule("Brinquedos", "Carrinhos e Pistas", 3),
    "pista de corrida":     Rule("Brinquedos", "Carrinhos e Pistas", 2),
    "carrinho de brinquedo": Rule("Brinquedos", "Carrinhos e Pistas", 2),
    "jogo de tabuleiro":    Rule("Brinquedos", "Jogos de Tabuleiro", 2),
    "xadrez":               Rule("Brinquedos", "Jogos de Tabuleiro", 1),
    "pelucia":              Rule("Brinquedos", "Pelúcias", 1),
    "ursinho de pelucia":   Rule("Brinquedos", "Pelúcias", 2),
    "chinelo havaianas":    Rule("Vestuário e Calçados", "Chinelos e Sandálias", 2),
    "havaianas":            Rule("Vestuário e Calçados", "Chinelos e Sandálias", 1),
    "sandalia feminina":    Rule("Vestuário e Calçados", "Chinelos e Sandálias", 2),
    "chinelo":              Rule("Vestuário e Calçados", "Chinelos e Sandálias", 1),
    "sandalia":             Rule("Vestuário e Calçados", "Chinelos e Sandálias", 1),
    "calcinha":             Rule("Vestuário e Calçados", "Peças Íntimas", 1),
    "cueca":                Rule("Vestuário e Calçados", "Peças Íntimas", 1),
    "sutia":                Rule("Vestuário e Calçados", "Peças Íntimas", 1),
    "meia":                 Rule("Vestuário e Calçados", "Peças Íntimas", 1),
    "camiseta":             Rule("Vestuário e Calçados", "Roupas", 1),
    "blusa":                Rule("Vestuário e Calçados", "Roupas", 1),
    "calca jeans":          Rule("Vestuário e Calçados", "Roupas", 2),
    "capa de chuva":        Rule("Vestuário e Calçados", "Capas de Chuva", 2),
    "guarda chuva":         Rule("Vestuário e Calçados", "Capas de Chuva", 2),
    "poncho":               Rule("Vestuário e Calçados", "Capas de Chuva", 1),
    "cigarro eletronico":   Rule("Tabacaria", "Cigarros", 2),
    "cigarro":              Rule("Tabacaria", "Cigarros", 1),
    "isqueiro":             Rule("Tabacaria", "Isqueiros e Fósforos", 1),
    "fosforo":              Rule("Tabacaria", "Isqueiros e Fósforos", 1),
    "toalha de banho":      Rule("Cama, Mesa e Banho", "Toalhas", 2),
    "toalha de rosto":      Rule("Cama, Mesa e Banho", "Toalhas", 2),
    "jogo de toalhas":      Rule("Cama, Mesa e Banho", "Toalhas", 2),
    "toalha":               Rule("Cama, Mesa e Banho", "Toalhas", 1),
    "tapete de banheiro":   Rule("Cama, Mesa e Banho", "Tapetes", 2),
    "tapete sala":          Rule("Cama, Mesa e Banho", "Tapetes", 2),
    "tapete":               Rule("Cama, Mesa e Banho", "Tapetes", 1),
    "cortina blackout":     Rule("Cama, Mesa e Banho", "Cortinas e Varões", 2),
    "varao de cortina":     Rule("Cama, Mesa e Banho", "Cortinas e Varões", 2),
    "cortina":              Rule("Cama, Mesa e Banho", "Cortinas e Varões", 1),
    "pao de forma":         Rule("Padaria e Lanchonete", "Pães e Salgados", 2, _UTENSILIO_TOKENS),
    "baguete":              Rule("Padaria e Lanchonete", "Pães e Salgados", 1, _UTENSILIO_TOKENS),
    "coxinha":              Rule("Padaria e Lanchonete", "Pães e Salgados", 1, _UTENSILIO_TOKENS),
    "kibe":                 Rule("Padaria e Lanchonete", "Pães e Salgados", 1, _UTENSILIO_TOKENS),
    "salgado":              Rule("Padaria e Lanchonete", "Pães e Salgados", 1, _UTENSILIO_TOKENS),
    "pao":                  Rule("Padaria e Lanchonete", "Pães e Salgados", 1, _UTENSILIO_TOKENS),
    "bolo de chocolate":    Rule("Padaria e Lanchonete", "Bolos e Tortas", 2, _UTENSILIO_TOKENS),
    "torta doce":           Rule("Padaria e Lanchonete", "Bolos e Tortas", 2, _UTENSILIO_TOKENS),
    "bolo":                 Rule("Padaria e Lanchonete", "Bolos e Tortas", 1, _UTENSILIO_TOKENS),
    "torta":                Rule("Padaria e Lanchonete", "Bolos e Tortas", 1, _UTENSILIO_TOKENS),
    "refeicao pronta":      Rule("Padaria e Lanchonete", "Refeições Prontas", 2, _UTENSILIO_TOKENS),
    "marmita":              Rule("Padaria e Lanchonete", "Refeições Prontas", 1, _UTENSILIO_TOKENS),
    "sanduiche":            Rule("Padaria e Lanchonete", "Lanches Rápidos", 1, _UTENSILIO_TOKENS),
    "hamburguer":           Rule("Padaria e Lanchonete", "Lanches Rápidos", 1, _UTENSILIO_TOKENS),
    "lanche":               Rule("Padaria e Lanchonete", "Lanches Rápidos", 1, _UTENSILIO_TOKENS),
}


# ---------------------------------------------------------------------------
# Função principal — pontuação por candidatos + vetos
# ---------------------------------------------------------------------------

def classify_by_keywords(descricao: str) -> dict | None:
    """
    Classifica um produto por pontuação acumulada de termos + vetos contextuais.

    Algoritmo:
      1. Normaliza o texto e extrai unigramas, bigramas e trigramas.
      2. Para cada regra cujo termo está presente, acumula score em
         um dicionário keyed por (grupo, subgrupo).
      3. Filtra candidatos cujas regras têm veto_if disparado pelos
         tokens da descrição.
      4. Retorna o (grupo, subgrupo) com maior score acumulado.

    Isso resolve ambiguidades tipo "concha de macarrão":
      - "concha" → Bazar/Utensílios de Cozinha, score 1, sem veto
      - "macarrao" → Alimentos/Grãos, score 1, veto_if inclui "concha" → VETADO
      - Resultado: Bazar/Utensílios de Cozinha ✓

    Args:
        descricao: Descrição do produto a classificar.

    Returns:
        Dict {"grupo": str, "subgrupo": str} ou None se nenhum termo casar.
    """
    if not descricao or not descricao.strip():
        return None

    norm = normalize(descricao)
    words = norm.split()
    token_set = set(words)

    bigrams  = {words[i] + " " + words[i+1]             for i in range(len(words) - 1)}
    trigrams = {words[i] + " " + words[i+1] + " " + words[i+2] for i in range(len(words) - 2)}
    all_terms = token_set | bigrams | trigrams

    # Acumular scores por (grupo, subgrupo)
    scores: dict[tuple[str, str], int] = {}

    for term, rule in KEYWORD_RULES.items():
        if term not in all_terms:
            continue

        # Verificar veto contextual
        if rule.veto_if and rule.veto_if & token_set:
            vetoed_by = rule.veto_if & token_set
            logger.debug(
                f"Regra '{term}' → {rule.grupo}/{rule.subgrupo} "
                f"VETADA por tokens: {vetoed_by} em '{descricao[:60]}'"
            )
            continue

        key = (rule.grupo, rule.subgrupo)
        scores[key] = scores.get(key, 0) + rule.score

    if not scores:
        return None

    best_key = max(scores, key=lambda k: scores[k])
    best_score = scores[best_key]

    logger.debug(
        f"Keywords → {best_key[0]}/{best_key[1]} "
        f"(score={best_score}, todos={scores}) "
        f"para '{descricao[:60]}'"
    )

    return {"grupo": best_key[0], "subgrupo": best_key[1]}
