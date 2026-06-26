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
class Regra:
    """Uma regra de classificação com peso e vetos opcionais."""
    grupo: str
    subgrupo: str
    pontuacao: int = 1          # unigramas=1, bigramas=2, trigramas=3
    vetar_se: set[str] = field(default_factory=set)
    # Se qualquer termo de veto_if estiver na descrição normalizada,
    # esta regra é ignorada mesmo que o termo principal case.


# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------

def normalizar(texto: str) -> str:
    """Remove acentos, lowercase, substitui pontuação por espaço."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-z0-9 ]", " ", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


# ---------------------------------------------------------------------------
# Vetos globais — tokens que indicam "objeto físico" e bloqueiam Alimentos/Frios
# ---------------------------------------------------------------------------

# Qualquer regra de Alimentos/Frios que encontrar esses tokens na descrição
# será cancelada, pois o produto é claramente um utensílio ou recipiente.
_TOKENS_UTENSILIO = {
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
# Dicionário principal — REGRAS_PALAVRAS_CHAVE
# Formato: termo → Regra(grupo, subgrupo, score, veto_if)
# Bigramas definidos ANTES de unigramas para ganhar em caso de empate de score.
# ---------------------------------------------------------------------------

REGRAS_PALAVRAS_CHAVE: dict[str, Regra] = {

    # ═══════════════════════════════════════════════════════════════════════
    # BEBIDAS
    # ═══════════════════════════════════════════════════════════════════════

    # Vinhos
    "vinho tinto":      Regra("Bebidas", "Vinhos", 2),
    "vinho branco":     Regra("Bebidas", "Vinhos", 2),
    "vinho rose":       Regra("Bebidas", "Vinhos", 2),
    "vinho verde":      Regra("Bebidas", "Vinhos", 2),
    "vinho suave":      Regra("Bebidas", "Vinhos", 2),
    "espumante":        Regra("Bebidas", "Vinhos", 1),
    "vinho":            Regra("Bebidas", "Vinhos", 1),

    # Cervejas
    "cerveja":          Regra("Bebidas", "Cervejas", 1),
    "heineken":         Regra("Bebidas", "Cervejas", 1),
    "skol":             Regra("Bebidas", "Cervejas", 1),
    "brahma":           Regra("Bebidas", "Cervejas", 1),
    "itaipava":         Regra("Bebidas", "Cervejas", 1),
    "budweiser":        Regra("Bebidas", "Cervejas", 1),
    "amstel":           Regra("Bebidas", "Cervejas", 1),
    "stella artois":    Regra("Bebidas", "Cervejas", 2),
    "petra":            Regra("Bebidas", "Cervejas", 1),

    # Refrigerantes
    "refrigerante":     Regra("Bebidas", "Refrigerantes", 1),
    "coca cola":        Regra("Bebidas", "Refrigerantes", 2),
    "pepsi":            Regra("Bebidas", "Refrigerantes", 1),
    "guarana":          Regra("Bebidas", "Refrigerantes", 1),
    "fanta":            Regra("Bebidas", "Refrigerantes", 1),
    "sprite":           Regra("Bebidas", "Refrigerantes", 1),
    "schweppes":        Regra("Bebidas", "Refrigerantes", 1),

    # Sucos e Chás
    "suco de":          Regra("Bebidas", "Sucos e Chás", 2),
    "nectar de":        Regra("Bebidas", "Sucos e Chás", 2),
    "cha gelado":       Regra("Bebidas", "Sucos e Chás", 2),
    "cha verde":        Regra("Bebidas", "Sucos e Chás", 2),
    "cha preto":        Regra("Bebidas", "Sucos e Chás", 2),
    "powerade":         Regra("Bebidas", "Sucos e Chás", 1),
    "gatorade":         Regra("Bebidas", "Sucos e Chás", 1),
    "suco":             Regra("Bebidas", "Sucos e Chás", 1),
    "nectar":           Regra("Bebidas", "Sucos e Chás", 1),
    "isotônico":        Regra("Bebidas", "Sucos e Chás", 1),
    "isotonico":        Regra("Bebidas", "Sucos e Chás", 1),

    # Água
    "agua mineral":     Regra("Bebidas", "Água", 2),
    "agua com gas":     Regra("Bebidas", "Água", 3),
    "agua sem gas":     Regra("Bebidas", "Água", 3),
    "agua":             Regra("Bebidas", "Água", 1),

    # Destilados e Ice
    "whisky":           Regra("Bebidas", "Destilados e Ice", 1),
    "whiskey":          Regra("Bebidas", "Destilados e Ice", 1),
    "vodka":            Regra("Bebidas", "Destilados e Ice", 1),
    "cachaca":          Regra("Bebidas", "Destilados e Ice", 1),
    "rum":              Regra("Bebidas", "Destilados e Ice", 1),
    "gin":              Regra("Bebidas", "Destilados e Ice", 1),
    "tequila":          Regra("Bebidas", "Destilados e Ice", 1),
    "licor":            Regra("Bebidas", "Destilados e Ice", 1),
    "conhaque":         Regra("Bebidas", "Destilados e Ice", 1),
    "destilado":        Regra("Bebidas", "Destilados e Ice", 1),

    # Energéticos
    "energetico":       Regra("Bebidas", "Energéticos", 1),
    "red bull":         Regra("Bebidas", "Energéticos", 2),
    "monster":          Regra("Bebidas", "Energéticos", 1),
    "tnt energy":       Regra("Bebidas", "Energéticos", 2),
    "burn":             Regra("Bebidas", "Energéticos", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # LIMPEZA
    # ═══════════════════════════════════════════════════════════════════════

    "vassoura":             Regra("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 1),
    "rodo":                 Regra("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 1),
    "esponja de limpeza":   Regra("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 2),
    "balde":                Regra("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 1),
    "pano de chao":         Regra("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 2),
    "flanela":              Regra("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 1),
    "mop":                  Regra("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 1),
    "esponja":              Regra("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 1),
    "luva de borracha":     Regra("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)", 2),
    "detergente":           Regra("Limpeza", "Produtos Químicos", 1),
    "desinfetante":         Regra("Limpeza", "Produtos Químicos", 1),
    "alvejante":            Regra("Limpeza", "Produtos Químicos", 1),
    "sabao em po":          Regra("Limpeza", "Produtos Químicos", 2),
    "sabao liquido":        Regra("Limpeza", "Produtos Químicos", 2),
    "amaciante":            Regra("Limpeza", "Produtos Químicos", 1),
    "multiuso":             Regra("Limpeza", "Produtos Químicos", 1),
    "limpa vidro":          Regra("Limpeza", "Produtos Químicos", 2),
    "ajax":                 Regra("Limpeza", "Produtos Químicos", 1),
    "omo":                  Regra("Limpeza", "Produtos Químicos", 1),
    "ariel":                Regra("Limpeza", "Produtos Químicos", 1),
    "tira mofo":            Regra("Limpeza", "Produtos Químicos", 2),
    "cloro":                Regra("Limpeza", "Produtos Químicos", 1),
    "hipoclorito":          Regra("Limpeza", "Produtos Químicos", 1),
    "lixeira":              Regra("Limpeza", "Lixeiras e Cestos", 1),
    "cesto de lixo":        Regra("Limpeza", "Lixeiras e Cestos", 2),
    "cesto":                Regra("Limpeza", "Lixeiras e Cestos", 1),
    "organizador":          Regra("Limpeza", "Organização", 1),
    "organizador de cozinha": Regra("Limpeza", "Organização", 3),
    "organizador plastico": Regra("Limpeza", "Organização", 2),

    # ═══════════════════════════════════════════════════════════════════════
    # ALIMENTOS — todos com veto_if=_TOKENS_UTENSILIO
    # ═══════════════════════════════════════════════════════════════════════

    # Biscoitos e Salgadinhos
    "biscoito":         Regra("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _TOKENS_UTENSILIO),
    "bolacha":          Regra("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _TOKENS_UTENSILIO),
    "salgadinho":       Regra("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _TOKENS_UTENSILIO),
    "chips":            Regra("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _TOKENS_UTENSILIO),
    "amendoim":         Regra("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _TOKENS_UTENSILIO),
    "batatinha":        Regra("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _TOKENS_UTENSILIO),
    "snack":            Regra("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _TOKENS_UTENSILIO),
    "torrada":          Regra("Alimentos (Mercearia)", "Biscoitos e Salgadinhos", 1, _TOKENS_UTENSILIO),

    # Doces e Sobremesas
    "chocolate":        Regra("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _TOKENS_UTENSILIO),
    "bala":             Regra("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _TOKENS_UTENSILIO),
    "chiclete":         Regra("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _TOKENS_UTENSILIO),
    "pirulito":         Regra("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _TOKENS_UTENSILIO),
    "bombom":           Regra("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _TOKENS_UTENSILIO),
    "geleia":           Regra("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _TOKENS_UTENSILIO),
    "mel":              Regra("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _TOKENS_UTENSILIO),
    "doce de leite":    Regra("Alimentos (Mercearia)", "Doces e Sobremesas", 2, _TOKENS_UTENSILIO),
    "achocolatado":     Regra("Alimentos (Mercearia)", "Doces e Sobremesas", 1, _TOKENS_UTENSILIO),

    # Conservas e Molhos — veto especial: "molheira" é utensílio
    "extrato de tomate": Regra("Alimentos (Mercearia)", "Conservas e Molhos", 3, _TOKENS_UTENSILIO),
    "molho de tomate":  Regra("Alimentos (Mercearia)", "Conservas e Molhos", 2, _TOKENS_UTENSILIO),
    "milho em lata":    Regra("Alimentos (Mercearia)", "Conservas e Molhos", 2, _TOKENS_UTENSILIO),
    "ervilha em lata":  Regra("Alimentos (Mercearia)", "Conservas e Molhos", 2, _TOKENS_UTENSILIO),
    "creme de leite":   Regra("Alimentos (Mercearia)", "Conservas e Molhos", 2, _TOKENS_UTENSILIO),
    "leite condensado": Regra("Alimentos (Mercearia)", "Conservas e Molhos", 2, _TOKENS_UTENSILIO),
    "atum":             Regra("Alimentos (Mercearia)", "Conservas e Molhos", 1, _TOKENS_UTENSILIO),
    "sardinha":         Regra("Alimentos (Mercearia)", "Conservas e Molhos", 1, _TOKENS_UTENSILIO),
    "conserva":         Regra("Alimentos (Mercearia)", "Conservas e Molhos", 1, _TOKENS_UTENSILIO),
    "molho":            Regra("Alimentos (Mercearia)", "Conservas e Molhos", 1, _TOKENS_UTENSILIO),

    # Grãos e Massas — veto forte: qualquer utensílio cancela
    "macarrao":         Regra("Alimentos (Mercearia)", "Grãos e Massas", 1, _TOKENS_UTENSILIO),
    "arroz":            Regra("Alimentos (Mercearia)", "Grãos e Massas", 1, _TOKENS_UTENSILIO),
    "feijao":           Regra("Alimentos (Mercearia)", "Grãos e Massas", 1, _TOKENS_UTENSILIO),
    "lentilha":         Regra("Alimentos (Mercearia)", "Grãos e Massas", 1, _TOKENS_UTENSILIO),
    "grao de bico":     Regra("Alimentos (Mercearia)", "Grãos e Massas", 2, _TOKENS_UTENSILIO),
    "fuba":             Regra("Alimentos (Mercearia)", "Grãos e Massas", 1, _TOKENS_UTENSILIO),
    "farinha de trigo": Regra("Alimentos (Mercearia)", "Grãos e Massas", 2, _TOKENS_UTENSILIO),
    "farinha de mandioca": Regra("Alimentos (Mercearia)", "Grãos e Massas", 3, _TOKENS_UTENSILIO),
    "aveia":            Regra("Alimentos (Mercearia)", "Grãos e Massas", 1, _TOKENS_UTENSILIO),
    "granola":          Regra("Alimentos (Mercearia)", "Grãos e Massas", 1, _TOKENS_UTENSILIO),
    "farinha":          Regra("Alimentos (Mercearia)", "Grãos e Massas", 1, _TOKENS_UTENSILIO),
    "massa":            Regra("Alimentos (Mercearia)", "Grãos e Massas", 1, _TOKENS_UTENSILIO),

    # Óleos e Temperos — "oleo" genérico veta utensílio
    "azeite":           Regra("Alimentos (Mercearia)", "Óleos e Temperos", 1, _TOKENS_UTENSILIO),
    "oleo de soja":     Regra("Alimentos (Mercearia)", "Óleos e Temperos", 2, _TOKENS_UTENSILIO),
    "oleo de girassol": Regra("Alimentos (Mercearia)", "Óleos e Temperos", 2, _TOKENS_UTENSILIO),
    "vinagre":          Regra("Alimentos (Mercearia)", "Óleos e Temperos", 1, _TOKENS_UTENSILIO),
    "sal refinado":     Regra("Alimentos (Mercearia)", "Óleos e Temperos", 2, _TOKENS_UTENSILIO),
    "pimenta do reino": Regra("Alimentos (Mercearia)", "Óleos e Temperos", 2, _TOKENS_UTENSILIO),
    "tempero pronto":   Regra("Alimentos (Mercearia)", "Óleos e Temperos", 2, _TOKENS_UTENSILIO),
    "caldo de":         Regra("Alimentos (Mercearia)", "Óleos e Temperos", 2, _TOKENS_UTENSILIO),
    "oleo":             Regra("Alimentos (Mercearia)", "Óleos e Temperos", 1, _TOKENS_UTENSILIO),
    "tempero":          Regra("Alimentos (Mercearia)", "Óleos e Temperos", 1, _TOKENS_UTENSILIO),

    # Pipoca
    "pipoca":           Regra("Alimentos (Mercearia)", "Pipoca", 1, _TOKENS_UTENSILIO),

    # ═══════════════════════════════════════════════════════════════════════
    # FRIOS E CONGELADOS — veto utensílios
    # ═══════════════════════════════════════════════════════════════════════

    "sorvete":              Regra("Frios e Congelados", "Sorvetes e Picolés", 1, _TOKENS_UTENSILIO),
    "picole":               Regra("Frios e Congelados", "Sorvetes e Picolés", 1, _TOKENS_UTENSILIO),
    "gelato":               Regra("Frios e Congelados", "Sorvetes e Picolés", 1, _TOKENS_UTENSILIO),
    "frango congelado":     Regra("Frios e Congelados", "Carnes e Aves", 2, _TOKENS_UTENSILIO),
    "carne bovina":         Regra("Frios e Congelados", "Carnes e Aves", 2, _TOKENS_UTENSILIO),
    "linguica":             Regra("Frios e Congelados", "Carnes e Aves", 1, _TOKENS_UTENSILIO),
    "salsicha":             Regra("Frios e Congelados", "Carnes e Aves", 1, _TOKENS_UTENSILIO),
    "presunto":             Regra("Frios e Congelados", "Carnes e Aves", 1, _TOKENS_UTENSILIO),
    "mussarela":            Regra("Frios e Congelados", "Carnes e Aves", 1, _TOKENS_UTENSILIO),
    "queijo":               Regra("Frios e Congelados", "Carnes e Aves", 1, _TOKENS_UTENSILIO),
    "frango":               Regra("Frios e Congelados", "Carnes e Aves", 1, _TOKENS_UTENSILIO),
    "carne":                Regra("Frios e Congelados", "Carnes e Aves", 1, _TOKENS_UTENSILIO),
    "lasanha congelada":    Regra("Frios e Congelados", "Pratos Prontos", 2, _TOKENS_UTENSILIO),
    "pizza congelada":      Regra("Frios e Congelados", "Pratos Prontos", 2, _TOKENS_UTENSILIO),
    "prato pronto":         Regra("Frios e Congelados", "Pratos Prontos", 2, _TOKENS_UTENSILIO),

    # ═══════════════════════════════════════════════════════════════════════
    # HIGIENE E CUIDADOS PESSOAIS
    # ═══════════════════════════════════════════════════════════════════════

    "shampoo":              Regra("Higiene e Cuidados Pessoais", "Cabelo", 1),
    "condicionador":        Regra("Higiene e Cuidados Pessoais", "Cabelo", 1),
    "creme de cabelo":      Regra("Higiene e Cuidados Pessoais", "Cabelo", 2),
    "tinta de cabelo":      Regra("Higiene e Cuidados Pessoais", "Cabelo", 2),
    "mascara capilar":      Regra("Higiene e Cuidados Pessoais", "Cabelo", 2),
    "sabonete":             Regra("Higiene e Cuidados Pessoais", "Sabonetes", 1),
    "sabao liquido para maos": Regra("Higiene e Cuidados Pessoais", "Sabonetes", 3),
    "desodorante":          Regra("Higiene e Cuidados Pessoais", "Desodorantes", 1),
    "antitranspirante":     Regra("Higiene e Cuidados Pessoais", "Desodorantes", 1),
    "escova de dente":      Regra("Higiene e Cuidados Pessoais", "Higiene Oral", 2),
    "pasta de dente":       Regra("Higiene e Cuidados Pessoais", "Higiene Oral", 2),
    "fio dental":           Regra("Higiene e Cuidados Pessoais", "Higiene Oral", 2),
    "enxaguante bucal":     Regra("Higiene e Cuidados Pessoais", "Higiene Oral", 2),
    "dentifricio":          Regra("Higiene e Cuidados Pessoais", "Higiene Oral", 1),
    "absorvente":           Regra("Higiene e Cuidados Pessoais", "Absorventes", 1),
    "fralda":               Regra("Higiene e Cuidados Pessoais", "Absorventes", 1),
    "lenco umedecido":      Regra("Higiene e Cuidados Pessoais", "Absorventes", 2),
    "creme hidratante":     Regra("Higiene e Cuidados Pessoais", "Cosméticos", 2),
    "maquiagem":            Regra("Higiene e Cuidados Pessoais", "Cosméticos", 1),
    "batom":                Regra("Higiene e Cuidados Pessoais", "Cosméticos", 1),
    "perfume":              Regra("Higiene e Cuidados Pessoais", "Cosméticos", 1),
    "protetor solar":       Regra("Higiene e Cuidados Pessoais", "Cosméticos", 2),
    "base maquiagem":       Regra("Higiene e Cuidados Pessoais", "Cosméticos", 2),
    "hidratante":           Regra("Higiene e Cuidados Pessoais", "Cosméticos", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # BAZAR E UTILIDADES — tokens de utensílio têm score alto
    # ═══════════════════════════════════════════════════════════════════════

    "panela de pressao":    Regra("Bazar e Utilidades", "Panelas", 2),
    "frigideira":           Regra("Bazar e Utilidades", "Panelas", 1),
    "wok":                  Regra("Bazar e Utilidades", "Panelas", 1),
    "cacarola":             Regra("Bazar e Utilidades", "Panelas", 1),
    "panela":               Regra("Bazar e Utilidades", "Panelas", 1),
    "pote plastico":        Regra("Bazar e Utilidades", "Recipientes de Plástico", 2),
    "vasilha plastica":     Regra("Bazar e Utilidades", "Recipientes de Plástico", 2),
    "pote hermetico":       Regra("Bazar e Utilidades", "Recipientes de Plástico", 2),
    "tupperware":           Regra("Bazar e Utilidades", "Recipientes de Plástico", 1),
    "pote":                 Regra("Bazar e Utilidades", "Recipientes de Plástico", 1),
    "vasilha":              Regra("Bazar e Utilidades", "Recipientes de Plástico", 1),
    "taca de vidro":        Regra("Bazar e Utilidades", "Vidros e Taças", 2),
    "copo de vidro":        Regra("Bazar e Utilidades", "Vidros e Taças", 2),
    "jarra de vidro":       Regra("Bazar e Utilidades", "Vidros e Taças", 2),
    "garrafa de vidro":     Regra("Bazar e Utilidades", "Vidros e Taças", 2),
    "escorredor de pratos": Regra("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "espatula de cozinha":  Regra("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "concha de servir":     Regra("Bazar e Utilidades", "Utensílios de Cozinha", 3),
    "concha":               Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "pegador de macarrao":  Regra("Bazar e Utilidades", "Utensílios de Cozinha", 3),
    "pegador de salada":    Regra("Bazar e Utilidades", "Utensílios de Cozinha", 3),
    "pegador":              Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "faca de cozinha":      Regra("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "tabua de corte":       Regra("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "colher de pau":        Regra("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "espatula":             Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "escorredor":           Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "ralador":              Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "descascador":          Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "abridor":              Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "espremedor":           Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "peneira":              Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "coador":               Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "colher":               Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "forma":                Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "assadeira":            Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "molheira":             Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "galheteiro":           Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "tabua":                Regra("Bazar e Utilidades", "Utensílios de Cozinha", 1),
    "porta tempero":        Regra("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "porta sal":            Regra("Bazar e Utilidades", "Utensílios de Cozinha", 2),
    "utensilios de cozinha": Regra("Bazar e Utilidades", "Utensílios de Cozinha", 3),
    "garrafa termica":      Regra("Bazar e Utilidades", "Garrafas Térmicas", 2),
    "squeeze":              Regra("Bazar e Utilidades", "Garrafas Térmicas", 1),
    "copo termico":         Regra("Bazar e Utilidades", "Garrafas Térmicas", 2),
    "jogo de talheres":     Regra("Bazar e Utilidades", "Talheres", 2),
    "colher de mesa":       Regra("Bazar e Utilidades", "Talheres", 2),
    "garfo":                Regra("Bazar e Utilidades", "Talheres", 1),
    "talher":               Regra("Bazar e Utilidades", "Talheres", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # MÓVEIS
    # ═══════════════════════════════════════════════════════════════════════

    "cadeira de escritorio": Regra("Móveis", "Cadeiras e Poltronas", 2),
    "poltrona":             Regra("Móveis", "Cadeiras e Poltronas", 1),
    "banqueta":             Regra("Móveis", "Cadeiras e Poltronas", 1),
    "cadeira":              Regra("Móveis", "Cadeiras e Poltronas", 1),
    "mesa de jantar":       Regra("Móveis", "Mesas", 2),
    "mesa de escritorio":   Regra("Móveis", "Mesas", 2),
    "mesa de centro":       Regra("Móveis", "Mesas", 2),
    "mesinha":              Regra("Móveis", "Mesas", 1),
    "mesa":                 Regra("Móveis", "Mesas", 1),
    "colchao":              Regra("Móveis", "Colchões e Camas", 1),
    "cama box":             Regra("Móveis", "Colchões e Camas", 2),
    "beliche":              Regra("Móveis", "Colchões e Camas", 1),
    "berco":                Regra("Móveis", "Colchões e Camas", 1),
    "cama":                 Regra("Móveis", "Colchões e Camas", 1),
    "guarda roupa":         Regra("Móveis", "Armários e Roupeiros", 2),
    "comoda":               Regra("Móveis", "Armários e Roupeiros", 1),
    "armario":              Regra("Móveis", "Armários e Roupeiros", 1),
    "estante de livros":    Regra("Móveis", "Estantes e Racks", 2),
    "rack de tv":           Regra("Móveis", "Estantes e Racks", 2),
    "prateleira":           Regra("Móveis", "Estantes e Racks", 1),
    "estante":              Regra("Móveis", "Estantes e Racks", 1),
    "rack":                 Regra("Móveis", "Estantes e Racks", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # DECORAÇÃO
    # ═══════════════════════════════════════════════════════════════════════

    "espelho decorativo":   Regra("Decoração", "Espelhos", 2),
    "espelho":              Regra("Decoração", "Espelhos", 1),
    "relogio de parede":    Regra("Decoração", "Relógios de Parede", 2),
    "relogio":              Regra("Decoração", "Relógios de Parede", 1),
    "vaso decorativo":      Regra("Decoração", "Vasos", 2),
    "cachepot":             Regra("Decoração", "Vasos", 1),
    "vaso":                 Regra("Decoração", "Vasos", 1),
    "quadro decorativo":    Regra("Decoração", "Quadros", 2),
    "poster":               Regra("Decoração", "Quadros", 1),
    "quadro":               Regra("Decoração", "Quadros", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # LAZER E CAMPING
    # ═══════════════════════════════════════════════════════════════════════

    "piscina infantil":     Regra("Lazer e Camping", "Piscinas e Acessórios", 2),
    "boia de piscina":      Regra("Lazer e Camping", "Piscinas e Acessórios", 2),
    "inflavel de piscina":  Regra("Lazer e Camping", "Piscinas e Acessórios", 2),
    "piscina":              Regra("Lazer e Camping", "Piscinas e Acessórios", 1),
    "caixa termica":        Regra("Lazer e Camping", "Caixas Térmicas", 2),
    "cooler":               Regra("Lazer e Camping", "Caixas Térmicas", 1),
    "isopor":               Regra("Lazer e Camping", "Caixas Térmicas", 1),
    "barraca de camping":   Regra("Lazer e Camping", "Barracas", 2),
    "barraca de praia":     Regra("Lazer e Camping", "Barracas", 2),
    "barraca":              Regra("Lazer e Camping", "Barracas", 1),
    "cadeira de praia":     Regra("Lazer e Camping", "Cadeiras de Praia", 2),
    "cadeira dobravel":     Regra("Lazer e Camping", "Cadeiras de Praia", 2),

    # ═══════════════════════════════════════════════════════════════════════
    # FERRAMENTAS E FERRAGENS
    # ═══════════════════════════════════════════════════════════════════════

    "furadeira":            Regra("Ferramentas e Ferragens", "Elétricas", 1),
    "esmerilhadeira":       Regra("Ferramentas e Ferragens", "Elétricas", 1),
    "parafusadeira":        Regra("Ferramentas e Ferragens", "Elétricas", 1),
    "serra circular":       Regra("Ferramentas e Ferragens", "Elétricas", 2),
    "lixadeira":            Regra("Ferramentas e Ferragens", "Elétricas", 1),
    "martelo":              Regra("Ferramentas e Ferragens", "Manuais", 1),
    "chave de fenda":       Regra("Ferramentas e Ferragens", "Manuais", 2),
    "alicate":              Regra("Ferramentas e Ferragens", "Manuais", 1),
    "chave inglesa":        Regra("Ferramentas e Ferragens", "Manuais", 2),
    "serrote":              Regra("Ferramentas e Ferragens", "Manuais", 1),
    "trena":                Regra("Ferramentas e Ferragens", "Medição", 1),
    "nivel de bolha":       Regra("Ferramentas e Ferragens", "Medição", 2),
    "paquimetro":           Regra("Ferramentas e Ferragens", "Medição", 1),
    "cadeado":              Regra("Ferramentas e Ferragens", "Ferragens e Cadeados", 1),
    "dobradica":            Regra("Ferramentas e Ferragens", "Ferragens e Cadeados", 1),
    "parafuso":             Regra("Ferramentas e Ferragens", "Ferragens e Cadeados", 1),
    "prego":                Regra("Ferramentas e Ferragens", "Ferragens e Cadeados", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # MATERIAIS DE CONSTRUÇÃO
    # ═══════════════════════════════════════════════════════════════════════

    "tinta latex":          Regra("Materiais de Construção", "Pintura", 2),
    "tinta acrilica":       Regra("Materiais de Construção", "Pintura", 2),
    "massa corrida":        Regra("Materiais de Construção", "Pintura", 2),
    "rolo de pintura":      Regra("Materiais de Construção", "Pintura", 2),
    "pincel de pintura":    Regra("Materiais de Construção", "Pintura", 2),
    "verniz":               Regra("Materiais de Construção", "Pintura", 1),
    "tinta":                Regra("Materiais de Construção", "Pintura", 1),
    "pincel":               Regra("Materiais de Construção", "Pintura", 1),
    "torneira":             Regra("Materiais de Construção", "Hidráulica", 1),
    "registro de agua":     Regra("Materiais de Construção", "Hidráulica", 2),
    "sifao":                Regra("Materiais de Construção", "Hidráulica", 1),
    "tubo pvc":             Regra("Materiais de Construção", "Hidráulica", 2),
    "cano":                 Regra("Materiais de Construção", "Hidráulica", 1),
    "fio eletrico":         Regra("Materiais de Construção", "Elétrica", 2),
    "cabo eletrico":        Regra("Materiais de Construção", "Elétrica", 2),
    "tomada eletrica":      Regra("Materiais de Construção", "Elétrica", 2),
    "interruptor":          Regra("Materiais de Construção", "Elétrica", 1),
    "disjuntor":            Regra("Materiais de Construção", "Elétrica", 1),
    "lampada led":          Regra("Materiais de Construção", "Elétrica", 2),
    "lampada":              Regra("Materiais de Construção", "Elétrica", 1),
    "led":                  Regra("Materiais de Construção", "Elétrica", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # ELETRO E ELETRÔNICOS
    # ═══════════════════════════════════════════════════════════════════════

    "liquidificador":       Regra("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "batedeira":            Regra("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "cafeteira":            Regra("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "sanduicheira":         Regra("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "ventilador":           Regra("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "ferro de passar":      Regra("Eletro e Eletrônicos", "Eletroportáteis", 2),
    "aspirador de po":      Regra("Eletro e Eletrônicos", "Eletroportáteis", 2),
    "micro-ondas":          Regra("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "multiprocessador":     Regra("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "airfryer":             Regra("Eletro e Eletrônicos", "Eletroportáteis", 1),
    "cabo usb":             Regra("Eletro e Eletrônicos", "Cabos e Carregadores", 2),
    "cabo hdmi":            Regra("Eletro e Eletrônicos", "Cabos e Carregadores", 2),
    "carregador de celular": Regra("Eletro e Eletrônicos", "Cabos e Carregadores", 2),
    "carregador portatil":  Regra("Eletro e Eletrônicos", "Cabos e Carregadores", 2),
    "carregador":           Regra("Eletro e Eletrônicos", "Cabos e Carregadores", 1),
    "cabo":                 Regra("Eletro e Eletrônicos", "Cabos e Carregadores", 1),
    "caixa de som bluetooth": Regra("Eletro e Eletrônicos", "Áudio e Som", 3),
    "fone de ouvido":       Regra("Eletro e Eletrônicos", "Áudio e Som", 2),
    "headphone":            Regra("Eletro e Eletrônicos", "Áudio e Som", 1),
    "headset":              Regra("Eletro e Eletrônicos", "Áudio e Som", 1),
    "caixa de som":         Regra("Eletro e Eletrônicos", "Áudio e Som", 2),
    "capa de celular":      Regra("Eletro e Eletrônicos", "Acessórios de Celular", 2),
    "pelicula de celular":  Regra("Eletro e Eletrônicos", "Acessórios de Celular", 2),
    "suporte celular":      Regra("Eletro e Eletrônicos", "Acessórios de Celular", 2),
    "acessorio celular":    Regra("Eletro e Eletrônicos", "Acessórios de Celular", 2),
    "pelicula":             Regra("Eletro e Eletrônicos", "Acessórios de Celular", 1),
    "pilha alcalina":       Regra("Eletro e Eletrônicos", "Pilhas e Baterias", 2),
    "bateria recarregavel": Regra("Eletro e Eletrônicos", "Pilhas e Baterias", 2),
    "pilha":                Regra("Eletro e Eletrônicos", "Pilhas e Baterias", 1),

    # ═══════════════════════════════════════════════════════════════════════
    # AUTOMOTIVO / BRINQUEDOS / VESTUÁRIO / TABACARIA / CAMA MESA BANHO / PADARIA
    # ═══════════════════════════════════════════════════════════════════════

    "capacete moto":        Regra("Automotivo e Moto", "Capacetes", 2),
    "capacete":             Regra("Automotivo e Moto", "Capacetes", 1),
    "boneca barbie":        Regra("Brinquedos", "Bonecas", 2),
    "boneca":               Regra("Brinquedos", "Bonecas", 1),
    "carrinho hot wheels":  Regra("Brinquedos", "Carrinhos e Pistas", 3),
    "pista de corrida":     Regra("Brinquedos", "Carrinhos e Pistas", 2),
    "carrinho de brinquedo": Regra("Brinquedos", "Carrinhos e Pistas", 2),
    "jogo de tabuleiro":    Regra("Brinquedos", "Jogos de Tabuleiro", 2),
    "xadrez":               Regra("Brinquedos", "Jogos de Tabuleiro", 1),
    "pelucia":              Regra("Brinquedos", "Pelúcias", 1),
    "ursinho de pelucia":   Regra("Brinquedos", "Pelúcias", 2),
    "chinelo havaianas":    Regra("Vestuário e Calçados", "Chinelos e Sandálias", 2),
    "havaianas":            Regra("Vestuário e Calçados", "Chinelos e Sandálias", 1),
    "sandalia feminina":    Regra("Vestuário e Calçados", "Chinelos e Sandálias", 2),
    "chinelo":              Regra("Vestuário e Calçados", "Chinelos e Sandálias", 1),
    "sandalia":             Regra("Vestuário e Calçados", "Chinelos e Sandálias", 1),
    "calcinha":             Regra("Vestuário e Calçados", "Peças Íntimas", 1),
    "cueca":                Regra("Vestuário e Calçados", "Peças Íntimas", 1),
    "sutia":                Regra("Vestuário e Calçados", "Peças Íntimas", 1),
    "meia":                 Regra("Vestuário e Calçados", "Peças Íntimas", 1),
    "camiseta":             Regra("Vestuário e Calçados", "Roupas", 1),
    "blusa":                Regra("Vestuário e Calçados", "Roupas", 1),
    "calca jeans":          Regra("Vestuário e Calçados", "Roupas", 2),
    "capa de chuva":        Regra("Vestuário e Calçados", "Capas de Chuva", 2),
    "guarda chuva":         Regra("Vestuário e Calçados", "Capas de Chuva", 2),
    "poncho":               Regra("Vestuário e Calçados", "Capas de Chuva", 1),
    "cigarro eletronico":   Regra("Tabacaria", "Cigarros", 2),
    "cigarro":              Regra("Tabacaria", "Cigarros", 1),
    "isqueiro":             Regra("Tabacaria", "Isqueiros e Fósforos", 1),
    "fosforo":              Regra("Tabacaria", "Isqueiros e Fósforos", 1),
    "toalha de banho":      Regra("Cama, Mesa e Banho", "Toalhas", 2),
    "toalha de rosto":      Regra("Cama, Mesa e Banho", "Toalhas", 2),
    "jogo de toalhas":      Regra("Cama, Mesa e Banho", "Toalhas", 2),
    "toalha":               Regra("Cama, Mesa e Banho", "Toalhas", 1),
    "tapete de banheiro":   Regra("Cama, Mesa e Banho", "Tapetes", 2),
    "tapete sala":          Regra("Cama, Mesa e Banho", "Tapetes", 2),
    "tapete":               Regra("Cama, Mesa e Banho", "Tapetes", 1),
    "cortina blackout":     Regra("Cama, Mesa e Banho", "Cortinas e Varões", 2),
    "varao de cortina":     Regra("Cama, Mesa e Banho", "Cortinas e Varões", 2),
    "cortina":              Regra("Cama, Mesa e Banho", "Cortinas e Varões", 1),
    "pao de forma":         Regra("Padaria e Lanchonete", "Pães e Salgados", 2, _TOKENS_UTENSILIO),
    "baguete":              Regra("Padaria e Lanchonete", "Pães e Salgados", 1, _TOKENS_UTENSILIO),
    "coxinha":              Regra("Padaria e Lanchonete", "Pães e Salgados", 1, _TOKENS_UTENSILIO),
    "kibe":                 Regra("Padaria e Lanchonete", "Pães e Salgados", 1, _TOKENS_UTENSILIO),
    "salgado":              Regra("Padaria e Lanchonete", "Pães e Salgados", 1, _TOKENS_UTENSILIO),
    "pao":                  Regra("Padaria e Lanchonete", "Pães e Salgados", 1, _TOKENS_UTENSILIO),
    "bolo de chocolate":    Regra("Padaria e Lanchonete", "Bolos e Tortas", 2, _TOKENS_UTENSILIO),
    "torta doce":           Regra("Padaria e Lanchonete", "Bolos e Tortas", 2, _TOKENS_UTENSILIO),
    "bolo":                 Regra("Padaria e Lanchonete", "Bolos e Tortas", 1, _TOKENS_UTENSILIO),
    "torta":                Regra("Padaria e Lanchonete", "Bolos e Tortas", 1, _TOKENS_UTENSILIO),
    "refeicao pronta":      Regra("Padaria e Lanchonete", "Refeições Prontas", 2, _TOKENS_UTENSILIO),
    "marmita":              Regra("Padaria e Lanchonete", "Refeições Prontas", 1, _TOKENS_UTENSILIO),
    "sanduiche":            Regra("Padaria e Lanchonete", "Lanches Rápidos", 1, _TOKENS_UTENSILIO),
    "hamburguer":           Regra("Padaria e Lanchonete", "Lanches Rápidos", 1, _TOKENS_UTENSILIO),
    "lanche":               Regra("Padaria e Lanchonete", "Lanches Rápidos", 1, _TOKENS_UTENSILIO),
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

    normalizado = normalizar(descricao)
    palavras = normalizado.split()
    conjunto_tokens = set(palavras)

    bigramas  = {palavras[i] + " " + words[i+1]             for i in range(len(palavras) - 1)}
    trigramas = {palavras[i] + " " + words[i+1] + " " + words[i+2] for i in range(len(palavras) - 2)}
    todos_os_termos = conjunto_tokens | bigramas | trigramas

    # Acumular scores por (grupo, subgrupo)
    pontuacoes: dict[tuple[str, str], int] = {}

    for termo, regra in REGRAS_PALAVRAS_CHAVE.items():
        if termo not in all_terms:
            continue

        # Verificar veto contextual
        if regra.vetar_se and regra.vetar_se & conjunto_tokens:
            vetado_por = regra.vetar_se & conjunto_tokens
            logger.debug(
                f"Regra '{termo}' → {regra.grupo}/{regra.subgrupo} "
                f"VETADA por tokens: {vetado_por} em '{descricao[:60]}'"
            )
            continue

        chave = (regra.grupo, regra.subgrupo)
        pontuacoes[chave] = pontuacoes.get(key, 0) + regra.pontuacao

    if not pontuacoes:
        return None

    best_chave = max(pontuacoes, key=lambda k: pontuacoes[k])
    melhor_pontuacao = scores[melhor_chave]

    logger.debug(
        f"Keywords → {melhor_chave[0]}/{melhor_chave[1]} "
        f"(score={melhor_pontuacao}, todos={pontuacoes}) "
        f"para '{descricao[:60]}'"
    )

    return {"grupo": melhor_chave[0], "subgrupo": melhor_chave[1]}
