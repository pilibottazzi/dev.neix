# fix_cn_consolidado_comas.py
from __future__ import annotations

from pathlib import Path
import pandas as pd


NUM_COLS = ["Neto Agente", "Gross Agente"]  # ajustá si tus nombres cambian


def _coerce_number_any(series: pd.Series) -> pd.Series:
    """
    Convierte números que pueden venir como:
      - "1234.56" (punto decimal)
      - "1,234.56" (US: miles coma, decimal punto)
      - "1.234,56" (AR: miles punto, decimal coma)
      - "1234,56"
    a float. Lo que no pueda queda NaN.
    """
    s = series.astype(str).str.strip()

    # normalizamos vacíos
    s = s.replace({"": None, "None": None, "nan": None, "NaN": None})

    # limpiamos símbolos / espacios comunes
    s = s.str.replace("\u00a0", "", regex=False)  # NBSP
    s = s.str.replace(" ", "", regex=False)
    s = s.str.replace("$", "", regex=False)
    s = s.str.replace("USD", "", regex=False)
    s = s.str.replace("ARS", "", regex=False)

    has_comma = s.str.contains(",", na=False)
    has_dot = s.str.contains(r"\.", na=False)

    out = s.copy()

    # si tiene coma y punto: decidir por última ocurrencia cuál es decimal
    both = has_comma & has_dot
    if both.any():
        last_comma = out[both].str.rfind(",")
        last_dot = out[both].str.rfind(".")
        ar_mask = last_comma > last_dot  # decimal coma (AR)
        us_mask = ~ar_mask               # decimal punto (US/EN)

        idx_ar = out[both].index[ar_mask]
        out.loc[idx_ar] = (
            out.loc[idx_ar]
            .str.replace(".", "", regex=False)   # miles
            .str.replace(",", ".", regex=False)  # decimal
        )

        idx_us = out[both].index[us_mask]
        out.loc[idx_us] = out.loc[idx_us].str.replace(",", "", regex=False)  # miles

    # solo coma => decimal coma
    only_comma = has_comma & ~has_dot
    if only_comma.any():
        out.loc[only_comma] = out.loc[only_comma].str.replace(",", ".", regex=False)

    # solo punto => decimal punto (dejamos)
    return pd.to_numeric(out, errors="coerce")


def fix_cn_consolidado(input_path: str | Path, output_path: str | Path, sheet_name: str | None = None) -> None:
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"No existe: {input_path}")

    # Leemos (por defecto primera hoja). Si querés forzar: sheet_name="Consolidado"
    df = pd.read_excel(input_path, sheet_name=sheet_name, dtype=str)
    df.columns = df.columns.str.strip()

    # Convertir columnas numéricas
    for c in NUM_COLS:
        if c in df.columns:
            df[c] = _coerce_number_any(df[c])
        else:
            print(f"[WARN] No encontré columna '{c}' en el archivo.")

    # Escribir Excel con formato numérico
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Consolidado")

        ws = writer.sheets["Consolidado"]

        # aplicar formato número (Excel mostrará coma si tu configuración regional es ES/AR)
        for c in NUM_COLS:
            if c in df.columns:
                col_idx = df.columns.get_loc(c) + 1  # 1-based
                for col_cells in ws.iter_cols(min_col=col_idx, max_col=col_idx, min_row=2):
                    for cell in col_cells:
                        cell.number_format = "#,##0.00"

    print(f"OK → generado: {output_path}")


if __name__ == "__main__":
    # ====== AJUSTÁ RUTAS ======
    IN_FILE = r"cn_bancos_consolidado.xlsx"
    OUT_FILE = r"cn_bancos_consolidado_comas.xlsx"

    # Si sabés el nombre de la hoja, ponelo (recomendado):
    # SHEET = "Consolidado"
    SHEET = None

    fix_cn_consolidado(IN_FILE, OUT_FILE, sheet_name=SHEET)
