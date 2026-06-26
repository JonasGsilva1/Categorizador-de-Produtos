"""
Leitura e escrita de arquivos .xlsx via Pandas.
- Leitura rápida com pd.read_excel em lote.
- Escrita usando pd.DataFrame.to_excel e xlsxwriter para manter formatação nativa.
"""

import io
import pandas as pd
from app.models import ProdutoEntrada, ProdutoSaida


def read_products(bytes_arquivo: bytes) -> list[ProdutoEntrada]:
    """
    Lê a planilha .xlsx usando Pandas e extrai os produtos.
    Espera colunas: Descrição, EAN, NCM (insensível a maiúsculas/minúsculas).
    Retorna lista de ProdutoEntrada com o índice da linha.
    """
    df = pd.read_excel(io.BytesIO(bytes_arquivo), engine="openpyxl")
    df.columns = df.columns.astype(str).str.strip().str.lower().str.replace("_", " ")

    apelidos_cabecalho = {
        "descricao": ["descrição", "descricao", "description", "desc", "produto", "nome"],
        "ean": ["ean", "gtin", "codigo de barras", "código de barras", "cod barras", "barcode"],
        "ncm": ["ncm", "cod ncm", "código ncm"],
    }
    
    mapa_colunas = {}
    for coluna in df.columns:
        for campo, apelidos in apelidos_cabecalho.items():
            if coluna in apelidos and campo not in mapa_colunas:
                mapa_colunas[coluna] = campo
                break
    
    df = df.rename(columns=mapa_colunas)
    
    if "descricao" not in df.columns:
        raise ValueError(
            "Coluna 'Descrição' não encontrada na planilha. "
            "Colunas aceitas: " + ", ".join(apelidos_cabecalho["descricao"])
        )

    if "ean" not in df.columns:
        df["ean"] = ""
    if "ncm" not in df.columns:
        df["ncm"] = ""
        
    df["descricao"] = df["descricao"].fillna("").astype(str).str.strip()
    df["ean"] = df["ean"].fillna("").astype(str).str.strip()
    df["ncm"] = df["ncm"].fillna("").astype(str).str.strip()
    
    df["ean"] = df["ean"].apply(lambda x: x[:-2] if x.endswith(".0") else x)
    df["ncm"] = df["ncm"].apply(lambda x: x[:-2] if x.endswith(".0") else x)
    
    produtos: list[ProdutoEntrada] = []
    for indice_linha, linha in df.iterrows():
        linha_excel = int(indice_linha) + 2
        if not linha["descricao"]:
            continue
        produtos.append(ProdutoEntrada(
            row_index=linha_excel,
            descricao=linha["descricao"],
            ean=linha["ean"],
            ncm=linha["ncm"],
        ))
        
    return produtos


def read_feedback_products(bytes_arquivo: bytes) -> list[dict]:
    """
    Lê a planilha de retroalimentação (corrigida manualmente) via Pandas.
    """
    df = pd.read_excel(io.BytesIO(bytes_arquivo), engine="openpyxl")
    df.columns = df.columns.astype(str).str.strip().str.lower().str.replace("_", " ")

    apelidos_cabecalho = {
        "descricao": ["descrição", "descricao", "description", "desc", "produto", "nome"],
        "ean": ["ean", "gtin", "codigo de barras", "código de barras"],
        "ncm": ["ncm", "cod ncm", "código ncm"],
        "grupo": ["grupo", "category", "categoria"],
        "subgrupo": ["subgrupo", "subcategoria", "subcategory", "sub grupo"],
    }
    
    mapa_colunas = {}
    for coluna in df.columns:
        for campo, apelidos in apelidos_cabecalho.items():
            if coluna in apelidos and campo not in mapa_colunas:
                mapa_colunas[coluna] = campo
                break
                
    df = df.rename(columns=mapa_colunas)
    
    obrigatorios = ["descricao", "grupo", "subgrupo"]
    ausentes = [f for f in obrigatorios if f not in df.columns]
    if ausentes:
        raise ValueError(f"Colunas obrigatórias não encontradas: {ausentes}")

    if "ean" not in df.columns:
        df["ean"] = ""
    if "ncm" not in df.columns:
        df["ncm"] = ""

    df["descricao"] = df["descricao"].fillna("").astype(str).str.strip()
    df["grupo"] = df["grupo"].fillna("").astype(str).str.strip()
    df["subgrupo"] = df["subgrupo"].fillna("").astype(str).str.strip()
    df["ean"] = df["ean"].fillna("").astype(str).str.strip()
    df["ncm"] = df["ncm"].fillna("").astype(str).str.strip()
    
    df["ean"] = df["ean"].apply(lambda x: x[:-2] if x.endswith(".0") else x)
    df["ncm"] = df["ncm"].apply(lambda x: x[:-2] if x.endswith(".0") else x)
    
    df = df[df["descricao"] != ""]
    df = df[df["grupo"] != ""]
    df = df[df["subgrupo"] != ""]

    return df.to_dict("records")


def write_results(produtos: list[ProdutoSaida]) -> io.BytesIO:
    """
    Gera o .xlsx de resultado via Pandas com formatação xlsxwriter.
    """
    saida = io.BytesIO()
    
    dados = [
        {
            "Descrição": p.descricao,
            "EAN": p.ean,
            "NCM": p.ncm,
            "Grupo": p.grupo,
            "Subgrupo": p.subgrupo,
            "Origem da Decisão": p.origem,
            "Status": p.status,
        }
        for p in produtos
    ]
    df = pd.DataFrame(dados)
    
    with pd.ExcelWriter(saida, engine="xlsxwriter") as escritor:
        df.to_excel(escritor, sheet_name="Resultado", index=False)
        livro_trabalho = escritor.book
        planilha = escritor.sheets["Resultado"]
        
        fmt_cabecalho = livro_trabalho.add_format({
            "bold": True,
            "bg_color": "#1a1a2e",
            "font_color": "#e0e0ff",
            "border": 1,
            "text_wrap": True,
            "align": "center",
            "valign": "vcenter",
            "font_size": 11,
        })
        
        fmt_celula = livro_trabalho.add_format({
            "border": 1,
            "text_wrap": True,
            "valign": "vcenter",
        })
        
        fmt_aprovado = livro_trabalho.add_format({
            "bg_color": "#d4edda",
            "font_color": "#155724",
            "border": 1,
        })
        
        fmt_pendente = livro_trabalho.add_format({
            "bg_color": "#fff3cd",
            "font_color": "#856404",
            "border": 1,
        })
        
        cabecalhos = ["Descrição", "EAN", "NCM", "Grupo", "Subgrupo", "Origem da Decisão", "Status"]
        larguras_coluna = [50, 16, 12, 20, 25, 22, 20]
        
        for indice_coluna, (cabecalho, largura) in enumerate(zip(cabecalhos, larguras_coluna)):
            planilha.set_column(indice_coluna, indice_coluna, largura)
            planilha.write(0, indice_coluna, cabecalho, fmt_cabecalho)
            
        for indice_linha, p in enumerate(produtos, start=1):
            planilha.write(indice_linha, 0, p.descricao, fmt_celula)
            planilha.write(indice_linha, 1, p.ean, fmt_celula)
            planilha.write(indice_linha, 2, p.ncm, fmt_celula)
            planilha.write(indice_linha, 3, p.grupo, fmt_celula)
            planilha.write(indice_linha, 4, p.subgrupo, fmt_celula)
            planilha.write(indice_linha, 5, p.origem, fmt_celula)
            
            fmt_status = fmt_aprovado if p.status == "Aprovado" else fmt_pendente
            planilha.write(indice_linha, 6, p.status, fmt_status)
            
        planilha.autofilter(0, 0, len(produtos), len(cabecalhos) - 1)
        planilha.freeze_panes(1, 0)
        
    saida.seek(0)
    return saida
