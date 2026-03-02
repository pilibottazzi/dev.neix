# tools/comerciales/transactions_analyzer.py
from __future__ import annotations

import io
from typing import List, Optional

import numpy as np
import pandas as pd
import streamlit as st


# =========================
# UI (simple + prolija)
# =========================
NEIX_RED = "#ef4444"


def _ui_css() -> None:
    st.markdown(
        f"""
        <style>
          .ta-title {{
            font-weight: 900;
            letter-spacing: .01em;
            font-size: 2.0rem;
            margin: 0 0 .25rem 0;
          }}
          .ta-sub {{
            color: #6b7280;
            margin: 0 0 1.15rem 0;
            font-size: .98rem;
          }}

          .ta-pill {{
            border: 1px solid rgba(0,0,0,.08);
            border-radius: 16px;
            padding: 12px 14px;
            background: #fff;
            box-shadow: 0 2px 10px rgba(0,0,0,.04);
          }}

          .ta-kpis {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 10px;
          }}
          @media (max-width: 950px) {{
            .ta-kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
          }}
          .ta-kpi {{
            border: 1px solid rgba(0,0,0,.08);
            border-radius: 16px;
            padding: 12px 14px;
            background: #fff;
          }}
          .ta-kpi .label {{
            color:#6b7280;
            font-size:.85rem;
            font-weight: 800;
            margin-bottom: 6px;
          }}
          .ta-kpi .value {{
            font-size: 1.85rem;
            font-weight: 900;
            letter-spacing: .01em;
          }}
          .ta-kpi .hint {{
            color:#6b7280;
            font-size:.82rem;
            margin-top: 4px;
          }}

          /* Tabs minimal */
          .stTabs [data-baseweb="tab-list"] {{
            gap: 6px;
            border-bottom: 1px solid rgba(0,0,0,0.08);
            padding-left: 2px;
            margin-top: 6px;
          }}
          .stTabs [data-baseweb="tab"] {{
            background: transparent;
            border: none;
            font-weight: 900;
            color: #6b7280;
            padding: 10px 14px;
            font-size: .95rem;
          }}
          .stTabs [aria-selected="true"] {{
            color:#111827;
            border-bottom: 3px solid {NEIX_RED};
          }}

          div[data-testid="stDataFrame"] {{
            border: 1px solid rgba(0,0,0,.08);
            border-radius: 14px;
            overflow: hidden;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _money_fmt(x: float) -> str:
    try:
        return f"{x:,.2f}"
    except Exception:
        return str(x)


def _safe_str(x: object) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x)


def _upper(x: object) -> str:
    return _safe_str(x).strip().upper()


def _pick_existing_cols(df: pd.DataFrame, cols: List[str]) -> List[str]:
    return [c for c in cols if c in df.columns]


# =========================
# Pershing columns
# =========================
COL_PROCESS_DATE = "Process Date"
COL_SETTLEMENT_DATE = "Settlement Date"
COL_NET_BASE = "Net Amount (Base Currency)"
COL_TX_TYPE = "Transaction Type"
COL_SEC_DESC = "Security Description"
COL_TX_DESC = "Transaction Description"

COL_BUYSELL = "Buy/Sell"
COL_QTY = "Quantity"
COL_PRICE = "Price (Transaction Currency)"
COL_SYMBOL = "SYMBOL"
COL_SECURITY_TYPE = "Security Type"

# Phase 1 rules
CASH_IN = "FEDERAL FUNDS RECEIVED"
CASH_OUT = "FEDERAL FUNDS SENT"
SEC_TYPE_ETF = "EXCHANGE TRADED FUNDS"


# =========================
# Excel reading (robusto)
# =========================
def _sheet_to_df(obj) -> pd.DataFrame:
    """
    pandas puede devolver:
      - DataFrame (sheet única)
      - dict[str, DataFrame] (múltiples sheets)
    """
    if isinstance(obj, dict):
        # preferimos una sheet con nombre "Transactions" si existe, sino la primera
        for k in obj.keys():
            if str(k).strip().lower() == "transactions":
                return obj[k]
        return next(iter(obj.values()))
    return obj


def _find_header_row(raw: pd.DataFrame) -> int:
    """
    Pershing trae metadata arriba. Detectamos la fila donde está el header real
    buscando la celda "Process Date".
    """
    target = _upper(COL_PROCESS_DATE)
    limit = min(len(raw), 120)  # margen grande por si el reporte trae mucho texto arriba

    for r in range(limit):
        row = raw.iloc[r].astype(str).map(_upper)
        if (row == target).any():
            return r

    raise ValueError("No pude encontrar la fila de encabezados (no aparece 'Process Date').")


def _read_pershing_transactions_excel(file_bytes: bytes, sheet_name: Optional[str] = None) -> pd.DataFrame:
    bio = io.BytesIO(file_bytes)

    # 1) crudo sin header para detectar fila
    raw_obj = pd.read_excel(bio, sheet_name=sheet_name, header=None, engine="openpyxl")
    raw = _sheet_to_df(raw_obj)

    header_row = _find_header_row(raw)

    # 2) leer con header correcto
    bio2 = io.BytesIO(file_bytes)
    df_obj = pd.read_excel(bio2, sheet_name=sheet_name, header=header_row, engine="openpyxl")
    df = _sheet_to_df(df_obj)

    # limpiar Unnamed (FIX: si df fuese dict, acá explotaba: ahora ya es DF)
    df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")].copy()
    df = df.dropna(how="all").copy()

    return df


def _coerce_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def _coerce_number(s: pd.Series) -> pd.Series:
    def to_float(v: object) -> float:
        if v is None:
            return np.nan
        try:
            if pd.isna(v):
                return np.nan
        except Exception:
            pass
        if isinstance(v, (int, float, np.integer, np.floating)):
            return float(v)
        t = str(v).strip()
        if not t:
            return np.nan
        t = t.replace("$", "").replace(",", "")
        try:
            return float(t)
        except Exception:
            return np.nan

    return s.map(to_float)


def standardize_df(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()

    for c in [COL_PROCESS_DATE, COL_SETTLEMENT_DATE]:
        if c in d.columns:
            d[c] = _coerce_date(d[c])

    for c in [COL_NET_BASE, COL_QTY, COL_PRICE]:
        if c in d.columns:
            d[c] = _coerce_number(d[c])

    for c in [COL_TX_TYPE, COL_SEC_DESC, COL_TX_DESC, COL_BUYSELL, COL_SYMBOL, COL_SECURITY_TYPE]:
        if c in d.columns:
            d[c] = d[c].map(_safe_str)

    return d


def _filter_by_date(df: pd.DataFrame, date_col: str, start: Optional[pd.Timestamp], end: Optional[pd.Timestamp]) -> pd.DataFrame:
    if date_col not in df.columns:
        return df.copy()

    s = pd.to_datetime(df[date_col], errors="coerce")
    m = pd.Series(True, index=df.index)

    if start is not None:
        m &= s >= pd.to_datetime(start)
    if end is not None:
        m &= s <= pd.to_datetime(end)

    return df.loc[m].copy()


# =========================
# CASH_MOVEMENT (fase 1)
# =========================
def build_cash_movements(df: pd.DataFrame) -> pd.DataFrame:
    req = [COL_PROCESS_DATE, COL_SETTLEMENT_DATE, COL_NET_BASE, COL_TX_TYPE, COL_SEC_DESC]
    missing = [c for c in req if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas para CASH_MOVEMENT: {missing}")

    d = df.copy()
    d["_tx_u"] = d[COL_TX_TYPE].map(_upper)

    # SOLO Federal Funds (y por ende NO aparece Activity Within Your Acct ni fees)
    d = d[d["_tx_u"].isin([CASH_IN, CASH_OUT])].copy()

    d["direction"] = np.where(d["_tx_u"] == CASH_IN, "IN", "OUT")

    out = d[[COL_PROCESS_DATE, COL_SETTLEMENT_DATE, COL_NET_BASE, COL_TX_TYPE, COL_SEC_DESC, "direction"]].copy()
    out = out.sort_values(by=[COL_SETTLEMENT_DATE, COL_PROCESS_DATE], ascending=True, na_position="last")
    return out.reset_index(drop=True)


# =========================
# TRADE (fase 1: ETFs + BUY/SELL)
# =========================
def _norm_buysell(x: object) -> str:
    s = _upper(x)
    if s in {"BUY", "B"}:
        return "BUY"
    if s in {"SELL", "S"}:
        return "SELL"
    return ""


def build_trades_etf(df: pd.DataFrame) -> pd.DataFrame:
    req = [COL_SECURITY_TYPE, COL_BUYSELL, COL_SYMBOL, COL_SETTLEMENT_DATE]
    missing = [c for c in req if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas para TRADE (ETF): {missing}")

    d = df.copy()

    d["_sec_type_u"] = d[COL_SECURITY_TYPE].map(_upper)
    d = d[d["_sec_type_u"] == SEC_TYPE_ETF].copy()

    d["buy_sell_norm"] = d[COL_BUYSELL].map(_norm_buysell)
    d = d[d["buy_sell_norm"].isin(["BUY", "SELL"])].copy()

    cols = _pick_existing_cols(
        d,
        [
            COL_PROCESS_DATE,
            COL_SETTLEMENT_DATE,
            COL_SYMBOL,
            "buy_sell_norm",
            COL_QTY,
            COL_PRICE,
            COL_NET_BASE,
            COL_SEC_DESC,
            COL_TX_TYPE,
        ],
    )

    out = d[cols].copy()
    out = out.sort_values(by=[COL_SETTLEMENT_DATE, COL_PROCESS_DATE], ascending=True, na_position="last")
    return out.reset_index(drop=True)


# =========================
# Render (entrypoint)
# =========================
def render(_ctx=None) -> None:
    _ui_css()

    st.markdown("<div class='ta-title'>🧾 Movimientos CV — Transactions Analyzer</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='ta-sub'>Subí el Excel exportado (Transactions). Arrancamos simple: cash (FEDERAL FUNDS) y trades (ETFs) para ordenar la lectura.</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1.35, 1.0, 0.9])

    with c1:
        up = st.file_uploader("Subí el Excel exportado (Transactions)", type=["xlsx", "xls"])

    with c2:
        date_col = st.selectbox(
            "Fecha para análisis",
            options=[COL_SETTLEMENT_DATE, COL_PROCESS_DATE],
            index=0,
        )

    with c3:
        st.markdown(
            "<div class='ta-pill'><b>Fase 1</b><br/>Solo <b>FEDERAL FUNDS</b> en cash y <b>ETFs BUY/SELL</b> en trades.</div>",
            unsafe_allow_html=True,
        )

    if not up:
        st.info("Subí un Excel para empezar.")
        return

    try:
        df_raw = _read_pershing_transactions_excel(up.getvalue(), sheet_name=None)
        df = standardize_df(df_raw)
    except Exception as e:
        st.error("No pude leer el Excel (o detectar la fila de encabezados).")
        st.exception(e)
        return

    # fechas rango
    if date_col in df.columns:
        ds = pd.to_datetime(df[date_col], errors="coerce").dropna()
    else:
        ds = pd.Series([], dtype="datetime64[ns]")

    if len(ds) > 0:
        min_d, max_d = ds.min().date(), ds.max().date()
        f1, f2 = st.columns([1, 1])
        with f1:
            start = st.date_input("Desde", value=min_d)
        with f2:
            end = st.date_input("Hasta", value=max_d)
        df = _filter_by_date(df, date_col, pd.Timestamp(start), pd.Timestamp(end))
    else:
        st.warning("No pude inferir fechas para filtrar (columna de fecha vacía o inexistente).")

    # armar datasets
    try:
        cash = build_cash_movements(df)
    except Exception as e:
        cash = pd.DataFrame()
        st.warning("No pude armar CASH_MOVEMENT con este archivo.")
        st.exception(e)

    try:
        trades = build_trades_etf(df)
    except Exception as e:
        trades = pd.DataFrame()
        st.warning("No pude armar TRADE (ETF) con este archivo.")
        st.exception(e)

    # KPIs Cash
    if not cash.empty and COL_NET_BASE in cash.columns and "direction" in cash.columns:
        cash_in = float(cash.loc[cash["direction"] == "IN", COL_NET_BASE].sum())
        cash_out = float(cash.loc[cash["direction"] == "OUT", COL_NET_BASE].sum())
        cash_net = cash_in + cash_out
        cash_n = int(len(cash))
    else:
        cash_in = cash_out = cash_net = 0.0
        cash_n = 0

    st.markdown(
        f"""
        <div class="ta-kpis">
          <div class="ta-kpi">
            <div class="label">CASH — Ingresos (FEDERAL FUNDS RECEIVED)</div>
            <div class="value">{_money_fmt(cash_in)}</div>
            <div class="hint">Suma de Net Amount (Base Currency)</div>
          </div>
          <div class="ta-kpi">
            <div class="label">CASH — Egresos (FEDERAL FUNDS SENT)</div>
            <div class="value">{_money_fmt(cash_out)}</div>
            <div class="hint">Suma de Net Amount (Base Currency)</div>
          </div>
          <div class="ta-kpi">
            <div class="label">CASH — Neto</div>
            <div class="value">{_money_fmt(cash_net)}</div>
            <div class="hint">Ingresos + Egresos (con signo)</div>
          </div>
          <div class="ta-kpi">
            <div class="label">CASH — Movimientos</div>
            <div class="value">{cash_n}</div>
            <div class="hint">Cantidad de filas (solo FEDERAL FUNDS)</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_cash, tab_trade = st.tabs(["CASH_MOVEMENT", "TRADE"])

    with tab_cash:
        st.markdown("### CASH_MOVEMENT")
        st.caption("Solo FEDERAL FUNDS RECEIVED / FEDERAL FUNDS SENT. (Fees y Activity quedan fuera por ahora.)")

        show_cols = _pick_existing_cols(
            cash,
            [COL_PROCESS_DATE, COL_SETTLEMENT_DATE, COL_NET_BASE, COL_TX_TYPE, COL_SEC_DESC, "direction"],
        )

        if cash.empty:
            st.info("No hay movimientos cash (FEDERAL FUNDS) para el filtro actual.")
        else:
            st.dataframe(cash[show_cols], use_container_width=True, hide_index=True)

            out = io.BytesIO()
            cash[show_cols].to_excel(out, index=False, sheet_name="CASH_MOVEMENT")
            st.download_button(
                "Descargar CASH_MOVEMENT (Excel)",
                data=out.getvalue(),
                file_name="cash_movement.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    with tab_trade:
        st.markdown("### TRADE")
        st.caption("Solo ETFs (Security Type = EXCHANGE TRADED FUNDS) + Buy/Sell normalizado (BUY/SELL).")

        if trades.empty:
            st.info("No hay trades ETF BUY/SELL para el filtro actual.")
        else:
            n_tr = len(trades)
            buy_n = int((trades["buy_sell_norm"] == "BUY").sum()) if "buy_sell_norm" in trades.columns else 0
            sell_n = int((trades["buy_sell_norm"] == "SELL").sum()) if "buy_sell_norm" in trades.columns else 0
            symbols_n = int(trades[COL_SYMBOL].nunique()) if COL_SYMBOL in trades.columns else 0

            a, b, c = st.columns([1, 1, 2])
            a.metric("Trades", n_tr)
            b.metric("BUY / SELL", f"{buy_n} / {sell_n}")
            c.metric("Symbols", symbols_n)

            show_cols = _pick_existing_cols(
                trades,
                [COL_SETTLEMENT_DATE, COL_SYMBOL, "buy_sell_norm", COL_QTY, COL_PRICE, COL_NET_BASE, COL_SEC_DESC],
            )
            st.dataframe(trades[show_cols], use_container_width=True, hide_index=True)

            out = io.BytesIO()
            trades[show_cols].to_excel(out, index=False, sheet_name="TRADE_ETF")
            st.download_button(
                "Descargar TRADE (Excel)",
                data=out.getvalue(),
                file_name="trade_etf.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
