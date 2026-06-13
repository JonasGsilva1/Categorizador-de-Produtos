"""
Leitura e escrita de arquivos .xlsx via Pandas.
- Leitura rápida com pd.read_excel em lote.
- Escrita usando pd.DataFrame.to_excel e xlsxwriter para manter formatação nativa.
"""

import io
import pandas as pd
from app.models import ProductInput, ProductOutput


def read_products(file_bytes: bytes) -> list[ProductInput]:
    """
    Lê a planilha .xlsx usando Pandas e extrai os produtos.
    Espera colunas: Descrição, EAN, NCM (case-insensitive).
    Retorna lista de ProductInput com o índice da linha.
    """
    df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    df.columns = df.columns.astype(str).str.strip().str.lower().str.replace("_", " ")

    header_aliases = {
        "descricao": ["descrição", "descricao", "description", "desc", "produto", "nome"],
        "ean": ["ean", "gtin", "codigo de barras", "código de barras", "cod barras", "barcode"],
        "ncm": ["ncm", "cod ncm", "código ncm"],
    }
    
    col_map = {}
    for col in df.columns:
        for field, aliases in header_aliases.items():
            if col in aliases and field not in col_map:
                col_map[col] = field
                break
    
    df = df.rename(columns=col_map)
    
    if "descricao" not in df.columns:
        raise ValueError(
            "Coluna 'Descrição' não encontrada na planilha. "
            "Colunas aceitas: " + ", ".join(header_aliases["descricao"])
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
    
    products: list[ProductInput] = []
    for row_idx, row in df.iterrows():
        excel_row = int(row_idx) + 2
        if not row["descricao"]:
            continue
        products.append(ProductInput(
            row_index=excel_row,
            descricao=row["descricao"],
            ean=row["ean"],
            ncm=row["ncm"],
        ))
        
    return products


def read_feedback_products(file_bytes: bytes) -> list[dict]:
    """
    Lê a planilha de retroalimentação (corrigida manualmente) via Pandas.
    """
    df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    df.columns = df.columns.astype(str).str.strip().str.lower().str.replace("_", " ")

    header_aliases = {
        "descricao": ["descrição", "descricao", "description", "desc", "produto", "nome"],
        "ean": ["ean", "gtin", "codigo de barras", "código de barras"],
        "ncm": ["ncm", "cod ncm", "código ncm"],
        "grupo": ["grupo", "category", "categoria"],
        "subgrupo": ["subgrupo", "subcategoria", "subcategory", "sub grupo"],
    }
    
    col_map = {}
    for col in df.columns:
        for field, aliases in header_aliases.items():
            if col in aliases and field not in col_map:
                col_map[col] = field
                break
                
    df = df.rename(columns=col_map)
    
    required = ["descricao", "grupo", "subgrupo"]
    missing = [f for f in required if f not in df.columns]
    if missing:
        raise ValueError(f"Colunas obrigatórias não encontradas: {missing}")

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


def write_results(products: list[ProductOutput]) -> io.BytesIO:
    """
    Gera o .xlsx de resultado via Pandas com formatação xlsxwriter.
    """
    output = io.BytesIO()
    
    data = [
        {
            "Descrição": p.descricao,
            "EAN": p.ean,
            "NCM": p.ncm,
            "Grupo": p.grupo,
            "Subgrupo": p.subgrupo,
            "Origem da Decisão": p.origem,
            "Status": p.status,
        }
        for p in products
    ]
    df = pd.DataFrame(data)
    
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Resultado", index=False)
        workbook = writer.book
        worksheet = writer.sheets["Resultado"]
        
        header_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#1a1a2e",
            "font_color": "#e0e0ff",
            "border": 1,
            "text_wrap": True,
            "align": "center",
            "valign": "vcenter",
            "font_size": 11,
        })
        
        cell_fmt = workbook.add_format({
            "border": 1,
            "text_wrap": True,
            "valign": "vcenter",
        })
        
        approved_fmt = workbook.add_format({
            "bg_color": "#d4edda",
            "font_color": "#155724",
            "border": 1,
        })
        
        pending_fmt = workbook.add_format({
            "bg_color": "#fff3cd",
            "font_color": "#856404",
            "border": 1,
        })
        
        headers = ["Descrição", "EAN", "NCM", "Grupo", "Subgrupo", "Origem da Decisão", "Status"]
        col_widths = [50, 16, 12, 20, 25, 22, 20]
        
        for col_idx, (header, width) in enumerate(zip(headers, col_widths)):
            worksheet.set_column(col_idx, col_idx, width)
            worksheet.write(0, col_idx, header, header_fmt)
            
        for row_idx, p in enumerate(products, start=1):
            worksheet.write(row_idx, 0, p.descricao, cell_fmt)
            worksheet.write(row_idx, 1, p.ean, cell_fmt)
            worksheet.write(row_idx, 2, p.ncm, cell_fmt)
            worksheet.write(row_idx, 3, p.grupo, cell_fmt)
            worksheet.write(row_idx, 4, p.subgrupo, cell_fmt)
            worksheet.write(row_idx, 5, p.origem, cell_fmt)
            
            status_fmt = approved_fmt if p.status == "Aprovado" else pending_fmt
            worksheet.write(row_idx, 6, p.status, status_fmt)
            
        worksheet.autofilter(0, 0, len(products), len(headers) - 1)
        worksheet.freeze_panes(1, 0)
        
    output.seek(0)
    return output
