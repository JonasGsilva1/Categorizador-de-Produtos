"""
Camada 3 do Funil: Classificador determinístico por palavras-chave.

Substitui o LLM Gemini para produtos com termos inequívocos.
Usa normalização de texto (remoção de acentos, lowercase, sem pontuação)
e verifica unigramas e bigramas contra um dicionário de regras.

Regras mais específicas (bigramas) têm prioridade sobre as genéricas (unigramas)
pois o dicionário é percorrido na ordem de inserção (Python 3.7+).
"""

import re
import unicodedata
import logging

logger = logging.getLogger(__name__)


def normalize(text: str) -> str:
    """
    Normaliza texto para comparação: remove acentos, converte para lowercase,
    substitui pontuação por espaços e colapsa espaços múltiplos.
    """
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Dicionário de regras — bigramas ANTES dos unigramas para maior precisão
# ---------------------------------------------------------------------------
KEYWORD_RULES: dict[str, tuple[str, str]] = {
    # ── Bebidas ─────────────────────────────────────────────────────────────
    # Vinhos
    "vinho tinto": ("Bebidas", "Vinhos"),
    "vinho branco": ("Bebidas", "Vinhos"),
    "vinho rose": ("Bebidas", "Vinhos"),
    "vinho verde": ("Bebidas", "Vinhos"),
    "vinho suave": ("Bebidas", "Vinhos"),
    "espumante": ("Bebidas", "Vinhos"),
    "vinho": ("Bebidas", "Vinhos"),
    # Cervejas
    "cerveja": ("Bebidas", "Cervejas"),
    "cerv": ("Bebidas", "Cervejas"),
    "heineken": ("Bebidas", "Cervejas"),
    "skol": ("Bebidas", "Cervejas"),
    "brahma": ("Bebidas", "Cervejas"),
    "itaipava": ("Bebidas", "Cervejas"),
    "budweiser": ("Bebidas", "Cervejas"),
    "amstel": ("Bebidas", "Cervejas"),
    "corona": ("Bebidas", "Cervejas"),
    "stella artois": ("Bebidas", "Cervejas"),
    "petra": ("Bebidas", "Cervejas"),
    # Refrigerantes
    "refrigerante": ("Bebidas", "Refrigerantes"),
    "coca cola": ("Bebidas", "Refrigerantes"),
    "pepsi": ("Bebidas", "Refrigerantes"),
    "guarana": ("Bebidas", "Refrigerantes"),
    "fanta": ("Bebidas", "Refrigerantes"),
    "sprite": ("Bebidas", "Refrigerantes"),
    "schweppes": ("Bebidas", "Refrigerantes"),
    # Sucos e Chás
    "suco de": ("Bebidas", "Sucos e Chás"),
    "nectar de": ("Bebidas", "Sucos e Chás"),
    "cha gelado": ("Bebidas", "Sucos e Chás"),
    "cha verde": ("Bebidas", "Sucos e Chás"),
    "cha preto": ("Bebidas", "Sucos e Chás"),
    "isotonioco": ("Bebidas", "Sucos e Chás"),
    "powerade": ("Bebidas", "Sucos e Chás"),
    "gatorade": ("Bebidas", "Sucos e Chás"),
    "suco": ("Bebidas", "Sucos e Chás"),
    "nectar": ("Bebidas", "Sucos e Chás"),
    "isotoniico": ("Bebidas", "Sucos e Chás"),
    "isotônico": ("Bebidas", "Sucos e Chás"),
    # Água
    "agua mineral": ("Bebidas", "Água"),
    "agua com gas": ("Bebidas", "Água"),
    "agua sem gas": ("Bebidas", "Água"),
    "agua": ("Bebidas", "Água"),
    # Destilados e Ice
    "whisky": ("Bebidas", "Destilados e Ice"),
    "whiskey": ("Bebidas", "Destilados e Ice"),
    "vodka": ("Bebidas", "Destilados e Ice"),
    "cachaca": ("Bebidas", "Destilados e Ice"),
    "rum": ("Bebidas", "Destilados e Ice"),
    "gin": ("Bebidas", "Destilados e Ice"),
    "tequila": ("Bebidas", "Destilados e Ice"),
    "licor": ("Bebidas", "Destilados e Ice"),
    "conhaque": ("Bebidas", "Destilados e Ice"),
    "ice": ("Bebidas", "Destilados e Ice"),
    "destilado": ("Bebidas", "Destilados e Ice"),
    # Energéticos
    "energetico": ("Bebidas", "Energéticos"),
    "red bull": ("Bebidas", "Energéticos"),
    "monster": ("Bebidas", "Energéticos"),
    "tnt energy": ("Bebidas", "Energéticos"),
    "burn": ("Bebidas", "Energéticos"),
}

# Continuação do dicionário KEYWORD_RULES
_KEYWORD_RULES_EXTRA: dict[str, tuple[str, str]] = {
    # ── Limpeza ─────────────────────────────────────────────────────────────
    # Utensílios de Limpeza
    "vassoura": ("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)"),
    "rodo": ("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)"),
    "esponja de limpeza": ("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)"),
    "balde": ("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)"),
    "pano de chao": ("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)"),
    "flanela": ("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)"),
    "mop": ("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)"),
    "esponja": ("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)"),
    "luva de borracha": ("Limpeza", "Utensílios de Limpeza (Vassouras/Rodos)"),
    # Produtos Químicos
    "detergente": ("Limpeza", "Produtos Químicos"),
    "desinfetante": ("Limpeza", "Produtos Químicos"),
    "alvejante": ("Limpeza", "Produtos Químicos"),
    "sabao em po": ("Limpeza", "Produtos Químicos"),
    "sabao liquido": ("Limpeza", "Produtos Químicos"),
    "amaciante": ("Limpeza", "Produtos Químicos"),
    "multiuso": ("Limpeza", "Produtos Químicos"),
    "limpa vidro": ("Limpeza", "Produtos Químicos"),
    "ajax": ("Limpeza", "Produtos Químicos"),
    "omo": ("Limpeza", "Produtos Químicos"),
    "ariel": ("Limpeza", "Produtos Químicos"),
    "tira mofo": ("Limpeza", "Produtos Químicos"),
    "cloro": ("Limpeza", "Produtos Químicos"),
    "hipoclorito": ("Limpeza", "Produtos Químicos"),
    # Lixeiras e Cestos
    "lixeira": ("Limpeza", "Lixeiras e Cestos"),
    "cesto de lixo": ("Limpeza", "Lixeiras e Cestos"),
    "organizador de cozinha": ("Limpeza", "Organização"),
    "organizador plastico": ("Limpeza", "Organização"),
    "cesto": ("Limpeza", "Lixeiras e Cestos"),
    "organizador": ("Limpeza", "Organização"),
    # ── Alimentos (Mercearia) ────────────────────────────────────────────────
    # Biscoitos e Salgadinhos
    "biscoito": ("Alimentos (Mercearia)", "Biscoitos e Salgadinhos"),
    "bolacha": ("Alimentos (Mercearia)", "Biscoitos e Salgadinhos"),
    "salgadinho": ("Alimentos (Mercearia)", "Biscoitos e Salgadinhos"),
    "chips": ("Alimentos (Mercearia)", "Biscoitos e Salgadinhos"),
    "amendoim": ("Alimentos (Mercearia)", "Biscoitos e Salgadinhos"),
    "batatinha": ("Alimentos (Mercearia)", "Biscoitos e Salgadinhos"),
    "snack": ("Alimentos (Mercearia)", "Biscoitos e Salgadinhos"),
    "torrada": ("Alimentos (Mercearia)", "Biscoitos e Salgadinhos"),
    # Doces e Sobremesas
    "chocolate": ("Alimentos (Mercearia)", "Doces e Sobremesas"),
    "bala": ("Alimentos (Mercearia)", "Doces e Sobremesas"),
    "chiclete": ("Alimentos (Mercearia)", "Doces e Sobremesas"),
    "pirulito": ("Alimentos (Mercearia)", "Doces e Sobremesas"),
    "bombom": ("Alimentos (Mercearia)", "Doces e Sobremesas"),
    "geleia": ("Alimentos (Mercearia)", "Doces e Sobremesas"),
    "mel": ("Alimentos (Mercearia)", "Doces e Sobremesas"),
    "doce de leite": ("Alimentos (Mercearia)", "Doces e Sobremesas"),
    "achocolatado": ("Alimentos (Mercearia)", "Doces e Sobremesas"),
    # Conservas e Molhos
    "atum": ("Alimentos (Mercearia)", "Conservas e Molhos"),
    "sardinha": ("Alimentos (Mercearia)", "Conservas e Molhos"),
    "extrato de tomate": ("Alimentos (Mercearia)", "Conservas e Molhos"),
    "molho de tomate": ("Alimentos (Mercearia)", "Conservas e Molhos"),
    "milho em lata": ("Alimentos (Mercearia)", "Conservas e Molhos"),
    "ervilha em lata": ("Alimentos (Mercearia)", "Conservas e Molhos"),
    "creme de leite": ("Alimentos (Mercearia)", "Conservas e Molhos"),
    "leite condensado": ("Alimentos (Mercearia)", "Conservas e Molhos"),
    "conserva": ("Alimentos (Mercearia)", "Conservas e Molhos"),
    "molho": ("Alimentos (Mercearia)", "Conservas e Molhos"),
    # Grãos e Massas
    "macarrao": ("Alimentos (Mercearia)", "Grãos e Massas"),
    "arroz": ("Alimentos (Mercearia)", "Grãos e Massas"),
    "feijao": ("Alimentos (Mercearia)", "Grãos e Massas"),
    "lentilha": ("Alimentos (Mercearia)", "Grãos e Massas"),
    "grao de bico": ("Alimentos (Mercearia)", "Grãos e Massas"),
    "fuba": ("Alimentos (Mercearia)", "Grãos e Massas"),
    "farinha de trigo": ("Alimentos (Mercearia)", "Grãos e Massas"),
    "farinha de mandioca": ("Alimentos (Mercearia)", "Grãos e Massas"),
    "aveia": ("Alimentos (Mercearia)", "Grãos e Massas"),
    "granola": ("Alimentos (Mercearia)", "Grãos e Massas"),
    "farinha": ("Alimentos (Mercearia)", "Grãos e Massas"),
    "massa": ("Alimentos (Mercearia)", "Grãos e Massas"),
    # Óleos e Temperos
    "azeite": ("Alimentos (Mercearia)", "Óleos e Temperos"),
    "oleo de soja": ("Alimentos (Mercearia)", "Óleos e Temperos"),
    "oleo de girassol": ("Alimentos (Mercearia)", "Óleos e Temperos"),
    "vinagre": ("Alimentos (Mercearia)", "Óleos e Temperos"),
    "sal refinado": ("Alimentos (Mercearia)", "Óleos e Temperos"),
    "pimenta do reino": ("Alimentos (Mercearia)", "Óleos e Temperos"),
    "tempero pronto": ("Alimentos (Mercearia)", "Óleos e Temperos"),
    "caldo de": ("Alimentos (Mercearia)", "Óleos e Temperos"),
    "oleo": ("Alimentos (Mercearia)", "Óleos e Temperos"),
    "tempero": ("Alimentos (Mercearia)", "Óleos e Temperos"),
    # Pipoca
    "pipoca": ("Alimentos (Mercearia)", "Pipoca"),
}
KEYWORD_RULES.update(_KEYWORD_RULES_EXTRA)

_KEYWORD_RULES_EXTRA2: dict[str, tuple[str, str]] = {
    # ── Frios e Congelados ───────────────────────────────────────────────────
    "sorvete": ("Frios e Congelados", "Sorvetes e Picolés"),
    "picole": ("Frios e Congelados", "Sorvetes e Picolés"),
    "gelato": ("Frios e Congelados", "Sorvetes e Picolés"),
    "frango congelado": ("Frios e Congelados", "Carnes e Aves"),
    "carne bovina": ("Frios e Congelados", "Carnes e Aves"),
    "linguica": ("Frios e Congelados", "Carnes e Aves"),
    "salsicha": ("Frios e Congelados", "Carnes e Aves"),
    "presunto": ("Frios e Congelados", "Carnes e Aves"),
    "mussarela": ("Frios e Congelados", "Carnes e Aves"),
    "queijo": ("Frios e Congelados", "Carnes e Aves"),
    "frango": ("Frios e Congelados", "Carnes e Aves"),
    "carne": ("Frios e Congelados", "Carnes e Aves"),
    "lasanha congelada": ("Frios e Congelados", "Pratos Prontos"),
    "pizza congelada": ("Frios e Congelados", "Pratos Prontos"),
    "prato pronto": ("Frios e Congelados", "Pratos Prontos"),
    # ── Higiene e Cuidados Pessoais ──────────────────────────────────────────
    "shampoo": ("Higiene e Cuidados Pessoais", "Cabelo"),
    "condicionador": ("Higiene e Cuidados Pessoais", "Cabelo"),
    "creme de cabelo": ("Higiene e Cuidados Pessoais", "Cabelo"),
    "tinta de cabelo": ("Higiene e Cuidados Pessoais", "Cabelo"),
    "mascara capilar": ("Higiene e Cuidados Pessoais", "Cabelo"),
    "sabonete": ("Higiene e Cuidados Pessoais", "Sabonetes"),
    "sabao liquido para maos": ("Higiene e Cuidados Pessoais", "Sabonetes"),
    "desodorante": ("Higiene e Cuidados Pessoais", "Desodorantes"),
    "antitranspirante": ("Higiene e Cuidados Pessoais", "Desodorantes"),
    "escova de dente": ("Higiene e Cuidados Pessoais", "Higiene Oral"),
    "pasta de dente": ("Higiene e Cuidados Pessoais", "Higiene Oral"),
    "fio dental": ("Higiene e Cuidados Pessoais", "Higiene Oral"),
    "enxaguante bucal": ("Higiene e Cuidados Pessoais", "Higiene Oral"),
    "dentifricio": ("Higiene e Cuidados Pessoais", "Higiene Oral"),
    "absorvente": ("Higiene e Cuidados Pessoais", "Absorventes"),
    "fralda": ("Higiene e Cuidados Pessoais", "Absorventes"),
    "lenco umedecido": ("Higiene e Cuidados Pessoais", "Absorventes"),
    "creme hidratante": ("Higiene e Cuidados Pessoais", "Cosméticos"),
    "maquiagem": ("Higiene e Cuidados Pessoais", "Cosméticos"),
    "batom": ("Higiene e Cuidados Pessoais", "Cosméticos"),
    "perfume": ("Higiene e Cuidados Pessoais", "Cosméticos"),
    "protetor solar": ("Higiene e Cuidados Pessoais", "Cosméticos"),
    "base maquiagem": ("Higiene e Cuidados Pessoais", "Cosméticos"),
    "hidratante": ("Higiene e Cuidados Pessoais", "Cosméticos"),
    # ── Bazar e Utilidades ───────────────────────────────────────────────────
    "panela de pressao": ("Bazar e Utilidades", "Panelas"),
    "frigideira": ("Bazar e Utilidades", "Panelas"),
    "wok": ("Bazar e Utilidades", "Panelas"),
    "cacarola": ("Bazar e Utilidades", "Panelas"),
    "panela": ("Bazar e Utilidades", "Panelas"),
    "pote plastico": ("Bazar e Utilidades", "Recipientes de Plástico"),
    "vasilha plastica": ("Bazar e Utilidades", "Recipientes de Plástico"),
    "pote hermetico": ("Bazar e Utilidades", "Recipientes de Plástico"),
    "tupperware": ("Bazar e Utilidades", "Recipientes de Plástico"),
    "taça de vidro": ("Bazar e Utilidades", "Vidros e Taças"),
    "copo de vidro": ("Bazar e Utilidades", "Vidros e Taças"),
    "jarra de vidro": ("Bazar e Utilidades", "Vidros e Taças"),
    "garrafa de vidro": ("Bazar e Utilidades", "Vidros e Taças"),
    "escorredor de pratos": ("Bazar e Utilidades", "Utensílios de Cozinha"),
    "espatula de cozinha": ("Bazar e Utilidades", "Utensílios de Cozinha"),
    "concha de servir": ("Bazar e Utilidades", "Utensílios de Cozinha"),
    "faca de cozinha": ("Bazar e Utilidades", "Utensílios de Cozinha"),
    "tabua de corte": ("Bazar e Utilidades", "Utensílios de Cozinha"),
    "colher de pau": ("Bazar e Utilidades", "Utensílios de Cozinha"),
    "utensilios de cozinha": ("Bazar e Utilidades", "Utensílios de Cozinha"),
    "garrafa termica": ("Bazar e Utilidades", "Garrafas Térmicas"),
    "squeeze": ("Bazar e Utilidades", "Garrafas Térmicas"),
    "copo termico": ("Bazar e Utilidades", "Garrafas Térmicas"),
    "jogo de talheres": ("Bazar e Utilidades", "Talheres"),
    "colher de mesa": ("Bazar e Utilidades", "Talheres"),
    "garfo": ("Bazar e Utilidades", "Talheres"),
    "talher": ("Bazar e Utilidades", "Talheres"),
}
KEYWORD_RULES.update(_KEYWORD_RULES_EXTRA2)

_KEYWORD_RULES_EXTRA3: dict[str, tuple[str, str]] = {
    # ── Móveis ───────────────────────────────────────────────────────────────
    "cadeira de escritorio": ("Móveis", "Cadeiras e Poltronas"),
    "poltrona": ("Móveis", "Cadeiras e Poltronas"),
    "banqueta": ("Móveis", "Cadeiras e Poltronas"),
    "cadeira": ("Móveis", "Cadeiras e Poltronas"),
    "mesa de jantar": ("Móveis", "Mesas"),
    "mesa de escritorio": ("Móveis", "Mesas"),
    "mesa de centro": ("Móveis", "Mesas"),
    "mesinha": ("Móveis", "Mesas"),
    "mesa": ("Móveis", "Mesas"),
    "colchao": ("Móveis", "Colchões e Camas"),
    "cama box": ("Móveis", "Colchões e Camas"),
    "beliche": ("Móveis", "Colchões e Camas"),
    "berco": ("Móveis", "Colchões e Camas"),
    "cama": ("Móveis", "Colchões e Camas"),
    "guarda roupa": ("Móveis", "Armários e Roupeiros"),
    "guarda-roupa": ("Móveis", "Armários e Roupeiros"),
    "comoda": ("Móveis", "Armários e Roupeiros"),
    "armario": ("Móveis", "Armários e Roupeiros"),
    "estante de livros": ("Móveis", "Estantes e Racks"),
    "rack de tv": ("Móveis", "Estantes e Racks"),
    "prateleira": ("Móveis", "Estantes e Racks"),
    "estante": ("Móveis", "Estantes e Racks"),
    "rack": ("Móveis", "Estantes e Racks"),
    # ── Decoração ────────────────────────────────────────────────────────────
    "espelho decorativo": ("Decoração", "Espelhos"),
    "espelho": ("Decoração", "Espelhos"),
    "relogio de parede": ("Decoração", "Relógios de Parede"),
    "relogio": ("Decoração", "Relógios de Parede"),
    "vaso decorativo": ("Decoração", "Vasos"),
    "cachepot": ("Decoração", "Vasos"),
    "vaso": ("Decoração", "Vasos"),
    "quadro decorativo": ("Decoração", "Quadros"),
    "poster": ("Decoração", "Quadros"),
    "quadro": ("Decoração", "Quadros"),
    # ── Lazer e Camping ──────────────────────────────────────────────────────
    "piscina infantil": ("Lazer e Camping", "Piscinas e Acessórios"),
    "boia de piscina": ("Lazer e Camping", "Piscinas e Acessórios"),
    "inflavel de piscina": ("Lazer e Camping", "Piscinas e Acessórios"),
    "piscina": ("Lazer e Camping", "Piscinas e Acessórios"),
    "caixa termica": ("Lazer e Camping", "Caixas Térmicas"),
    "cooler": ("Lazer e Camping", "Caixas Térmicas"),
    "isopor": ("Lazer e Camping", "Caixas Térmicas"),
    "barraca de camping": ("Lazer e Camping", "Barracas"),
    "barraca de praia": ("Lazer e Camping", "Barracas"),
    "barraca": ("Lazer e Camping", "Barracas"),
    "cadeira de praia": ("Lazer e Camping", "Cadeiras de Praia"),
    "cadeira dobravel": ("Lazer e Camping", "Cadeiras de Praia"),
    # ── Ferramentas e Ferragens ──────────────────────────────────────────────
    "furadeira": ("Ferramentas e Ferragens", "Elétricas"),
    "esmerilhadeira": ("Ferramentas e Ferragens", "Elétricas"),
    "parafusadeira": ("Ferramentas e Ferragens", "Elétricas"),
    "serra circular": ("Ferramentas e Ferragens", "Elétricas"),
    "lixadeira": ("Ferramentas e Ferragens", "Elétricas"),
    "martelo": ("Ferramentas e Ferragens", "Manuais"),
    "chave de fenda": ("Ferramentas e Ferragens", "Manuais"),
    "alicate": ("Ferramentas e Ferragens", "Manuais"),
    "chave inglesa": ("Ferramentas e Ferragens", "Manuais"),
    "serrote": ("Ferramentas e Ferragens", "Manuais"),
    "trena": ("Ferramentas e Ferragens", "Medição"),
    "nivel de bolha": ("Ferramentas e Ferragens", "Medição"),
    "paquimetro": ("Ferramentas e Ferragens", "Medição"),
    "metro": ("Ferramentas e Ferragens", "Medição"),
    "cadeado": ("Ferramentas e Ferragens", "Ferragens e Cadeados"),
    "dobradica": ("Ferramentas e Ferragens", "Ferragens e Cadeados"),
    "parafuso": ("Ferramentas e Ferragens", "Ferragens e Cadeados"),
    "prego": ("Ferramentas e Ferragens", "Ferragens e Cadeados"),
    "ferragem": ("Ferramentas e Ferragens", "Ferragens e Cadeados"),
    # ── Materiais de Construção ───────────────────────────────────────────────
    "tinta latex": ("Materiais de Construção", "Pintura"),
    "tinta acrilica": ("Materiais de Construção", "Pintura"),
    "massa corrida": ("Materiais de Construção", "Pintura"),
    "rolo de pintura": ("Materiais de Construção", "Pintura"),
    "pincel de pintura": ("Materiais de Construção", "Pintura"),
    "verniz": ("Materiais de Construção", "Pintura"),
    "tinta": ("Materiais de Construção", "Pintura"),
    "pincel": ("Materiais de Construção", "Pintura"),
    "torneira": ("Materiais de Construção", "Hidráulica"),
    "registro de agua": ("Materiais de Construção", "Hidráulica"),
    "sifao": ("Materiais de Construção", "Hidráulica"),
    "tubo pvc": ("Materiais de Construção", "Hidráulica"),
    "cano": ("Materiais de Construção", "Hidráulica"),
    "fio eletrico": ("Materiais de Construção", "Elétrica"),
    "cabo eletrico": ("Materiais de Construção", "Elétrica"),
    "tomada eletrica": ("Materiais de Construção", "Elétrica"),
    "interruptor": ("Materiais de Construção", "Elétrica"),
    "disjuntor": ("Materiais de Construção", "Elétrica"),
    "lampada led": ("Materiais de Construção", "Elétrica"),
    "lampada": ("Materiais de Construção", "Elétrica"),
    "led": ("Materiais de Construção", "Elétrica"),
}
KEYWORD_RULES.update(_KEYWORD_RULES_EXTRA3)

_KEYWORD_RULES_EXTRA4: dict[str, tuple[str, str]] = {
    # ── Eletro e Eletrônicos ─────────────────────────────────────────────────
    "liquidificador": ("Eletro e Eletrônicos", "Eletroportáteis"),
    "batedeira": ("Eletro e Eletrônicos", "Eletroportáteis"),
    "cafeteira": ("Eletro e Eletrônicos", "Eletroportáteis"),
    "sanduicheira": ("Eletro e Eletrônicos", "Eletroportáteis"),
    "ventilador": ("Eletro e Eletrônicos", "Eletroportáteis"),
    "ferro de passar": ("Eletro e Eletrônicos", "Eletroportáteis"),
    "aspirador de po": ("Eletro e Eletrônicos", "Eletroportáteis"),
    "micro-ondas": ("Eletro e Eletrônicos", "Eletroportáteis"),
    "multiprocessador": ("Eletro e Eletrônicos", "Eletroportáteis"),
    "airfryer": ("Eletro e Eletrônicos", "Eletroportáteis"),
    "cabo usb": ("Eletro e Eletrônicos", "Cabos e Carregadores"),
    "cabo hdmi": ("Eletro e Eletrônicos", "Cabos e Carregadores"),
    "carregador de celular": ("Eletro e Eletrônicos", "Cabos e Carregadores"),
    "carregador portatil": ("Eletro e Eletrônicos", "Cabos e Carregadores"),
    "fonte de alimentacao": ("Eletro e Eletrônicos", "Cabos e Carregadores"),
    "carregador": ("Eletro e Eletrônicos", "Cabos e Carregadores"),
    "cabo": ("Eletro e Eletrônicos", "Cabos e Carregadores"),
    "caixa de som bluetooth": ("Eletro e Eletrônicos", "Áudio e Som"),
    "fone de ouvido": ("Eletro e Eletrônicos", "Áudio e Som"),
    "headphone": ("Eletro e Eletrônicos", "Áudio e Som"),
    "headset": ("Eletro e Eletrônicos", "Áudio e Som"),
    "alto-falante": ("Eletro e Eletrônicos", "Áudio e Som"),
    "caixa de som": ("Eletro e Eletrônicos", "Áudio e Som"),
    "capa de celular": ("Eletro e Eletrônicos", "Acessórios de Celular"),
    "pelicula de celular": ("Eletro e Eletrônicos", "Acessórios de Celular"),
    "suporte celular": ("Eletro e Eletrônicos", "Acessórios de Celular"),
    "acessorio celular": ("Eletro e Eletrônicos", "Acessórios de Celular"),
    "pelicula": ("Eletro e Eletrônicos", "Acessórios de Celular"),
    "pilha alcalina": ("Eletro e Eletrônicos", "Pilhas e Baterias"),
    "bateria recarregavel": ("Eletro e Eletrônicos", "Pilhas e Baterias"),
    "pilha": ("Eletro e Eletrônicos", "Pilhas e Baterias"),
    # ── Automotivo e Moto ────────────────────────────────────────────────────
    "capacete moto": ("Automotivo e Moto", "Capacetes"),
    "capacete": ("Automotivo e Moto", "Capacetes"),
    "acessorio moto": ("Automotivo e Moto", "Acessórios Moto"),
    "acessorio carro": ("Automotivo e Moto", "Acessórios Carro"),
    # ── Brinquedos ──────────────────────────────────────────────────────────
    "boneca barbie": ("Brinquedos", "Bonecas"),
    "boneca": ("Brinquedos", "Bonecas"),
    "carrinho hot wheels": ("Brinquedos", "Carrinhos e Pistas"),
    "pista de corrida": ("Brinquedos", "Carrinhos e Pistas"),
    "carrinho de brinquedo": ("Brinquedos", "Carrinhos e Pistas"),
    "jogo de tabuleiro": ("Brinquedos", "Jogos de Tabuleiro"),
    "xadrez": ("Brinquedos", "Jogos de Tabuleiro"),
    "dama jogo": ("Brinquedos", "Jogos de Tabuleiro"),
    "pelucia": ("Brinquedos", "Pelúcias"),
    "ursinho de pelucia": ("Brinquedos", "Pelúcias"),
    "brinquedo de praia": ("Brinquedos", "Praia e Piscina Infantil"),
    "brinquedo de piscina": ("Brinquedos", "Praia e Piscina Infantil"),
    # ── Vestuário e Calçados ─────────────────────────────────────────────────
    "chinelo havaianas": ("Vestuário e Calçados", "Chinelos e Sandálias"),
    "sandalia feminina": ("Vestuário e Calçados", "Chinelos e Sandálias"),
    "havaianas": ("Vestuário e Calçados", "Chinelos e Sandálias"),
    "chinelo": ("Vestuário e Calçados", "Chinelos e Sandálias"),
    "sandalia": ("Vestuário e Calçados", "Chinelos e Sandálias"),
    "calcinha": ("Vestuário e Calçados", "Peças Íntimas"),
    "cueca": ("Vestuário e Calçados", "Peças Íntimas"),
    "sutia": ("Vestuário e Calçados", "Peças Íntimas"),
    "meia": ("Vestuário e Calçados", "Peças Íntimas"),
    "roupa": ("Vestuário e Calçados", "Roupas"),
    "camiseta": ("Vestuário e Calçados", "Roupas"),
    "blusa": ("Vestuário e Calçados", "Roupas"),
    "calca jeans": ("Vestuário e Calçados", "Roupas"),
    "capa de chuva": ("Vestuário e Calçados", "Capas de Chuva"),
    "guarda chuva": ("Vestuário e Calçados", "Capas de Chuva"),
    "poncho": ("Vestuário e Calçados", "Capas de Chuva"),
    # ── Tabacaria ────────────────────────────────────────────────────────────
    "cigarro eletronico": ("Tabacaria", "Cigarros"),
    "narguilé": ("Tabacaria", "Cigarros"),
    "cigarro": ("Tabacaria", "Cigarros"),
    "isqueiro": ("Tabacaria", "Isqueiros e Fósforos"),
    "fosforo": ("Tabacaria", "Isqueiros e Fósforos"),
    # ── Cama, Mesa e Banho ───────────────────────────────────────────────────
    "toalha de banho": ("Cama, Mesa e Banho", "Toalhas"),
    "toalha de rosto": ("Cama, Mesa e Banho", "Toalhas"),
    "jogo de toalhas": ("Cama, Mesa e Banho", "Toalhas"),
    "toalha": ("Cama, Mesa e Banho", "Toalhas"),
    "tapete de banheiro": ("Cama, Mesa e Banho", "Tapetes"),
    "tapete sala": ("Cama, Mesa e Banho", "Tapetes"),
    "tapete": ("Cama, Mesa e Banho", "Tapetes"),
    "cortina blackout": ("Cama, Mesa e Banho", "Cortinas e Varões"),
    "varao de cortina": ("Cama, Mesa e Banho", "Cortinas e Varões"),
    "cortina": ("Cama, Mesa e Banho", "Cortinas e Varões"),
    # ── Padaria e Lanchonete ─────────────────────────────────────────────────
    "pao de forma": ("Padaria e Lanchonete", "Pães e Salgados"),
    "baguete": ("Padaria e Lanchonete", "Pães e Salgados"),
    "coxinha": ("Padaria e Lanchonete", "Pães e Salgados"),
    "kibe": ("Padaria e Lanchonete", "Pães e Salgados"),
    "salgado": ("Padaria e Lanchonete", "Pães e Salgados"),
    "pao": ("Padaria e Lanchonete", "Pães e Salgados"),
    "bolo de chocolate": ("Padaria e Lanchonete", "Bolos e Tortas"),
    "torta doce": ("Padaria e Lanchonete", "Bolos e Tortas"),
    "bolo": ("Padaria e Lanchonete", "Bolos e Tortas"),
    "torta": ("Padaria e Lanchonete", "Bolos e Tortas"),
    "refeicao pronta": ("Padaria e Lanchonete", "Refeições Prontas"),
    "marmita": ("Padaria e Lanchonete", "Refeições Prontas"),
    "sanduiche": ("Padaria e Lanchonete", "Lanches Rápidos"),
    "hamburguer": ("Padaria e Lanchonete", "Lanches Rápidos"),
    "lanche": ("Padaria e Lanchonete", "Lanches Rápidos"),
}
KEYWORD_RULES.update(_KEYWORD_RULES_EXTRA4)


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def classify_by_keywords(descricao: str) -> dict | None:
    """
    Classifica um produto por correspondência de palavras-chave/bigramas.

    O texto é normalizado antes da comparação (sem acentos, lowercase).
    Bigramas têm prioridade sobre unigramas por estarem primeiro no dicionário.

    Args:
        descricao: Descrição do produto a classificar.

    Returns:
        Dict ``{"grupo": str, "subgrupo": str}`` ou None se nenhum termo casar.
    """
    if not descricao or not descricao.strip():
        return None

    norm = normalize(descricao)
    words = norm.split()

    # Conjunto de unigramas + bigramas
    bigrams = {words[i] + " " + words[i + 1] for i in range(len(words) - 1)}
    all_terms = set(words) | bigrams

    for term, (grupo, subgrupo) in KEYWORD_RULES.items():
        if term in all_terms:
            logger.debug(
                f"Keyword match: '{term}' → {grupo}/{subgrupo} "
                f"(descrição: '{descricao[:60]}')"
            )
            return {"grupo": grupo, "subgrupo": subgrupo}

    return None
