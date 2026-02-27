# tools/comercial/cn.py
from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional

import pandas as pd
import streamlit as st


SHEETS = ["WSC A", "WSC B", "INSIGNEO"]

OUTPUT_COLS = [
    "Fecha",
    "Cuenta",
    "Producto",
    "Neto Agente",
    "Gross Agente",
    "Id_Off",
    "Id_manager",
    "MANAGER",
    "Id_oficial",
    "OFICIAL",
]

NEIX_RED = "#ff3b30"

TEMPLATE_PATH = Path("data") / "Capital N - herramienta de datos.xlsx"


# =========================
# UI CSS
# =========================
def _inject_css() -> None:
    st.markdown(
        f"""
<style>
  .block-container {{
    max-width: 1180px;
    padding-top: 1.2rem;
    padding-bottom: 2rem;
  }}

  div[data-testid="stDownloadButton"] > button {{
    width: 100% !important;
    background: {NEIX_RED} !important;
    color: white !important;
    border-radius: 14px !important;
    font-weight: 800 !important;
    padding: 0.95rem 1rem !important;
    border: 0 !important;
  }}
</style>
""",
        unsafe_allow_html=True,
    )


# =========================
# Helpers
# =========================
def _read_template_bytes() -> bytes | None:
    if not TEMPLATE_PATH.exists():
        return None
    return TEMPLATE_PATH.read_bytes()


def _read_one_sheet(xls: pd.ExcelFile, sheet_name: str) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_excel(xls, sheet_name=sheet_name, dtype=str)
    except Exception:
        return None

    df.columns = df.columns.str.strip()

    missing = [c for c in OUTPUT_COLS if c not in df.columns]
    if missing:
        st.warning(f"{sheet_name} falta columnas: {missing}")
        return None

    df = df[OUTPUT_COLS].copy()
    df.insert(0, "Banco", sheet_name)

    return df


def _coerce_ar_number_to_float(series: pd.Series) -> pd.Series:
    """
    Convierte números que pueden venir como:
      - "1.234,56" (AR)
      - "1234,56"
      - "1234.56" (EN)
      - "1,234.56" (US)
      - con espacios / $ etc
    a float. Lo que no pueda, queda NaN.
    """
    s = series.astype(str).str.strip()

    # vacíos
    s = s.replace({"": None, "None": None, "nan": None, "NaN": None})

    # limpiamos símbolos comunes
    s = s.str.replace("\u00a0", "", regex=False)  # non-breaking space
    s = s.str.replace(" ", "", regex=False)
    s = s.str.replace("$", "", regex=False)
    s = s.str.replace("USD", "", regex=False)
    s = s.str.replace("ARS", "", regex=False)

    # Heurística:
    # si tiene "," y ".":
    #  - si la última ocurrencia es "," => asumimos AR (miles ".", decimal ",")
    #  - si la última ocurrencia es "." => asumimos US (miles ",", decimal ".")
    has_comma = s.str.contains(",", na=False)
    has_dot = s.str.contains(r"\.", na=False)

    out = s.copy()

    both = has_comma & has_dot
    if both.any():
        last_comma = out[both].str.rfind(",")
        last_dot = out[both].str.rfind(".")
        ar_mask = last_comma > last_dot
        us_mask = ~ar_mask

        # AR: miles "." -> remove, decimal "," -> "."
        idx_ar = out[both].index[ar_mask]
        out.loc[idx_ar] = (
            out.loc[idx_ar]
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
        )

        # US: miles "," -> remove, decimal "." -> keep
        idx_us = out[both].index[us_mask]
        out.loc[idx_us] = out.loc[idx_us].str.replace(",", "", regex=False)

    # solo coma: decimal coma
    only_comma = has_comma & ~has_dot
    if only_comma.any():
        out.loc[only_comma] = out.loc[only_comma].str.replace(",", ".", regex=False)

    # solo punto: ya es decimal punto (o entero) => dejamos
    # nada: entero => ok

    return pd.to_numeric(out, errors="coerce")


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    """
    Exporta el consolidado a Excel dejando Neto/Gross como NÚMEROS
    y aplicando formato de número con coma decimal (estilo ES/AR).
    """
    df = df.copy()
    num_cols = ["Neto Agente", "Gross Agente"]

    for c in num_cols:
        if c in df.columns:
            df[c] = _coerce_ar_number_to_float(df[c])

    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Consolidado")

        ws = writer.sheets["Consolidado"]

        # Aplicar formato número (con coma decimal) a las columnas Neto/Gross
        # Nota: number_format es independiente del locale; Excel mostrará coma si el locale es ES/AR.
        for col_name in num_cols:
            if col_name in df.columns:
                col_idx = df.columns.get_loc(col_name) + 1  # 1-based en openpyxl
                # iter_cols usa índices 1-based
                for col_cells in ws.iter_cols(min_col=col_idx, max_col=col_idx, min_row=2):
                    for cell in col_cells:
                        cell.number_format = "#,##0.00"

    bio.seek(0)
    return bio.read()


# =========================
# RENDER
# =========================
def render(back_to_home=None) -> None:
    _inject_css()

    # -------------------------------------------------
    # BOTÓN TEMPLATE
    # -------------------------------------------------
    template_bytes = _read_template_bytes()

    if template_bytes:
        st.download_button(
            "Descargar template para completar",
            data=template_bytes,
            file_name="Capital N - herramienta de datos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    else:
        st.warning("No encontré el template en /data")

    st.divider()

    # -------------------------------------------------
    # UPLOAD
    # -------------------------------------------------
    up = st.file_uploader(
        "CN: Subí el Excel para consolidar bancos",
        type=["xlsx", "xls"],
        accept_multiple_files=False,
    )
    if not up:
        return

    try:
        xls = pd.ExcelFile(io.BytesIO(up.getvalue()))
    except Exception:
        st.error("No pude leer el archivo.")
        return

    dfs: List[pd.DataFrame] = []
    for s in SHEETS:
        one = _read_one_sheet(xls, s)
        if one is not None:
            dfs.append(one)

    if not dfs:
        st.warning("No encontré hojas válidas.")
        return

    df_all = pd.concat(dfs, ignore_index=True)

    st.download_button(
        "Excel consolidado",
        data=_to_excel_bytes(df_all),
        file_name="cn_bancos_consolidado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.markdown("### Consolidado")
    st.dataframe(df_all, use_container_width=True, height=620)
