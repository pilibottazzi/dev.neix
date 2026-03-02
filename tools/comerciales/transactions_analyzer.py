# tools/comerciales/transactions_analyzer.py

from __future__ import annotations
import io
import re
import pandas as pd
import numpy as np
import streamlit as st


# =========================================================
# Helpers
# =========================================================

def _norm_col(s: str) -> str:
    return (
        str(s)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
    )


def _to_numeric(x):
    if pd.isna(x):
        return 0.0
    s = str(x).strip()
    s = s.replace(".", "").replace(",", ".") if "," in s and "." in s else s
    try:
        return float(s)
    except:
        return 0.0


def _detect_header_row(df_raw: pd.DataFrame) -> int:
    """
    Busca fila que contenga 'Process Date'
    """
    for i in range(min(20, len(df_raw))):
        row = df_raw.iloc[i].astype(str).str.lower().tolist()
        if any("process date" in c for c in row):
            return i
    raise ValueError("No se encontró fila de encabezados (Process Date).")


def _read_pershing_excel(file_bytes: bytes) -> pd.DataFrame:
    df_raw = pd.read_excel(io.BytesIO(file_bytes), header=None)

    header_row = _detect_header_row(df_raw)

    df = pd.read_excel(
        io.BytesIO(file_bytes),
        header=header_row
    )

    df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed")]

    df.columns = [_norm_col(c) for c in df.columns]

    # Normalizaciones clave
    if "settlement_date" in df.columns:
        df["settlement_date"] = pd.to_datetime(df["settlement_date"], errors="coerce")

    if "net_amount_base_currency" in df.columns:
        df["net_amount_base_currency"] = df["net_amount_base_currency"].apply(_to_numeric)

    if "net_amount_transaction_currency" in df.columns:
        df["net_amount_transaction_currency"] = df["net_amount_transaction_currency"].apply(_to_numeric)

    if "buy/sell" in df.columns:
        df["buy_sell"] = (
            df["buy/sell"]
            .astype(str)
            .str.upper()
            .str.strip()
        )
    else:
        df["buy_sell"] = "-"

    return df


# =========================================================
# Clasificaciones
# =========================================================

def _cash_movement(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        df["transaction_type"].isin(
            ["FEDERAL FUNDS RECEIVED", "FEDERAL FUNDS SENT"]
        )
    ].copy()


def _etfs(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        (df["security_type"] == "EXCHANGE TRADED FUNDS")
        & (df["buy_sell"].isin(["BUY", "SELL"]))
    ].copy()


def _stocks(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        (df["security_type"].isin(["COMMON STOCK", "COMMON STOCK ADR"]))
        & (df["buy_sell"].isin(["BUY", "SELL"]))
    ].copy()


def _dividends_net(df: pd.DataFrame) -> pd.DataFrame:
    div_mask = df["transaction_type"].str.contains("DIVIDEND", na=False)
    tax_mask = df["transaction_type"].str.contains("TAX", na=False)

    df_div = df[div_mask].copy()
    df_tax = df[tax_mask].copy()

    df_all = pd.concat([df_div, df_tax])

    grouped = (
        df_all.groupby(
            ["settlement_date", "symbol", "security_description"],
            dropna=False
        )["net_amount_base_currency"]
        .sum()
        .reset_index()
    )

    grouped.rename(
        columns={"net_amount_base_currency": "net_dividend_usd"},
        inplace=True
    )

    return grouped


def _fees(df: pd.DataFrame) -> pd.DataFrame:
    fee_keywords = [
        "FEE",
        "CUSTODY",
        "ASSET BASED",
        "PAPER DELIVERY",
        "INT. CHARGED"
    ]

    mask = df["transaction_type"].astype(str).str.contains(
        "|".join(fee_keywords),
        case=False,
        na=False
    )

    return df[mask].copy()


def _taxes(df: pd.DataFrame) -> pd.DataFrame:
    mask = df["transaction_type"].astype(str).str.contains(
        "TAX",
        case=False,
        na=False
    )

    return df[mask].copy()


# =========================================================
# Render
# =========================================================

def render(context=None):

    st.title("📊 Movimientos CV — Transactions Analyzer")

    uploaded = st.file_uploader(
        "Subí el Excel exportado (Transactions)",
        type=["xlsx", "xls"]
    )

    if not uploaded:
        st.info("Esperando archivo.")
        return

    try:
        df = _read_pershing_excel(uploaded.getvalue())
    except Exception as e:
        st.error(f"No pude leer el Excel: {e}")
        return

    if "settlement_date" not in df.columns:
        st.error("No encontré Settlement Date.")
        return

    # Filtro fechas
    min_date = df["settlement_date"].min()
    max_date = df["settlement_date"].max()

    col1, col2 = st.columns(2)
    with col1:
        desde = st.date_input("Desde", min_date)
    with col2:
        hasta = st.date_input("Hasta", max_date)

    df = df[
        (df["settlement_date"] >= pd.to_datetime(desde))
        & (df["settlement_date"] <= pd.to_datetime(hasta))
    ].copy()

    # Clasificaciones
    df_cash = _cash_movement(df)
    df_etf = _etfs(df)
    df_stocks = _stocks(df)
    df_div = _dividends_net(df)
    df_fees = _fees(df)
    df_taxes = _taxes(df)

    tabs = st.tabs([
        "Overview",
        "Cash Movement",
        "ETFs",
        "Stocks",
        "Dividends",
        "Fees",
        "Taxes"
    ])

    # =====================================================
    # OVERVIEW
    # =====================================================
    with tabs[0]:
        st.subheader("Resumen General")

        cash_in = df_cash[
            df_cash["transaction_type"] == "FEDERAL FUNDS RECEIVED"
        ]["net_amount_base_currency"].sum()

        cash_out = df_cash[
            df_cash["transaction_type"] == "FEDERAL FUNDS SENT"
        ]["net_amount_base_currency"].sum()

        trade_net = (
            df_etf["net_amount_base_currency"].sum()
            + df_stocks["net_amount_base_currency"].sum()
        )

        dividends_net = df_div["net_dividend_usd"].sum()
        fees_total = df_fees["net_amount_base_currency"].sum()
        taxes_total = df_taxes["net_amount_base_currency"].sum()

        col1, col2, col3 = st.columns(3)

        col1.metric("Cash In", f"{cash_in:,.2f}")
        col2.metric("Cash Out", f"{cash_out:,.2f}")
        col3.metric("Net Trades", f"{trade_net:,.2f}")

        col4, col5, col6 = st.columns(3)
        col4.metric("Net Dividends", f"{dividends_net:,.2f}")
        col5.metric("Fees", f"{fees_total:,.2f}")
        col6.metric("Taxes", f"{taxes_total:,.2f}")

    # =====================================================
    # CASH MOVEMENT
    # =====================================================
    with tabs[1]:
        st.subheader("Cash Movement")
        st.dataframe(df_cash[[
            "process_date",
            "settlement_date",
            "net_amount_base_currency",
            "transaction_type",
            "security_description"
        ]])

    # =====================================================
    # ETFs
    # =====================================================
    with tabs[2]:
        st.subheader("ETFs Trades")
        st.dataframe(df_etf)

    # =====================================================
    # STOCKS
    # =====================================================
    with tabs[3]:
        st.subheader("Stocks Trades")
        st.dataframe(df_stocks)

    # =====================================================
    # DIVIDENDS
    # =====================================================
    with tabs[4]:
        st.subheader("Net Dividends (Dividend - Tax)")
        st.dataframe(df_div)

    # =====================================================
    # FEES
    # =====================================================
    with tabs[5]:
        st.subheader("Fees")
        st.dataframe(df_fees)

    # =====================================================
    # TAXES
    # =====================================================
    with tabs[6]:
        st.subheader("Taxes")
        st.dataframe(df_taxes)
