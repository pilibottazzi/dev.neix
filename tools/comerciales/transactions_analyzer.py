# tools/comerciales/transactions_analyzer.py
# NEIX Workbench tool — versión “limpia” + UI prolija (sin sumar cosas al pedo)
# Cambios clave vs tu versión:
# - La pestaña "Transacciones" (Cash) queda como pediste:
#   Process Date, Settlement Date, Net Amount (Base Currency), Transaction Type, Security Description
# - En ingresos/egresos de dinero: EXCLUYE "ACTIVITY WITHIN YOUR ACCT"
# - Presentación: header más prolijo, filtros compactos, KPIs alineados, tablas más “clean”
# - Sin inventar features extra: dejamos tabs por categoría pero el foco es Cash/Transacciones
# - Fix definitivo del error de máscara (siempre reset_index antes de filtrar)

from __future__ import annotations

import re
import datetime as dt
from typing import Optional, List

import pandas as pd
import streamlit as st


# =========================
# Constantes
# =========================
ES_MON = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12,
}

CATEGORIES = ["TRADE", "CASH_MOVEMENT", "INCOME_DIV", "TAX", "FEE", "OTHER"]

# Orden de tabs (sin agregar cosas raras)
TAB_ORDER = ["Transacciones"] + CATEGORIES

# Tx types a excluir del análisis de ingresos/egresos de cash
EXCLUDE_CASH_TX_TYPES = {"ACTIVITY WITHIN YOUR ACCT"}


# =========================
# Utils
# =========================
def _safe_str(v) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    return str(v)


def _norm_header(s: str) -> str:
    s = _safe_str(s).strip().lower()
    s = (
        s.replace("á", "a").replace("é", "e").replace("í", "i")
         .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def parse_es_date(x) -> pd.Timestamp:
    """
    Convierte:
      'dic 31, 2024' / 'ene 2, 2026'
    a Timestamp.
    """
    if x is None:
        return pd.NaT
    try:
        if pd.isna(x):
            return pd.NaT
    except Exception:
        pass

    if isinstance(x, (pd.Timestamp, dt.date, dt.datetime)):
        return pd.Timestamp(x)

    s = _safe_str(x).strip()
    if not s or s == "-":
        return pd.NaT

    m = re.match(r"^([a-zA-Z]{3,4})\s+(\d{1,2}),\s*(\d{4})$", s)
    if m:
        mon_txt = m.group(1).lower()
        day = int(m.group(2))
        year = int(m.group(3))
        mon = ES_MON.get(mon_txt)
        if mon:
            try:
                return pd.Timestamp(dt.date(year, mon, day))
            except Exception:
                return pd.NaT

    try:
        return pd.to_datetime(s, errors="coerce")
    except Exception:
        return pd.NaT


def parse_num_mixed(x) -> float:
    """
    Convierte números con coma decimal (AR/ES) y/o punto miles.
    """
    s = _safe_str(x).strip()
    if not s or s == "-":
        return 0.0

    s = re.sub(r"[^0-9\-,\.]", "", s)

    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")

    try:
        return float(s)
    except Exception:
        return 0.0


# =========================
# Detectar tabla (header real)
# =========================
def _find_header_row(df_raw: pd.DataFrame) -> Optional[int]:
    want = {
        "processdate",
        "settlementdate",
        "netamountbasecurrency",
        "transactiontype",
        "securitydescription",
    }
    for i in range(min(len(df_raw), 250)):
        row = df_raw.iloc[i].astype(str).tolist()
        normed = [_norm_header(c) for c in row]
        hit = sum(1 for w in want if w in normed)
        if hit >= 3:
            return i
    return None


def _slice_table_from_export(df_raw: pd.DataFrame) -> pd.DataFrame:
    hr = _find_header_row(df_raw)
    if hr is None:
        df = df_raw.copy()
        df.columns = [str(c).strip() for c in df.columns]
        return df.reset_index(drop=True)

    headers = df_raw.iloc[hr].astype(str).tolist()
    df = df_raw.iloc[hr + 1 :].copy()
    df.columns = headers
    df = df.dropna(how="all")
    df = df.loc[:, ~df.columns.astype(str).str.match(r"^\s*$")]
    return df.reset_index(drop=True)


# =========================
# Normalización de columnas
# =========================
def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = list(df.columns)
    norm_map = {_norm_header(c): c for c in cols}

    def pick(*candidates: str) -> Optional[str]:
        for cand in candidates:
            k = _norm_header(cand)
            if k in norm_map:
                return norm_map[k]
        return None

    c_process = pick("Process Date")
    c_settle = pick("Settlement Date")
    c_net_base = pick("Net Amount (Base Currency)", "Net Amount Base Currency")
    c_type = pick("Transaction Type")
    c_sec_desc = pick("Security Description")

    # Extras para tabs (no para el cuadrito de transacciones)
    c_desc = pick("Transaction Description")
    c_symbol = pick("SYMBOL", "Symbol")
    c_buysell = pick("Buy/Sell", "Buy Sell", "BuySell")
    c_qty = pick("Quantity")
    c_price = pick("Price (Transaction Currency)", "Price Transaction Currency", "Price")

    missing = []
    if not c_process and not c_settle:
        missing.append("Process Date / Settlement Date")
    if not c_net_base:
        missing.append("Net Amount (Base Currency)")
    if not c_type:
        missing.append("Transaction Type")
    if not c_sec_desc:
        missing.append("Security Description")

    if missing:
        st.error("No pude mapear columnas clave en el Excel.")
        st.write("Columnas detectadas:", list(df.columns))
        st.write("Faltan:", missing)
        st.stop()

    out = pd.DataFrame()

    out["process_date"] = df[c_process].apply(parse_es_date) if c_process else pd.NaT
    out["settlement_date"] = df[c_settle].apply(parse_es_date) if c_settle else pd.NaT
    out["net_amount_base"] = df[c_net_base].apply(parse_num_mixed)

    out["tx_type"] = df[c_type].astype(str).str.strip()
    out["security_desc"] = df[c_sec_desc].astype(str).str.strip()

    out["tx_desc"] = df[c_desc].astype(str).str.strip() if c_desc else ""
    out["symbol"] = df[c_symbol].astype(str).str.strip() if c_symbol else ""
    out["buy_sell"] = df[c_buysell].astype(str).str.strip() if c_buysell else ""
    out["quantity"] = df[c_qty].apply(parse_num_mixed) if c_qty else 0.0
    out["price"] = df[c_price].apply(parse_num_mixed) if c_price else 0.0

    # normalizaciones
    out["tx_type_u"] = out["tx_type"].str.upper()
    out["security_desc_u"] = out["security_desc"].str.upper()
    out["symbol_u"] = out["symbol"].str.upper()

    # helper YM para overview si se usa
    out["ym"] = out["settlement_date"].dt.to_period("M").astype(str)

    return out.reset_index(drop=True)


# =========================
# Categorías
# =========================
def _categorize_row(tx_type_u: str, tx_desc: str, buy_sell: str) -> str:
    t = (tx_type_u or "").upper()
    d = (tx_desc or "").upper()
    b = (buy_sell or "").upper()

    if b in {"BUY", "SELL"} or t.startswith("BUY ") or t.startswith("SELL "):
        return "TRADE"

    if "DIVIDEND" in t or "DIVIDEND" in d or t.startswith("DV"):
        return "INCOME_DIV"

    if "TAX" in t or "WITHHELD" in t or "NRA" in t or "FOREIGN TAX" in t:
        return "TAX"

    if "FEE" in t or "CUSTODY" in t or "SUBSCRIPTION" in t or "BILLING" in t or "ADVISORY" in t:
        return "FEE"

    if "FEDERAL FUNDS" in t or "JOURNAL" in t or "INTRA-ACCT" in d or "ACTIVITY WITHIN" in d:
        return "CASH_MOVEMENT"

    return "OTHER"


def _add_category(df: pd.DataFrame) -> pd.DataFrame:
    dff = df.copy()
    dff["category"] = [
        _categorize_row(t, desc, bs)
        for t, desc, bs in zip(dff["tx_type_u"], dff["tx_desc"], dff["buy_sell"])
    ]
    return dff


# =========================
# Filtros (safe)
# =========================
def _filter_by_date(df: pd.DataFrame, date_col: str, start: Optional[dt.date], end: Optional[dt.date]) -> pd.DataFrame:
    dff = df.copy().reset_index(drop=True)
    s = pd.to_datetime(dff[date_col], errors="coerce")
    m = s.notna()
    if start is not None:
        m &= s >= pd.Timestamp(start)
    if end is not None:
        m &= s <= pd.Timestamp(end)
    return dff.loc[m].copy().reset_index(drop=True)


# =========================
# UI
# =========================
def _kpi_row(saldo_inicial: float, movimientos: float, movimientos_count: int):
    k1, k2, k3, k4 = st.columns([1, 1, 1, 1], vertical_alignment="center")
    k1.metric("Saldo inicial (Cash)", f"{saldo_inicial:,.2f}")
    k2.metric("Movimientos netos", f"{movimientos:,.2f}")
    k3.metric("Saldo final (Cash)", f"{(saldo_inicial + movimientos):,.2f}")
    k4.metric("Movimientos", f"{movimientos_count:,}")


def render_transactions_analyzer() -> None:
    # Header limpio
    st.markdown("## 🗒️ Movimientos CV — Transactions Analyzer")
    st.caption("Objetivo: entender el flujo de caja: **Saldo inicial + movimientos = Saldo final** (Base Currency).")

    # Top controls compactos
    top1, top2, top3 = st.columns([1.35, 1.05, 1.6], vertical_alignment="bottom")
    with top1:
        up = st.file_uploader("Subí el Excel exportado (Transactions)", type=["xlsx", "xls"])
    with top2:
        date_basis = st.selectbox("Fecha para análisis", ["Settlement Date", "Process Date"], index=0)
    with top3:
        cats = st.multiselect("Categorías", options=CATEGORIES, default=CATEGORIES)

    if not up:
        st.info("Subí el Excel para comenzar.")
        return

    # Leer y detectar tabla real
    df_raw = pd.read_excel(up, sheet_name=0, header=None, dtype=object)
    df_table = _slice_table_from_export(df_raw)
    df = _standardize_columns(df_table)
    df = _add_category(df)

    date_col = "settlement_date" if date_basis == "Settlement Date" else "process_date"

    # Filtros de fecha
    min_d = pd.to_datetime(df[date_col], errors="coerce").min()
    max_d = pd.to_datetime(df[date_col], errors="coerce").max()

    f1, f2, f3 = st.columns([1, 1, 1], vertical_alignment="bottom")
    with f1:
        start = st.date_input("Desde", value=min_d.date() if pd.notna(min_d) else None)
    with f2:
        end = st.date_input("Hasta", value=max_d.date() if pd.notna(max_d) else None)
    with f3:
        sym = st.text_input("Filtrar Symbol", value="").strip().upper()

    dff = _filter_by_date(df, date_col, start, end)

    if cats:
        dff = dff[dff["category"].isin(cats)].copy().reset_index(drop=True)

    if sym:
        dff = dff[dff["symbol_u"].str.contains(sym, na=False)].copy().reset_index(drop=True)

    # =========================
    # KPIs cash (global)
    # =========================
    # Saldo inicial por default: suma de FEDERAL FUNDS RECEIVED (solo depósitos) antes del primer trade,
    # pero para no agregar “lógica extra” acá, lo dejamos manual simple:
    saldo_inicial = st.number_input("Saldo inicial (Cash) — manual", value=0.0, step=1000.0)
    mov_neto = float(dff["net_amount_base"].sum() if len(dff) else 0.0)
    _kpi_row(saldo_inicial, mov_neto, len(dff))

    st.divider()

    # =========================
    # Tabs
    # =========================
    tabs = st.tabs(TAB_ORDER)

    # ---------------------------------------------------------
    # TAB 0: Transacciones (Ingresos/Egresos Cash) — tu pedido
    # ---------------------------------------------------------
    with tabs[0]:
        st.markdown("### Transacciones · Ingresos/Egresos de dinero (Cash)")

        base = dff.copy().reset_index(drop=True)

        # Excluir “ACTIVITY WITHIN YOUR ACCT” del análisis de ingresos/egresos
        base = base[~base["tx_type_u"].isin(EXCLUDE_CASH_TX_TYPES)].copy().reset_index(drop=True)

        # Para cash, nos quedamos con lo que sea “CURRENCY” (como en tu ejemplo U.S.DOLLARS CURRENCY)
        is_cash = base["security_desc_u"].str.contains("CURRENCY", na=False)
        cash = base[is_cash].copy().reset_index(drop=True)

        cuadrito = cash[ESSENTIAL_COLS_ORDER].copy()
        cuadrito = cuadrito.sort_values(["settlement_date", "process_date"], ascending=True).reset_index(drop=True)

        # KPIs solo cash (para que sea claro)
        mov_cash = float(cuadrito["net_amount_base"].sum() if len(cuadrito) else 0.0)
        _kpi_row(saldo_inicial, mov_cash, len(cuadrito))

        st.caption("Vista filtrada a **Cash/Currency**. Excluye **ACTIVITY WITHIN YOUR ACCT**.")
        st.dataframe(
            cuadrito,
            use_container_width=True,
            hide_index=True,
            column_config={
                "process_date": st.column_config.DatetimeColumn("Process Date"),
                "settlement_date": st.column_config.DatetimeColumn("Settlement Date"),
                "net_amount_base": st.column_config.NumberColumn("Net Amount (Base Currency)", format="%.2f"),
                "tx_type": st.column_config.TextColumn("Transaction Type"),
                "security_desc": st.column_config.TextColumn("Security Description"),
            },
            height=420,
        )

    # ---------------------------------------------------------
    # Resto de tabs: por categoría (simple, sin ruido)
    # ---------------------------------------------------------
    def _tab_cat(cat: str):
        st.markdown(f"### {cat}")
        dfc = dff[dff["category"] == cat].copy().reset_index(drop=True)
        st.caption(f"Movimientos en categoría **{cat}**.")

        st.metric("Total (Base Currency)", f"{dfc['net_amount_base'].sum():,.2f}")
        cols = [
            "process_date",
            "settlement_date",
            "symbol",
            "buy_sell",
            "quantity",
            "price",
            "net_amount_base",
            "tx_type",
            "security_desc",
        ]
        show = [c for c in cols if c in dfc.columns]
        st.dataframe(
            dfc[show].sort_values(["settlement_date", "process_date"]).reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            height=520,
        )

    for i, cat in enumerate(CATEGORIES, start=1):
        with tabs[i]:
            _tab_cat(cat)


# =========================
# Wrapper Workbench
# =========================
def render(_ctx=None):
    render_transactions_analyzer()
