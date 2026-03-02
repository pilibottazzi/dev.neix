# tools/comerciales/transactions_analyzer.py
# NEIX Workbench tool (router-compatible): expone render(_ctx=None)
# Objetivo: subir Excel "Transactions", limpiar tabla, categorizar en 5 tabs,
# y reconstruir CASH: saldo inicial + movimientos = saldo final.

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

CATEGORY_ORDER = ["TRADE", "CASH_MOVEMENT", "INCOME_DIV", "TAX", "FEE", "OTHER"]


# =========================
# Helpers base
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

    # fallback
    try:
        return pd.to_datetime(s, errors="coerce")
    except Exception:
        return pd.NaT


def parse_num_mixed(x) -> float:
    """
    Convierte números con coma decimal (AR/ES) y/o punto miles.
    Ej:
      "-18290,42" -> -18290.42
      "114,48000" -> 114.48
      "22.733.580,97" -> 22733580.97
    """
    s = _safe_str(x).strip()
    if not s or s == "-":
        return 0.0

    s = re.sub(r"[^0-9\-,\.]", "", s)

    if "," in s and "." in s:
        # '.' miles, ',' decimal
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


# =========================
# Detectar tabla dentro del export
# =========================
def _find_header_row(df_raw: pd.DataFrame) -> Optional[int]:
    want = {
        "processdate",
        "settlementdate",
        "netamountbasecurrency",
        "transactiondescription",
        "transactiontype",
    }
    for i in range(min(len(df_raw), 120)):
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
        return df

    headers = df_raw.iloc[hr].astype(str).tolist()
    df = df_raw.iloc[hr + 1 :].copy()
    df.columns = headers
    df = df.dropna(how="all")
    df = df.loc[:, ~df.columns.astype(str).str.match(r"^\s*$")]
    return df


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
    c_desc = pick("Transaction Description")
    c_type = pick("Transaction Type")
    c_symbol = pick("SYMBOL", "Symbol")
    c_buysell = pick("Buy/Sell", "Buy Sell", "BuySell")
    c_qty = pick("Quantity")
    c_price = pick("Price (Transaction Currency)", "Price Transaction Currency", "Price")
    c_ccy = pick("Transaction Currency")

    out = pd.DataFrame()
    out["process_date_raw"] = df[c_process] if c_process else None
    out["settlement_date_raw"] = df[c_settle] if c_settle else None
    out["net_base_raw"] = df[c_net_base] if c_net_base else None
    out["tx_desc"] = df[c_desc] if c_desc else ""
    out["tx_type"] = df[c_type] if c_type else ""
    out["symbol"] = df[c_symbol] if c_symbol else ""
    out["buy_sell"] = df[c_buysell] if c_buysell else ""
    out["quantity_raw"] = df[c_qty] if c_qty else None
    out["price_raw"] = df[c_price] if c_price else None
    out["tx_ccy"] = df[c_ccy] if c_ccy else ""

    out["process_date"] = out["process_date_raw"].apply(parse_es_date)
    out["settlement_date"] = out["settlement_date_raw"].apply(parse_es_date)
    out["net_amount_base"] = out["net_base_raw"].apply(parse_num_mixed)
    out["quantity"] = out["quantity_raw"].apply(parse_num_mixed)
    out["price"] = out["price_raw"].apply(parse_num_mixed)

    for c in ["tx_desc", "tx_type", "symbol", "buy_sell", "tx_ccy"]:
        out[c] = out[c].astype(str).str.strip()

    out["ym_settle"] = out["settlement_date"].dt.to_period("M").astype(str)
    out["ym_process"] = out["process_date"].dt.to_period("M").astype(str)
    return out


# =========================
# Categorías
# =========================
def _categorize_row(tx_type: str, tx_desc: str, buy_sell: str) -> str:
    t = (tx_type or "").upper()
    d = (tx_desc or "").upper()
    b = (buy_sell or "").upper()

    # TRADE
    if b in {"BUY", "SELL"}:
        return "TRADE"
    if "BUY " in t or "SELL " in t or "SHARE(S)" in t or "PARVALUE" in t:
        return "TRADE"

    # INCOME
    if "DIVIDEND" in t or "DIVIDEND" in d or "CASH DIVIDEND" in t or t.startswith("DV"):
        return "INCOME_DIV"

    # TAX
    if "TAX" in t or "WITHHELD" in t or "NRA" in t or "ALIEN" in t or "FOREIGN TAX" in t:
        return "TAX"

    # FEES
    if "FEE" in t or "CUSTODY" in t or "SUBSCRIPTION" in t or "BILLING" in t or "ADVISORY" in t:
        return "FEE"

    # CASH MOVEMENTS
    if "FEDERAL FUNDS" in t or "FEDERAL FUNDS" in d or "JOURNAL" in t or "INTRA-ACCT" in d:
        return "CASH_MOVEMENT"

    return "OTHER"


def _add_category_and_qty_signed(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["category"] = [
        _categorize_row(t, d, b) for t, d, b in zip(df["tx_type"], df["tx_desc"], df["buy_sell"])
    ]

    def qty_signed(row) -> float:
        q = float(row["quantity"] or 0.0)
        bs = (row["buy_sell"] or "").upper()
        if bs == "SELL":
            return -abs(q) if q != 0 else q
        if bs == "BUY":
            return abs(q) if q != 0 else q
        return q

    df["qty_signed"] = df.apply(qty_signed, axis=1)
    return df


def _filter_by_date(df: pd.DataFrame, date_col: str, start: Optional[dt.date], end: Optional[dt.date]) -> pd.DataFrame:
    if start is None and end is None:
        return df
    d = df[date_col]
    m = pd.Series([True] * len(df))
    if start is not None:
        m &= d >= pd.Timestamp(start)
    if end is not None:
        m &= d <= pd.Timestamp(end)
    return df.loc[m].copy()


# =========================
# Render principal (tool UI)
# =========================
def render_transactions_analyzer() -> None:
    st.markdown("## 🧾 Movimientos CV — Transactions Analyzer")
    st.caption(
        "Subí el Excel de movimientos. Esto reconstruye **cash** (Base Currency): "
        "**Saldo inicial + movimientos = Saldo final**. "
        "Después lo extendemos a valuación si querés."
    )

    c1, c2, c3 = st.columns([1.35, 1.0, 1.0], vertical_alignment="bottom")
    with c1:
        up = st.file_uploader("Subí el Excel exportado (Transactions)", type=["xlsx", "xls"])
    with c2:
        saldo_inicial = st.number_input(
            "Saldo inicial (Cash) — Base Currency",
            value=0.0,
            step=1000.0,
        )
    with c3:
        date_basis = st.selectbox(
            "Fecha para análisis",
            options=["Settlement Date (recomendado)", "Process Date"],
            index=0,
        )

    if not up:
        st.info("Subí el Excel para empezar.")
        return

    # leer sin headers para detectar tabla interna
    df_raw = pd.read_excel(up, sheet_name=0, header=None, dtype=object)
    df_table = _slice_table_from_export(df_raw)

    df = _standardize_columns(df_table)
    df = _add_category_and_qty_signed(df)

    date_col = "settlement_date" if date_basis.startswith("Settlement") else "process_date"
    ym_col = "ym_settle" if date_col == "settlement_date" else "ym_process"

    # filtros (rango + categorías + symbol)
    min_d = df[date_col].min()
    max_d = df[date_col].max()

    f1, f2, f3, f4 = st.columns([1.0, 1.0, 1.2, 1.0], vertical_alignment="bottom")

    with f1:
        start = st.date_input(
            "Desde",
            value=min_d.date() if pd.notna(min_d) else None,
            min_value=min_d.date() if pd.notna(min_d) else None,
            max_value=max_d.date() if pd.notna(max_d) else None,
        ) if pd.notna(min_d) else None

    with f2:
        end = st.date_input(
            "Hasta",
            value=max_d.date() if pd.notna(max_d) else None,
            min_value=min_d.date() if pd.notna(min_d) else None,
            max_value=max_d.date() if pd.notna(max_d) else None,
        ) if pd.notna(max_d) else None

    with f3:
        cat_sel = st.multiselect("Categorías", options=CATEGORY_ORDER, default=CATEGORY_ORDER)

    with f4:
        sym = st.text_input("Filtrar Symbol", value="").strip().upper()

    dff = _filter_by_date(df, date_col, start, end)

    if cat_sel:
        dff = dff[dff["category"].isin(cat_sel)].copy()
    if sym:
        dff = dff[dff["symbol"].astype(str).str.upper().str.contains(sym, na=False)].copy()

    # KPI cash
    mov_neto = float(dff["net_amount_base"].sum() if len(dff) else 0.0)
    saldo_final = float(saldo_inicial + mov_neto)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Saldo inicial (Cash)", f"{saldo_inicial:,.2f}")
    k2.metric("Movimientos netos", f"{mov_neto:,.2f}")
    k3.metric("Saldo final (Cash)", f"{saldo_final:,.2f}")
    k4.metric("Movimientos", f"{len(dff):,}")

    st.divider()

    tabs = st.tabs(["Overview"] + CATEGORY_ORDER)

    # Overview
    with tabs[0]:
        left, right = st.columns([1.35, 1.0])

        with left:
            st.markdown("### Movimientos (tabla limpia)")
            show_cols = [
                date_col, "category", "symbol", "buy_sell",
                "qty_signed", "price", "net_amount_base",
                "tx_type", "tx_desc",
            ]
            view = dff[show_cols].sort_values(by=date_col, ascending=True).reset_index(drop=True)
            st.dataframe(view, use_container_width=True, height=460)

        with right:
            st.markdown("### Suma por categoría")
            by_cat = (
                dff.groupby("category", dropna=False)["net_amount_base"]
                .sum()
                .reindex(CATEGORY_ORDER)
                .fillna(0.0)
                .reset_index()
                .rename(columns={"net_amount_base": "net_base_sum"})
            )
            st.dataframe(by_cat, use_container_width=True, height=240)

            st.markdown("### Suma mensual")
            by_month = (
                dff.groupby([ym_col, "category"], dropna=False)["net_amount_base"]
                .sum()
                .reset_index()
                .pivot(index=ym_col, columns="category", values="net_amount_base")
                .reindex(columns=CATEGORY_ORDER)
                .fillna(0.0)
                .sort_index()
            )
            st.dataframe(by_month, use_container_width=True, height=260)

    # Tabs por categoría
    for i, cat in enumerate(CATEGORY_ORDER, start=1):
        with tabs[i]:
            dfc = dff[dff["category"] == cat].copy()

            cA, cB, cC = st.columns([1.0, 1.0, 1.0])
            cA.metric(f"{cat} — Total", f"{dfc['net_amount_base'].sum():,.2f}")
            cB.metric(f"{cat} — Movimientos", f"{len(dfc):,}")
            if cat == "TRADE":
                cC.metric("TRADE — Qty (abs)", f"{dfc['qty_signed'].abs().sum():,.4f}")
            else:
                cC.metric("—", "")

            show_cols = [
                date_col, "symbol", "buy_sell", "qty_signed", "price",
                "net_amount_base", "tx_type", "tx_desc",
            ]
            st.dataframe(
                dfc[show_cols].sort_values(by=date_col, ascending=True).reset_index(drop=True),
                use_container_width=True,
                height=520,
            )

            if cat in {"TRADE", "INCOME_DIV", "TAX", "FEE"} and len(dfc):
                st.markdown("#### Resumen por Symbol")
                by_sym = (
                    dfc.groupby("symbol", dropna=False)["net_amount_base"]
                    .sum()
                    .sort_values(ascending=True)
                    .reset_index()
                    .rename(columns={"net_amount_base": "net_base_sum"})
                )
                st.dataframe(by_sym, use_container_width=True, height=280)


# =========================
# Wrapper estándar del Workbench
# =========================
def render(_ctx=None):
    """
    Contrato Workbench: el router llama siempre tool.render(None)
    """
    render_transactions_analyzer()
