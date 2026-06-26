import re

filepath = r"c:\Projetos\Categorizador\backend\app\services\keyword_classifier.py"
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

replacements = [
    ("class Rule:", "class Regra:"),
    (" Rule(", " Regra("),
    ("KEYWORD_RULES", "REGRAS_PALAVRAS_CHAVE"),
    ("_UTENSILIO_TOKENS", "_TOKENS_UTENSILIO"),
    ("score: int", "pontuacao: int"),
    ("veto_if: set", "vetar_se: set"),
    ("rule.score", "regra.pontuacao"),
    ("rule.veto_if", "regra.vetar_se"),
    ("rule.grupo", "regra.grupo"),
    ("rule.subgrupo", "regra.subgrupo"),
    ("def normalize(text: str) -> str:", "def normalizar(texto: str) -> str:"),
    ("text = ", "texto = "),
    ("return re.sub", "return re.sub"), # just alignment
    ("def classify_by_keywords(descricao: str) -> dict | None:", "def classify_by_keywords(descricao: str) -> dict | None:"),
    ("norm = normalize(descricao)", "normalizado = normalizar(descricao)"),
    ("norm.split()", "normalizado.split()"),
    ("words = ", "palavras = "),
    ("token_set = set(words)", "conjunto_tokens = set(palavras)"),
    ("words[i]", "palavras[i]"),
    ("len(words)", "len(palavras)"),
    ("bigrams  =", "bigramas  ="),
    ("trigrams =", "trigramas ="),
    ("all_terms = token_set | bigrams | trigrams", "todos_os_termos = conjunto_tokens | bigramas | trigramas"),
    ("scores:", "pontuacoes:"),
    ("scores =", "pontuacoes ="),
    ("for term, rule in", "for termo, regra in"),
    ("if term not", "if termo not"),
    ("token_set", "conjunto_tokens"),
    ("vetoed_by", "vetado_por"),
    ("Regra '{term}'", "Regra '{termo}'"),
    ("key =", "chave ="),
    ("best_key", "melhor_chave"),
    ("best_score", "melhor_pontuacao"),
    ("max(scores, key=lambda k: scores[k])", "max(pontuacoes, key=lambda k: pontuacoes[k])"),
    ("scores[key]", "pontuacoes[chave]"),
    ("scores.get", "pontuacoes.get"),
    ("scores)", "pontuacoes)"),
    ("scores}", "pontuacoes}"),
]

for old, new in replacements:
    content = content.replace(old, new)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Refactored keyword_classifier.py")
