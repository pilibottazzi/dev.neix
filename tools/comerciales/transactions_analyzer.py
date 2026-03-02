# tools/comerciales/transactions_analyzer.py
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# =========================
# UI (minimal, pro)
# =========================
def _inject_css() -> None:
    st.markdown(
        """
        <style>
          .block-container { padding-top: 1.2rem; max-width: 1180px; }
          h1 { margin-bottom: 0.2rem; }
          .subtle { color: rgba(0,0,0,0.55); font-size: 0.95rem; margin-top: 0.1rem; }
          .kpi { padding: 12px 14px; border: 1px solid rgba(0,0,0,0.08); border-radius: 14px; background: #fff; }
          .kpi .label { color: rgba(0,0,0,0.55); font-size: 0.85rem; margin-bottom: 4px; }
          .kpi .value { font-size: 1.55rem; font-weight: 700; letter-spacing: -0.02em; }
          .pill { display:inline-block; padding: 3px 10px; border-radius: 999px; border: 1px solid rgba(0,0,0,0.12); font-size: 0.82rem; color: rgba(0,0,0,0.7); }
          .hr { height:1px; background: rgba(0,0,0,0.08); margin: 10px 0 12px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# =========================
# Parsing helpers
# =========================
CANON_COLS = [
    "Process Date",
    "Security Identifier",
    "Settlement Date",
    "Net Amount (Base Currency)",
    "Transaction Description",
    "Transaction Type",
    "Security Description",
    "Net Amount (Transaction Currency)",
    "Buy/Sell",
    "Quantity",
    "Price (Transaction Currency)",
    "Transaction Currency",
    "Security Type",
    "Payee",
    "Paid For (Name)",
    "Request Reason",
    "CUSIP",
    "FX Rate (To Base)",
    "ISIN",
    "SEDOL",
    "SYMBOL",
    "Trade Date",
    "Transaction code",
    "Withdrawal/Deposit Type",
    "Request ID #",
    "Commission",
]


def _norm(s: str) -> str:
    s = str(s or "").strip().lower()
    s = (
        s.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    s = re.sub(r"\s+", " ", s)
    return s


def _find_header_row(df0: pd.DataFrame) -> int:
    """
    Pershing export: arriba hay metadata (Account, Client, etc).
    Buscamos la fila donde aparezca 'Process Date' y otros headers clave.
    """
    key = _norm("Process Date")
    candidates = []
    for i in range(min(len(df0), 80)):  # suficiente para headers + metadata
        row = df0.iloc[i].astype(str).map(_norm).tolist()
        if key in row:
            score = 0
            for must in ["settlement date", "transaction type", "security type", "net amount (base currency)"]:
                if _norm(must) in row:
                    score += 1
            candidates.append((score, i))
    if not candidates:
        return -1
    candidates.sort(reverse=True)
    return candidates[0][1]


def _to_float(x):
    if pd.isna(x):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s == "" or s == "-":
        return None
    # soporta "22.733,58" y "22733.58"
    s = s.replace(" ", "")
    if re.search(r"\d+,\d+$", s) and s.count(",") == 1 and s.count(".") >= 1:
        # 22.733.580,97 -> 22733580.97
        s = s.replace(".", "").replace(",", ".")
    elif s.count(",") == 1 and s.count(".") == 0:
        # 123,45 -> 123.45
        s = s.replace(",", ".")
    else:
        # 1234.56 o 1234
        s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None


def _to_date(x):
    if pd.isna(x):
        return pd.NaT
    try:
        return pd.to_datetime(x, errors="coerce").date()
    except Exception:
        return pd.NaT


def _read_pershing_excel(file_bytes: bytes) -> pd.DataFrame:
    """
    Lee el Excel y devuelve un DF con columnas canon.
    IMPORTANTE: evitamos sheet_name=None (que devuelve dict), para no repetir tu error.
    """
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    sheet0 = xls.sheet_names[0]
    df0 = pd.read_excel(xls, sheet_name=sheet0, header=None, dtype=object)

    hdr = _find_header_row(df0)
    if hdr < 0:
        raise ValueError("No pude detectar la fila de encabezados (Process Date).")

    headers = df0.iloc[hdr].astype(str).tolist()
    df = df0.iloc[hdr + 1 :].copy()
    df.columns = headers
    df = df.dropna(how="all")

    # Renombrado suave: si vienen headers con espacios raros, igual los mapeamos
    col_map: Dict[str, str] = {}
    for c in df.columns:
        cn = _norm(c)
        for canon in CANON_COLS:
            if cn == _norm(canon):
                col_map[c] = canon
                break
    df = df.rename(columns=col_map)

    # Nos quedamos solo con columnas que existan
    keep = [c for c in CANON_COLS if c in df.columns]
    df = df[keep].copy()

    # Tipos
    if "Settlement Date" in df.columns:
        df["Settlement Date"] = df["Settlement Date"].apply(_to_date)
    if "Process Date" in df.columns:
        df["Process Date"] = df["Process Date"].apply(_to_date)
    if "Trade Date" in df.columns:
        # muchas veces viene texto, lo dejamos como string; si se puede parsear, ok
        df["Trade Date"] = df["Trade Date"].astype(str).where(df["Trade Date"].notna(), "")

    # Montos / cantidades
    for num_col in [
        "Net Amount (Base Currency)",
        "Net Amount (Transaction Currency)",
        "Quantity",
        "Price (Transaction Currency)",
        "Commission",
        "FX Rate (To Base)",
    ]:
        if num_col in df.columns:
            df[num_col] = df[num_col].apply(_to_float)

    # Normalizaciones base
    if "SYMBOL" in df.columns:
        df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip()
        df.loc[df["SYMBOL"].isin(["nan", "None"]), "SYMBOL"] = ""

    if "Security Type" in df.columns:
        df["Security Type"] = df["Security Type"].astype(str).str.strip().str.upper()

    if "Transaction Type" in df.columns:
        df["Transaction Type"] = df["Transaction Type"].astype(str).str.strip()

    if "Buy/Sell" in df.columns:
        df["Buy/Sell"] = df["Buy/Sell"].astype(str).str.strip().str.upper()
        df.loc[~df["Buy/Sell"].isin(["BUY", "SELL"]), "Buy/Sell"] = ""

    return df


# =========================
# Classification (FASE 1/2)
# =========================
CASH_TX = {"FEDERAL FUNDS RECEIVED", "FEDERAL FUNDS SENT"}
INTERNAL_TX = {"ACTIVITY WITHIN YOUR ACCT"}  # por ahora lo excluimos de cash movement

DIV_TX_MARKERS = [
    "CASH DIVIDEND RECEIVED",
    "FOREIGN SECURITY DIVIDEND RECEIVED",
]
TAX_MARKERS = [
    "NON-RESIDENT ALIEN TAX",
    "FOREIGN TAX WITHHELD",
]
FEE_MARKERS = [
    "FEE",
    "ADVISORY",
    "CUSTODY",
    "SUBSCRIPTION",
    "INT.",
    "INTEREST",
    "ASSET BASED FEE",
]


def _is_cash_movement(row: pd.Series) -> bool:
    tx = str(row.get("Transaction Type", "")).upper()
    if tx in INTERNAL_TX:
        return False
    return tx in CASH_TX


def _is_dividend(row: pd.Series) -> bool:
    tx = str(row.get("Transaction Type", "")).upper()
    return any(m in tx for m in DIV_TX_MARKERS)


def _is_tax(row: pd.Series) -> bool:
    tx = str(row.get("Transaction Type", "")).upper()
    code = str(row.get("Transaction code", "")).upper()
    desc = str(row.get("Transaction Description", "")).upper()

    if any(m in tx for m in TAX_MARKERS):
        return True
    # códigos típicos que aparecen en tus ejemplos (NRA / FGN / FGF)
    if code in {"NRA", "FGN", "FGF"}:
        return True
    # fallback: si dice TAX en el tipo
    if "TAX" in tx:
        return True
    # a veces la descripción lo marca
    if "TAX WITHHELD" in desc:
        return True
    return False


def _is_fee(row: pd.Series) -> bool:
    tx = str(row.get("Transaction Type", "")).upper()
    desc = str(row.get("Transaction Description", "")).upper()
    code = str(row.get("Transaction code", "")).upper()
    comm = row.get("Commission", None)
    if isinstance(comm, (int, float)) and comm and comm > 0:
        return True
    if "FEE" in tx or "FEE" in desc:
        return True
    if code in {"PDS", "NTF", "INM", "PCT", "/FG"}:
        return True
    if any(m in tx for m in FEE_MARKERS):
        return True
    return False


def _is_trade_real(row: pd.Series) -> bool:
    bs = str(row.get("Buy/Sell", "")).upper().strip()
    return bs in {"BUY", "SELL"}


ETF_TYPES = {"EXCHANGE TRADED FUNDS"}
STOCK_TYPES = {"COMMON STOCK", "COMMON STOCK ADR", "OPEN END TAXABLE LOAD FUND", "INDEX LINKED CORP BOND"}


# =========================
# Display helpers
# =========================
def _fmt_money(x: Optional[float]) -> str:
    if x is None or pd.isna(x):
        return "-"
    return f"{x:,.2f}"


def _kpi(label: str, value: str) -> None:
    st.markdown(
        f"""
        <div class="kpi">
          <div class="label">{label}</div>
          <div class="value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _select_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    cols_ok = [c for c in cols if c in df.columns]
    return df[cols_ok].copy()


# =========================
# Main render
# =========================
def render(_ctx=None) -> None:
    _inject_css()

    st.title("Movimientos CV — Transactions Analyzer")
    st.markdown(
        '<div class="subtle">Empezamos simple: cash (ingresos/egresos), ETFs y stocks. Todo en Base Currency (USD) y filtrado por Settlement Date.</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

    up = st.file_uploader("Subí el Excel exportado (Transactions)", type=["xlsx", "xls"])

    # Controles globales (se activan cuando hay data)
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1.2, 1.0, 0.8], vertical_alignment="bottom")

    with ctrl_col1:
        st.caption("Fecha para análisis (global)")
        date_col = "Settlement Date"  # fijo como pediste

    df_raw: Optional[pd.DataFrame] = None
    if up is not None:
        try:
            df_raw = _read_pershing_excel(up.getvalue())
        except Exception as e:
            st.error("No pude leer el Excel (o detectar la fila de encabezados).")
            st.exception(e)
            return
    else:
        st.info("Subí el Excel para empezar.")
        return

    # Validación mínima
    if date_col not in df_raw.columns:
        st.error("No encontré 'Settlement Date' en el archivo.")
        return

    df = df_raw.copy()
    df = df[df[date_col].notna()].copy()

    # Rango de fechas global
    min_d = df[date_col].min()
    max_d = df[date_col].max()

    with ctrl_col2:
        st.caption("Desde / Hasta (global)")
        from_d, to_d = st.date_input(
            "Rango",
            value=(min_d, max_d),
            min_value=min_d,
            max_value=max_d,
            label_visibility="collapsed",
        )

    # Aplicar filtro global
    df = df[(df[date_col] >= from_d) & (df[date_col] <= to_d)].copy()

    # Tabs (orden fijo)
    tab_over, tab_cash, tab_etf, tab_stock, tab_div, tab_fee, tab_tax = st.tabs(
        ["Overview", "Cash Movement", "ETFs", "Stocks", "Dividends", "Fees", "Taxes"]
    )

    # =========================
    # 1) Cash Movement
    # =========================
    df_cash = df[df.apply(_is_cash_movement, axis=1)].copy()

    # =========================
    # 2) ETFs (trades reales)
    # =========================
    df_etf = df[
        (df.get("Security Type", "").astype(str).str.upper().isin(ETF_TYPES))
        & (df.apply(_is_trade_real, axis=1))
    ].copy()

    # =========================
    # 3) Stocks (incluye ADR + Funds + Bonds por ahora)
    # =========================
    df_stock = df[
        (df.get("Security Type", "").astype(str).str.upper().isin(STOCK_TYPES))
        & (df.apply(_is_trade_real, axis=1))
    ].copy()

    # =========================
    # 4) Dividends (neto = dividend + tax, agrupado)
    # =========================
    df_div_gross = df[df.apply(_is_dividend, axis=1)].copy()

    # Tax asociado a dividendos: impuesto que menciona dividend o cae en mismos símbolos/fechas
    df_tax_all = df[df.apply(_is_tax, axis=1)].copy()
    if "SYMBOL" in df.columns:
        df_tax_div = df_tax_all[df_tax_all["SYMBOL"].isin(df_div_gross.get("SYMBOL", pd.Series([])))]
    else:
        df_tax_div = df_tax_all.copy()

    # Agregado simple (no “inventamos” pairing perfecto: usamos Settlement Date + Symbol)
    agg_keys = [date_col]
    if "SYMBOL" in df.columns:
        agg_keys.append("SYMBOL")

    def _sumcol(dfx: pd.DataFrame, col: str) -> pd.Series:
        if col not in dfx.columns:
            return pd.Series(dtype=float)
        return dfx.groupby(agg_keys)[col].sum()

    gross = _sumcol(df_div_gross, "Net Amount (Base Currency)").rename("Dividend (Gross, Base)")
    tax = _sumcol(df_tax_div, "Net Amount (Base Currency)").rename("Dividend Tax (Base)")
    div_table = pd.concat([gross, tax], axis=1).fillna(0.0)
    div_table["Dividend (Net, Base)"] = div_table["Dividend (Gross, Base)"] + div_table["Dividend Tax (Base)"]
    div_table = div_table.reset_index()

    # =========================
    # 5) Fees
    # =========================
    df_fee = df[df.apply(_is_fee, axis=1)].copy()
    # Sacamos los cash movements y taxes para no mezclar
    df_fee = df_fee[~df_fee.apply(_is_cash_movement, axis=1)]
    df_fee = df_fee[~df_fee.apply(_is_tax, axis=1)]
    df_fee = df_fee[~df_fee.apply(_is_dividend, axis=1)]

    # =========================
    # 6) Taxes
    # =========================
    df_tax = df_tax_all.copy()

    # =========================
    # Overview
    # =========================
    with tab_over:
        c1, c2, c3, c4 = st.columns(4)
        cash_in = df_cash[df_cash["Transaction Type"].astype(str).str.upper().eq("FEDERAL FUNDS RECEIVED")][
            "Net Amount (Base Currency)"
        ].sum() if "Net Amount (Base Currency)" in df_cash.columns else 0.0

        cash_out = df_cash[df_cash["Transaction Type"].astype(str).str.upper().eq("FEDERAL FUNDS SENT")][
            "Net Amount (Base Currency)"
        ].sum() if "Net Amount (Base Currency)" in df_cash.columns else 0.0

        etf_trades = len(df_etf)
        stock_trades = len(df_stock)

        with c1:
            _kpi("Cash In (Base)", _fmt_money(cash_in))
        with c2:
            _kpi("Cash Out (Base)", _fmt_money(cash_out))
        with c3:
            _kpi("ETF Trades", f"{etf_trades:,}")
        with c4:
            _kpi("Stock Trades", f"{stock_trades:,}")

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
        st.markdown(
            f'<span class="pill">Rango: {from_d} → {to_d}</span> &nbsp; '
            f'<span class="pill">Filas: {len(df):,}</span>',
            unsafe_allow_html=True,
        )

        st.caption("Nota: todavía estamos en fase de lectura y clasificación. Sin rentabilidad ni cálculos de cartera.")
        st.dataframe(df.head(25), use_container_width=True, height=420)

    # =========================
    # Cash Movement tab
    # =========================
    with tab_cash:
        st.subheader("Cash Movement")
        st.caption("Solo FEDERAL FUNDS RECEIVED / FEDERAL FUNDS SENT (excluye ACTIVITY WITHIN YOUR ACCT).")

        cols_cash = [
            "Process Date",
            "Settlement Date",
            "Net Amount (Base Currency)",
            "Transaction Type",
            "Security Description",
            "Transaction Description",
        ]
        view = _select_columns(df_cash, cols_cash).sort_values("Settlement Date")
        st.dataframe(view, use_container_width=True, height=520)

    # =========================
    # ETFs tab
    # =========================
    with tab_etf:
        st.subheader("ETFs")
        st.caption("Security Type = EXCHANGE TRADED FUNDS y solo BUY/SELL reales.")

        cols_long = [
            "Settlement Date",
            "Process Date",
            "Net Amount (Base Currency)",
            "Transaction Description",
            "Transaction Type",
            "Security Description",
            "Net Amount (Transaction Currency)",
            "Buy/Sell",
            "Quantity",
            "Price (Transaction Currency)",
            "Transaction Currency",
            "Security Type",
            "Payee",
            "Paid For (Name)",
            "Request Reason",
            "CUSIP",
            "FX Rate (To Base)",
            "ISIN",
            "SEDOL",
            "SYMBOL",
            "Trade Date",
        ]
        view = _select_columns(df_etf, cols_long).sort_values("Settlement Date")
        st.dataframe(view, use_container_width=True, height=520)

    # =========================
    # Stocks tab
    # =========================
    with tab_stock:
        st.subheader("Stocks")
        st.caption("Incluye COMMON STOCK + COMMON STOCK ADR. (Por ahora también: OPEN END TAXABLE LOAD FUND + INDEX LINKED CORP BOND)")

        cols_long = [
            "Settlement Date",
            "Process Date",
            "Net Amount (Base Currency)",
            "Transaction Description",
            "Transaction Type",
            "Security Description",
            "Net Amount (Transaction Currency)",
            "Buy/Sell",
            "Quantity",
            "Price (Transaction Currency)",
            "Transaction Currency",
            "Security Type",
            "Payee",
            "Paid For (Name)",
            "Request Reason",
            "CUSIP",
            "FX Rate (To Base)",
            "ISIN",
            "SEDOL",
            "SYMBOL",
            "Trade Date",
        ]
        view = _select_columns(df_stock, cols_long).sort_values("Settlement Date")
        st.dataframe(view, use_container_width=True, height=520)

    # =========================
    # Dividends tab
    # =========================
    with tab_div:
        st.subheader("Dividends")
        st.caption("Neto = Dividend (gross) + Dividend tax (negativo). Agregado por Settlement Date y Symbol.")

        show_cols = agg_keys + ["Dividend (Gross, Base)", "Dividend Tax (Base)", "Dividend (Net, Base)"]
        st.dataframe(div_table[show_cols].sort_values(agg_keys), use_container_width=True, height=520)

        with st.expander("Ver filas raw (dividendos)"):
            st.dataframe(
                _select_columns(
                    df_div_gross,
                    [
                        "Settlement Date",
                        "SYMBOL",
                        "Net Amount (Base Currency)",
                        "Transaction Type",
                        "Security Description",
                        "Transaction Description",
                        "Transaction code",
                    ],
                ).sort_values(["Settlement Date", "SYMBOL"]),
                use_container_width=True,
                height=420,
            )

        with st.expander("Ver filas raw (taxes asociados / candidatos)"):
            st.dataframe(
                _select_columns(
                    df_tax_div,
                    [
                        "Settlement Date",
                        "SYMBOL",
                        "Net Amount (Base Currency)",
                        "Transaction Type",
                        "Security Description",
                        "Transaction Description",
                        "Transaction code",
                    ],
                ).sort_values(["Settlement Date", "SYMBOL"]),
                use_container_width=True,
                height=420,
            )

    # =========================
    # Fees tab
    # =========================
    with tab_fee:
        st.subheader("Fees")
        st.caption("Fees/costs (clasificación simple). No incluye Cash Movement, Taxes ni Dividends.")
        cols_fee = [
            "Settlement Date",
            "Process Date",
            "Net Amount (Base Currency)",
            "Transaction Type",
            "Transaction Description",
            "Security Description",
            "Transaction code",
            "Commission",
        ]
        view = _select_columns(df_fee, cols_fee).sort_values("Settlement Date")
        st.dataframe(view, use_container_width=True, height=520)

    # =========================
    # Taxes tab
    # =========================
    with tab_tax:
        st.subheader("Taxes")
        st.caption("Taxes (incluye NRA / foreign tax withheld / etc).")
        cols_tax = [
            "Settlement Date",
            "Process Date",
            "Net Amount (Base Currency)",
            "Transaction Type",
            "Transaction Description",
            "Security Description",
            "Transaction code",
        ]
        view = _select_columns(df_tax, cols_tax).sort_values("Settlement Date")
        st.dataframe(view, use_container_width=True, height=520)
