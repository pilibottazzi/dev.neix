# tools/cartera.py
from __future__ import annotations

import os
import io
import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd
import streamlit as st
from scipy import optimize

# =========================
# PDF (ReportLab)
# =========================
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
)
from reportlab.lib.styles import getSampleStyleSheet


# =========================
# Config
# =========================
CASHFLOW_PATH = os.path.join("data", "cashflows_completos.xlsx")
LOGO_PATH = os.path.join("data", "Neix_logo.png")  # ✅ tu logo en /data

# TIR fija (no UI)
TIR_MIN = -15.0
TIR_MAX = 20.0

# Precios USD MEP
PRICE_SUFFIX = "D"

# Excepciones PESOS -> USD (cuando no es solo + "D")
PESOS_TO_USD_OVERRIDES: dict[str, str] = {
    # =========================
    # Provincia de Bs. As.
    # =========================
    "BPOB7": "BPB7D",
    "BPOB8": "BPB8D",
    "BPOC7": "BPC7D",
    "BPOD7": "BPD7D",

    # Familia BPA / BPB / BPC (si el cashflow viene sin la O)
    "BPA7": "BPA7D",
    "BPA8": "BPA8D",
    "BPB7": "BPB7D",
    "BPB8": "BPB8D",
    "BPC7": "BPC7D",

    # =========================
    # Bonos soberanos USD-link
    # =========================
    "AL30": "AL30D",
    "AL35": "AL35D",
    "AE38": "AE38D",
    "AL41": "AL41D",
    "GD30": "GD30D",
    "GD35": "GD35D",
    "GD38": "GD38D",
    "GD41": "GD41D",

    # =========================
    # Otros / atípicos
    # =========================
    "BPY26": "BPY6D",
}


# =========================
# Utils parse num AR
# =========================
def parse_ar_number(x) -> float:
    """
    Convierte:
      89.190,00 -> 89190.00
      22.733.580,97 -> 22733580.97
      6323 -> 6323.0
    """
    if x is None:
        return np.nan
    s = str(x).strip()
    if s == "" or s.lower() in {"-", "nan", "none"}:
        return np.nan
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return np.nan


def usd_fix_if_needed(ticker: str, raw_last: str, value: float) -> float:
    """
    Fix para tickers USD terminados en D.
    Caso típico: viene "6097" y era 60.97 (VN100).

    Regla:
      - termina en D
      - raw NO tiene '.' ni ','
      => dividir por 100
    """
    if not np.isfinite(value):
        return value

    t = (ticker or "").strip().upper()
    raw = (raw_last or "").strip()

    if not t.endswith("D"):
        return value

    if ("," in raw) or ("." in raw):
        return value

    return value / 100.0


# =========================
# XNPV / XIRR
# =========================
def xnpv(rate: float, cashflows: list[tuple[dt.datetime, float]]) -> float:
    chron = sorted(cashflows, key=lambda x: x[0])
    t0 = chron[0][0]
    if rate <= -0.999999:
        return np.nan

    out = 0.0
    for t, cf in chron:
        years = (t - t0).days / 365.0
        out += cf / (1.0 + rate) ** years
    return out


def xirr(cashflows: list[tuple[dt.datetime, float]], guess: float = 0.10) -> float:
    try:
        r = optimize.newton(lambda rr: xnpv(rr, cashflows), guess, maxiter=200)
        return float(r) * 100.0
    except Exception:
        return np.nan


# =========================
# Cashflows helpers
# =========================
def _settlement(plazo_dias: int) -> dt.datetime:
    base = pd.Timestamp.today().normalize().to_pydatetime()
    return base + dt.timedelta(days=int(plazo_dias))


def _future_cashflows(df: pd.DataFrame, settlement: dt.datetime) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["flujo_total"] = pd.to_numeric(df["flujo_total"], errors="coerce")
    df = df.dropna(subset=["date", "flujo_total"])
    df = df[df["date"] > settlement].sort_values("date")
    return df


# =========================
# Normalizaciones meta
# =========================
def normalize_law(x: str) -> str:
    s = (x or "").strip().upper()
    s = s.replace(".", "").replace("-", " ").replace("_", " ")
    s = " ".join(s.split())
    if s in {"ARG", "AR", "LOCAL", "LEY LOCAL", "ARGENTINA"}:
        return "ARG"
    if s in {"NYC", "NY", "NEW YORK", "NEWYORK", "LEY NY", "LEY NEW YORK", "N Y", "N Y C"}:
        return "NY"
    if s in {"", "NA", "NONE", "NAN"}:
        return "NA"
    return s


def law_cell_label(norm: str) -> str:
    # ✅ texto corto
    if norm == "ARG":
        return "Ley local"
    if norm == "NY":
        return "Ley NY"
    if norm == "NA":
        return "Sin ley"
    return norm


def normalize_issuer(x: str) -> str:
    s = (x or "").strip().upper()
    s = s.replace("_", " ").replace("-", " ")
    s = " ".join(s.split())
    return s if s else "NA"


def normalize_desc(x: str) -> str:
    s = (x or "").strip().upper()
    s = s.replace("_", " ").replace("-", " ")
    s = " ".join(s.split())
    return s if s else "NA"


# =========================
# ONs corporativas: O -> D
# =========================
def is_corporativo(issuer_norm: str) -> bool:
    s = (issuer_norm or "").strip().upper()
    return s in {"CORPORATIVO", "CORPORATE", "CORP", "CORPORAT"}


def on_usd_ticker_from_species(species: str) -> str:
    """
    Regla:
      - si termina en 'O' => reemplazar por 'D'
      - si ya termina en 'D' => dejar
      - si no termina en O ni D => agregar 'D'
    """
    sp = (species or "").strip().upper()
    if sp.endswith("O") and len(sp) >= 2:
        return sp[:-1] + "D"
    if sp.endswith("D"):
        return sp
    return sp + "D"


# =========================
# Load cashflows
# =========================
def load_cashflows(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No existe el archivo: {path}. Subilo al repo (ej: data/cashflows_completos.xlsx)."
        )

    df = pd.read_excel(path)
    df.columns = df.columns.astype(str).str.strip()

    req = {"date", "species", "law", "issuer", "description", "flujo_total"}
    missing = req - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas en {path}: {sorted(missing)} (requeridas: {sorted(req)})")

    df["species"] = df["species"].astype(str).str.strip().str.upper()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["flujo_total"] = pd.to_numeric(df["flujo_total"], errors="coerce")

    df["law_norm"] = df["law"].apply(normalize_law)
    df["issuer_norm"] = df["issuer"].apply(normalize_issuer)
    df["desc_norm"] = df["description"].apply(normalize_desc)

    df = df.dropna(subset=["species", "date", "flujo_total"]).sort_values(["species", "date"])
    return df


def build_cashflow_dict(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for k, g in df.groupby("species", sort=False):
        out[str(k)] = g[["date", "flujo_total"]].copy().sort_values("date")
    return out


def build_species_meta(df: pd.DataFrame) -> pd.DataFrame:
    meta = (
        df.groupby("species")
        .agg(
            law_norm=("law_norm", lambda s: s.value_counts().index[0]),
            issuer_norm=("issuer_norm", lambda s: s.value_counts().index[0]),
            desc_norm=("desc_norm", lambda s: s.value_counts().index[0]),
            vencimiento=("date", "max"),
        )
        .reset_index()
    )
    return meta


# =========================
# Market prices (Plan B: bonos + ONs)
# =========================
def _fetch_prices_from_url(url: str) -> pd.DataFrame:
    """
    Lee una tabla de IOL y devuelve un DF con index=TICKER y cols: Precio, Volumen.
    """
    try:
        tables = pd.read_html(url)
    except ImportError as e:
        raise ImportError(
            "Faltan dependencias para leer tablas HTML. En requirements.txt agregá: lxml y html5lib."
        ) from e
    except Exception as e:
        raise RuntimeError(f"No pude leer la tabla de precios. Error: {e}") from e

    if not tables:
        return pd.DataFrame()

    t = tables[0]
    cols = {str(c).strip() for c in t.columns}

    if "Símbolo" not in cols or "Último Operado" not in cols:
        return pd.DataFrame()

    df = pd.DataFrame()
    df["Ticker"] = t["Símbolo"].astype(str).str.strip().str.upper()

    df["RawPrecio"] = t["Último Operado"].astype(str).str.strip()
    df["Precio"] = t["Último Operado"].apply(parse_ar_number)
    df["Precio"] = [
        usd_fix_if_needed(tk, raw, val)
        for tk, raw, val in zip(df["Ticker"], df["RawPrecio"], df["Precio"])
    ]

    if "Monto Operado" in cols:
        df["Volumen"] = t["Monto Operado"].apply(parse_ar_number).fillna(0)
    else:
        df["Volumen"] = 0

    df = df.dropna(subset=["Precio"]).copy()
    df = df.set_index("Ticker")
    df = df[~df.index.duplicated(keep="first")]

    return df[["Precio", "Volumen"]].sort_values("Volumen", ascending=False)


def fetch_market_prices() -> pd.DataFrame:
    """
    Une precios de BONOS + ONs en un solo DF.
    Output:
      index = Ticker (uppercase)
      cols  = Precio, Volumen
    """
    url_bonos = "https://iol.invertironline.com/mercado/cotizaciones/argentina/bonos/todos"
    url_ons = "https://iol.invertironline.com/mercado/cotizaciones/argentina/obligaciones%20negociables"

    bonos = _fetch_prices_from_url(url_bonos)
    ons = _fetch_prices_from_url(url_ons)

    if bonos.empty and ons.empty:
        return pd.DataFrame()

    allp = pd.concat([bonos, ons], axis=0)
    allp = allp.sort_values("Volumen", ascending=False)
    allp = allp[~allp.index.duplicated(keep="first")]
    return allp


def resolve_usd_ticker(species: str) -> str:
    sp = str(species).strip().upper()
    if sp.endswith("D"):
        return sp
    if sp in PESOS_TO_USD_OVERRIDES:
        return PESOS_TO_USD_OVERRIDES[sp]
    return f"{sp}{PRICE_SUFFIX}"


def pick_price_usd(prices: pd.DataFrame, species: str) -> tuple[float, float, str]:
    usd_ticker = resolve_usd_ticker(species)
    if usd_ticker in prices.index:
        px = float(prices.loc[usd_ticker, "Precio"])
        vol = float(prices.loc[usd_ticker, "Volumen"])
        return px, vol, usd_ticker
    return np.nan, np.nan, ""


# =========================
# Métricas por instrumento
# =========================
def calc_tir(cf: pd.DataFrame, precio: float, plazo_dias: int = 1) -> float:
    if not np.isfinite(precio) or precio <= 0:
        return np.nan

    settlement = _settlement(plazo_dias)
    fut = _future_cashflows(cf, settlement)
    if fut.empty:
        return np.nan

    flujos = [(settlement, -float(precio))]
    for _, r in fut.iterrows():
        flujos.append((r["date"].to_pydatetime(), float(r["flujo_total"])))

    return xirr(flujos, guess=0.10)


# =========================
# Cartera
# =========================
@dataclass
class AssetRow:
    ticker: str
    pct: float
    usd: float
    price: float
    vn: float
    tir: float
    venc: dt.date | None
    ley: str
    issuer: str
    px_ticker: str


def fmt_money_int(x: float) -> str:
    if not np.isfinite(x):
        return ""
    return f"$ {x:,.0f}".replace(",", ".")


def fmt_num_2(x: float) -> str:
    if not np.isfinite(x):
        return ""
    return f"{x:.2f}"


def fmt_pct_2(x: float) -> str:
    if not np.isfinite(x):
        return ""
    return f"{x:.2f}%"


# =========================
# Universe elegible (no se muestra, solo para options)
# =========================
def build_eligible_universe(df_cf: pd.DataFrame, prices: pd.DataFrame, plazo: int = 1) -> pd.DataFrame:
    """
    Universe elegible:
      - Tiene precio USD
      - Tiene flujos futuros
      - TIR dentro de rango fijo
    """
    cashflows = build_cashflow_dict(df_cf)
    meta = build_species_meta(df_cf).set_index("species")

    rows = []
    for sp in meta.index:
        issuer = meta.loc[sp, "issuer_norm"]

        px = vol = np.nan
        px_ticker = ""

        # 1) ON corporativa: O -> D (o +D)
        if is_corporativo(issuer):
            tk_on = on_usd_ticker_from_species(sp)
            if tk_on in prices.index:
                px = float(prices.loc[tk_on, "Precio"])
                vol = float(prices.loc[tk_on, "Volumen"])
                px_ticker = tk_on

        # 2) fallback general: ticker -> USD
        if not np.isfinite(px) or px <= 0:
            px, vol, px_ticker = pick_price_usd(prices, sp)

        if not np.isfinite(px) or px <= 0:
            continue

        cf = cashflows.get(sp)
        if cf is None or cf.empty:
            continue

        settlement = _settlement(plazo)
        fut = _future_cashflows(cf, settlement)
        if fut.empty:
            continue

        y = calc_tir(cf, px, plazo_dias=plazo)
        if not np.isfinite(y):
            continue
        if not (TIR_MIN <= y <= TIR_MAX):
            continue

        rows.append(
            {
                "Ticker": sp,
                "Ley": meta.loc[sp, "law_norm"],
                "Issuer": meta.loc[sp, "issuer_norm"],
                "Descripción": meta.loc[sp, "desc_norm"],
                "Vencimiento": meta.loc[sp, "vencimiento"],
                "Precio (USD, VN100)": float(px),
                "Ticker precio": px_ticker,
                "Volumen": float(vol) if np.isfinite(vol) else 0.0,
                "TIR (%)": float(y),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["Vencimiento"] = pd.to_datetime(out["Vencimiento"], errors="coerce")
    out = out.sort_values(["Vencimiento", "Ticker"], na_position="last").reset_index(drop=True)
    return out


# =========================
# Construcción cartera + flujos
# =========================
def build_portfolio_table(
    df_cf: pd.DataFrame,
    prices: pd.DataFrame,
    selected: list[str],
    pct_map: dict[str, float],
    capital_usd: float,
    plazo: int = 1,
) -> tuple[pd.DataFrame, dict[str, float], pd.DataFrame]:
    df_cf = df_cf.copy()
    df_cf["species"] = df_cf["species"].astype(str).str.upper().str.strip()
    selected = [str(x).upper().strip() for x in selected if str(x).strip()]

    cashflows = build_cashflow_dict(df_cf)
    meta = build_species_meta(df_cf).set_index("species")

    # normalizar % (si no suma 100, escala)
    pcts = np.array([max(0.0, float(pct_map.get(t, 0.0))) for t in selected], dtype=float)
    s = float(np.sum(pcts))
    if s <= 0:
        pcts = np.zeros_like(pcts)
    else:
        pcts = pcts / s * 100.0

    assets: list[AssetRow] = []
    for t, pct in zip(selected, pcts):
        if pct <= 0:
            continue

        px = np.nan
        px_ticker = ""

        issuer = meta.loc[t, "issuer_norm"] if t in meta.index else "NA"

        # 1) ON corporativa: O -> D (o +D)
        if t in meta.index and is_corporativo(issuer):
            tk_on = on_usd_ticker_from_species(t)
            if tk_on in prices.index:
                px = float(prices.loc[tk_on, "Precio"])
                px_ticker = tk_on

        # 2) fallback general: ticker -> USD
        if not np.isfinite(px) or px <= 0:
            px, _, px_ticker = pick_price_usd(prices, t)

        if not np.isfinite(px) or px <= 0:
            continue

        cf = cashflows.get(t)
        if cf is None or cf.empty:
            continue

        usd_amt = capital_usd * (pct / 100.0)

        # VN estimada = USD / (Precio/100) asumiendo precio por VN100
        vn = usd_amt / (px / 100.0) if px > 0 else np.nan

        y = calc_tir(cf, px, plazo_dias=plazo)

        venc = None
        if t in meta.index:
            vv = pd.to_datetime(meta.loc[t, "vencimiento"], errors="coerce")
            venc = vv.date() if pd.notna(vv) else None

        ley = meta.loc[t, "law_norm"] if t in meta.index else "NA"

        assets.append(
            AssetRow(
                ticker=t,
                pct=float(pct),
                usd=float(usd_amt),
                price=float(px),
                vn=float(vn),
                tir=float(y) if np.isfinite(y) else np.nan,
                venc=venc,
                ley=str(ley),
                issuer=str(issuer),
                px_ticker=str(px_ticker),
            )
        )

    if not assets:
        return pd.DataFrame(), {"tir": np.nan}, pd.DataFrame()

    # Resumen ponderado por USD asignado (SOLO TIR)
    wsum = float(np.sum([a.usd for a in assets])) or 1.0
    tir_total = float(np.nansum([a.tir * a.usd for a in assets]) / wsum)
    resumen = {"tir": tir_total}

    df = pd.DataFrame(
        {
            "Ticker": [a.ticker for a in assets],
            "%": [a.pct for a in assets],
            "USD": [a.usd for a in assets],
            "Precio (USD, VN100)": [a.price for a in assets],
            "VN estimada": [a.vn for a in assets],
            "TIR (%)": [a.tir for a in assets],
            "Vencimiento": [a.venc for a in assets],
            "Ley": [law_cell_label(a.ley) for a in assets],
            "Issuer": [a.issuer for a in assets],
            "Ticker precio": [a.px_ticker for a in assets],
        }
    )

    # Flujos por mes + totales
    settlement = _settlement(plazo)
    flow_rows = []
    for a in assets:
        cf = cashflows.get(a.ticker)
        if cf is None or cf.empty:
            continue
        fut = _future_cashflows(cf, settlement)
        if fut.empty:
            continue

        factor = a.vn / 100.0 if np.isfinite(a.vn) else np.nan
        for _, r in fut.iterrows():
            flow_rows.append(
                {
                    "Ticker": a.ticker,
                    "Fecha": pd.to_datetime(r["date"]).date(),
                    "Monto": float(r["flujo_total"]) * float(factor),
                }
            )

    flows = pd.DataFrame(flow_rows)
    if flows.empty:
        flows_pivot = pd.DataFrame()
    else:
        flows["Mes"] = pd.to_datetime(flows["Fecha"]).dt.to_period("M").dt.to_timestamp()
        flows_pivot = (
            flows.pivot_table(index="Ticker", columns="Mes", values="Monto", aggfunc="sum", fill_value=0.0)
            .sort_index(axis=1)
        )
        flows_pivot["Total Ticker"] = flows_pivot.sum(axis=1)
        totals_row = pd.DataFrame([flows_pivot.sum(axis=0)], index=["Totales"])
        flows_pivot = pd.concat([flows_pivot, totals_row], axis=0)

    return df, resumen, flows_pivot


# =========================
# PDF helpers (AR formatting)
# =========================
def _to_float(x) -> float | None:
    try:
        v = float(x)
        if not np.isfinite(v):
            return None
        return v
    except Exception:
        return None


def fmt_money_pdf(x: float) -> str:
    """$ con miles AR (.) y sin decimales."""
    v = _to_float(x)
    if v is None:
        return ""
    return f"$ {v:,.0f}".replace(",", ".")


def fmt_ar_number(x: float, dec: int = 2) -> str:
    """
    Número AR:
      - miles con '.'
      - decimales con ','
    """
    v = _to_float(x)
    if v is None:
        return ""
    s = f"{v:,.{dec}f}"  # en_US
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def fmt_ar_pct(x: float, dec: int = 2) -> str:
    v = _to_float(x)
    if v is None:
        return ""
    return f"{fmt_ar_number(v, dec)}%"


def _format_cartera_for_pdf(df: pd.DataFrame) -> pd.DataFrame:
    """Tabla lista para PDF (headers cortos + AR)."""
    d = df.copy()

    # headers cortos
    d = d.rename(
        columns={
            "Precio (USD, VN100)": "Precio",
            "VN estimada": "VN",
            "TIR (%)": "TIR",
        }
    )

    # ✅ asegurar que NO aparezcan Duration ni MD
    d = d.drop(columns=["Duration", "MD"], errors="ignore")

    # formateos
    if "USD" in d.columns:
        d["USD"] = d["USD"].apply(fmt_money_pdf)

    if "Precio" in d.columns:
        d["Precio"] = pd.to_numeric(d["Precio"], errors="coerce").apply(lambda v: fmt_ar_number(v, 2))

    if "VN" in d.columns:
        d["VN"] = pd.to_numeric(d["VN"], errors="coerce").apply(lambda v: fmt_ar_number(v, 0))

    if "TIR" in d.columns:
        d["TIR"] = pd.to_numeric(d["TIR"], errors="coerce").apply(lambda v: fmt_ar_pct(v, 2))

    if "Vencimiento" in d.columns:
        d["Vencimiento"] = pd.to_datetime(d["Vencimiento"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")

    if "%" in d.columns:
        d["%"] = pd.to_numeric(d["%"], errors="coerce").apply(lambda v: fmt_ar_number(v, 2))

    # Ley: “Ley local / Ley NY / Sin ley”
    if "Ley" in d.columns:
        d["Ley"] = d["Ley"].astype(str).str.strip()
        d["Ley"] = d["Ley"].replace(
            {
                "ARG (Ley local)": "Ley local",
                "NY (Ley NY)": "Ley NY",
                "Sin ley": "Sin ley",
                "ARG": "Ley local",
                "NY": "Ley NY",
                "NA": "Sin ley",
            }
        )
        d["Ley"] = d["Ley"].str.replace("ARG", "Ley local", regex=False)
        d["Ley"] = d["Ley"].str.replace("NY", "Ley NY", regex=False)
        d["Ley"] = d["Ley"].str.replace("(Ley local)", "Ley local", regex=False)

    return d.fillna("")


def _format_flows_for_pdf(df: pd.DataFrame) -> pd.DataFrame:
    """Flujos: $ AR sin decimales."""
    d = df.copy()

    if d.index.name is not None or not isinstance(d.index, pd.RangeIndex):
        d = d.reset_index().rename(columns={"index": "Ticker"})

    for c in d.columns:
        if c == "Ticker":
            continue
        d[c] = pd.to_numeric(d[c], errors="coerce").apply(fmt_money_pdf)

    return d.fillna("")


def _df_to_table_data(df: pd.DataFrame, max_rows: int = 60) -> list[list[str]]:
    if df is None or df.empty:
        return [["(sin datos)"]]
    d = df.copy().head(max_rows).fillna("")
    cols = list(d.columns)
    data = [cols]
    for _, r in d.iterrows():
        data.append([str(r[c]) for c in cols])
    return data


def _colwidths_by_name(cols: list[str], usable_w: float) -> list[float]:
    """Anchos inteligentes para que no quede apretado."""
    weights = []
    for c in cols:
        c = str(c)

        if c == "Ticker":
            weights.append(1.15)
        elif c == "%":
            weights.append(0.70)
        elif c == "USD":
            weights.append(1.05)
        elif c == "Precio":
            weights.append(0.95)
        elif c == "VN":
            weights.append(0.90)
        elif c == "TIR":
            weights.append(0.90)
        elif "Venc" in c:
            weights.append(1.05)
        elif c == "Ley":
            weights.append(0.95)
        elif c == "Issuer":
            weights.append(1.00)
        else:
            weights.append(0.95)

    s = sum(weights) or 1.0
    return [usable_w * (w / s) for w in weights]


def build_cartera_pdf_bytes(
    *,
    capital_usd: float,
    resumen: dict,
    cartera_show: pd.DataFrame,
    flows_show: pd.DataFrame,
    logo_path: str | None = None,
) -> bytes:
    """
    PDF minimal/pro:
    - Logo
    - KPIs: Capital + TIR (NO Duration / NO MD)
    - Tabla cartera sin Duration / sin MD
    """
    buff = io.BytesIO()

    left = right = 1.3 * cm
    top = bottom = 1.2 * cm
    page_w, _page_h = A4
    usable_w = page_w - left - right

    doc = SimpleDocTemplate(
        buff,
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
    )

    styles = getSampleStyleSheet()
    story = []

    # Logo centrado
    if logo_path and os.path.exists(logo_path):
        try:
            logo = RLImage(logo_path, width=6.2 * cm, height=1.6 * cm)
            tlogo = Table([[logo]], colWidths=[usable_w])
            tlogo.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(tlogo)
            story.append(Spacer(1, 8))
        except Exception:
            pass

    # KPI (sin Duration / sin MD)
    kpi_data = [
        ["Capital (USD)", fmt_money_pdf(float(capital_usd))],
        ["TIR total (pond.)", fmt_ar_pct(float(resumen.get("tir", np.nan)), 2)],
    ]

    t_kpi = Table(kpi_data, colWidths=[usable_w * 0.42, usable_w * 0.58])
    t_kpi.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.lightgrey),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_kpi)
    story.append(Spacer(1, 18))

    # Detalle de cartera
    story.append(Paragraph("Detalle de cartera", styles["Heading2"]))

    cpdf = _format_cartera_for_pdf(cartera_show)
    cartera_data = _df_to_table_data(cpdf, max_rows=60)

    cols1 = cartera_data[0]
    col_w1 = _colwidths_by_name(cols1, usable_w)
    t1 = Table(cartera_data, repeatRows=1, colWidths=col_w1)
    t1.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.6),
                ("FONTSIZE", (0, 1), (-1, -1), 8.2),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 1), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
            ]
        )
    )
    story.append(t1)
    story.append(Spacer(1, 18))

    # Flujos
    story.append(Paragraph("Flujo de fondos", styles["Heading2"]))

    if flows_show is None or flows_show.empty:
        story.append(Paragraph("(sin flujos futuros)", styles["Normal"]))
    else:
        fpdf = _format_flows_for_pdf(flows_show)
        flows_data = _df_to_table_data(fpdf, max_rows=80)

        cols2 = flows_data[0]
        col_w2 = _colwidths_by_name(cols2, usable_w)
        t2 = Table(flows_data, repeatRows=1, colWidths=col_w2)
        t2.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8.6),
                    ("FONTSIZE", (0, 1), (-1, -1), 8.2),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, 0), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                    ("TOPPADDING", (0, 1), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
                ]
            )
        )
        story.append(t2)

    doc.build(story)
    pdf = buff.getvalue()
    buff.close()
    return pdf


# =========================
# Excel export
# =========================
def build_excel_bytes(
    *,
    cartera_df: pd.DataFrame,
    flows_df: pd.DataFrame,
    resumen: dict,
    capital_usd: float,
) -> bytes:
    """
    Exporta un .xlsx con:
      - Resumen
      - Cartera
      - Flujos
    Sin Duration / sin MD.
    """
    buff = io.BytesIO()

    # Limpiar: no incluir Duration / MD aunque existan por algún motivo
    cartera_x = cartera_df.copy()
    cartera_x = cartera_x.drop(columns=["Duration", "MD"], errors="ignore")

    flows_x = flows_df.copy() if flows_df is not None else pd.DataFrame()

    resumen_df = pd.DataFrame(
        {
            "Métrica": ["Capital (USD)", "TIR total (pond.)"],
            "Valor": [float(capital_usd), float(resumen.get("tir", np.nan))],
        }
    )

    with pd.ExcelWriter(buff, engine="openpyxl") as writer:
        resumen_df.to_excel(writer, index=False, sheet_name="Resumen")
        cartera_x.to_excel(writer, index=False, sheet_name="Cartera")
        if flows_x is None or flows_x.empty:
            pd.DataFrame({"info": ["(sin flujos futuros)"]}).to_excel(writer, index=False, sheet_name="Flujos")
        else:
            flows_x.to_excel(writer, sheet_name="Flujos")

    return buff.getvalue()


# =========================
# UI
# =========================
def _ui_css():
    st.markdown(
        """
<style>
  .wrap{ max-width: 1180px; margin: 0 auto; }
  .block-container { padding-top: 1.1rem; padding-bottom: 1.8rem; }

  .title{ font-size: 28px; font-weight: 850; letter-spacing: .02em; color:#111827; margin: 0; }
  .sub{ color: rgba(17,24,39,.62); font-size: 13px; margin-top: 4px; }
  .soft-hr{ height:1px; background:rgba(17,24,39,.10); margin: 14px 0 18px; }

  div[data-testid="stDataFrame"] {
    border-radius: 14px;
    overflow: hidden;
    border: 1px solid rgba(17,24,39,.10);
  }

  .kpi{
    border: 1px solid rgba(17,24,39,.10);
    border-radius: 16px;
    padding: 12px 14px;
    background: white;
  }
  .kpi .lbl{ color: rgba(17,24,39,.60); font-size: 12px; margin-bottom: 6px; }
  .kpi .val{ font-size: 26px; font-weight: 850; color:#111827; letter-spacing: .01em; }
</style>
""",
        unsafe_allow_html=True,
    )


def _height_for_rows(n: int, row_h: int = 34, header: int = 42, pad: int = 18, max_h: int = 900) -> int:
    n = int(max(0, n))
    h = header + pad + row_h * max(1, n + 1)
    return int(min(max_h, h))


def _spacer(px: int = 14):
    st.markdown(f'<div style="height:{int(px)}px"></div>', unsafe_allow_html=True)


def render(back_to_home=None):
    _ui_css()
    st.markdown('<div class="wrap">', unsafe_allow_html=True)

    # Header
    left, right = st.columns([0.72, 0.28], vertical_alignment="center")
    with left:
        st.markdown('<div class="title">NEIX · Cartera Comercial</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub">Arma tu cartera con precios online.</div>', unsafe_allow_html=True)
    with right:
        refresh = st.button("Actualizar precios", use_container_width=True, key="cartera_refresh")

    st.markdown('<div class="soft-hr"></div>', unsafe_allow_html=True)
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    # Load cashflows
    try:
        df_cf = load_cashflows(CASHFLOW_PATH)
    except Exception as e:
        st.error(str(e))
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Precios (cache)
    if refresh or "cartera_prices" not in st.session_state:
        with st.spinner("Actualizando precios..."):
            try:
                st.session_state["cartera_prices"] = fetch_market_prices()
            except Exception as e:
                st.error(str(e))
                st.markdown("</div>", unsafe_allow_html=True)
                return

    prices = st.session_state.get("cartera_prices")
    if prices is None or prices.empty:
        st.warning("No pude cargar precios de mercado (tabla vacía o cambió el formato).")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    universe = build_eligible_universe(df_cf, prices, plazo=1)
    if universe.empty:
        st.warning("No hay activos elegibles con TIR dentro del rango y precio disponible.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Selección
    st.markdown("### Selección de activos")
    opts = universe["Ticker"].tolist()

    selected = st.multiselect(
        "Activos (bonos + ONs)",
        options=opts,
        default=opts[:6] if len(opts) >= 6 else opts,
        key="cartera_selected",
    )

    _spacer(10)

    c1, c2 = st.columns([0.42, 0.58], vertical_alignment="bottom")
    with c1:
        capital = st.number_input(
            "Capital (USD)",
            min_value=0.0,
            value=100000.0,
            step=1000.0,
            format="%.0f",
            key="cartera_capital",
        )
    with c2:
        calc = st.button("Calcular cartera", type="primary", use_container_width=True, key="cartera_calc")

    _spacer(6)

    # Asignación
    st.markdown("### Asignación por activo")
    st.caption("Editá la columna %. Ideal: que sume 100% (si no, escala automáticamente).")

    if not selected:
        st.info("Seleccioná al menos un activo.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    default_pct = round(100.0 / len(selected), 2) if selected else 0.0
    df_pct = pd.DataFrame({"Ticker": selected, "%": [default_pct] * len(selected)})

    edited = st.data_editor(
        df_pct,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", disabled=True),
            "%": st.column_config.NumberColumn("%", min_value=0.0, max_value=100.0, step=0.5, format="%.2f"),
        },
        key="cartera_pct_editor",
    )

    pct_map = {r["Ticker"]: float(r["%"]) for _, r in edited.iterrows()}

    _spacer(10)
    st.markdown('<div class="soft-hr"></div>', unsafe_allow_html=True)
    _spacer(6)

    if not calc:
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Calcular cartera
    cartera_df, resumen, flows_pivot = build_portfolio_table(
        df_cf=df_cf,
        prices=prices,
        selected=selected,
        pct_map=pct_map,
        capital_usd=float(capital),
        plazo=1,
    )

    if cartera_df.empty:
        st.warning("No pude armar cartera con la selección actual (faltan precios o flujos).")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ✅ asegurar que NO aparezcan Duration ni MD por ningún lado
    cartera_df = cartera_df.drop(columns=["Duration", "MD"], errors="ignore")

    # KPIs (solo Capital + TIR)
    st.markdown("### Resumen")
    k1, k2 = st.columns(2)
    with k1:
        st.markdown(
            f"""
<div class="kpi">
  <div class="lbl">Capital (USD)</div>
  <div class="val">{fmt_money_int(float(capital))}</div>
</div>
""",
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            f"""
<div class="kpi">
  <div class="lbl">TIR total (pond.)</div>
  <div class="val">{fmt_pct_2(float(resumen["tir"]))}</div>
</div>
""",
            unsafe_allow_html=True,
        )

    _spacer(14)

    # Tabla cartera (UI)
    show = cartera_df.copy()
    show["%"] = pd.to_numeric(show["%"], errors="coerce").round(2)
    show["USD"] = pd.to_numeric(show["USD"], errors="coerce").round(0)
    show["Precio (USD, VN100)"] = pd.to_numeric(show["Precio (USD, VN100)"], errors="coerce").round(2)
    show["VN estimada"] = pd.to_numeric(show["VN estimada"], errors="coerce").round(0)
    show["TIR (%)"] = pd.to_numeric(show["TIR (%)"], errors="coerce").round(2)
    show["Vencimiento"] = pd.to_datetime(show["Vencimiento"], errors="coerce").dt.date

    # ✅ por si quedó algo
    show = show.drop(columns=["Duration", "MD"], errors="ignore")

    h_tbl = _height_for_rows(len(show), row_h=34, header=42, pad=12, max_h=780)

    st.dataframe(
        show.drop(columns=["Ticker precio"], errors="ignore"),
        hide_index=True,
        use_container_width=True,
        height=h_tbl,
        column_config={
            "%": st.column_config.NumberColumn("%", format="%.2f"),
            "USD": st.column_config.NumberColumn("USD", format="$ %.0f"),
            "Precio (USD, VN100)": st.column_config.NumberColumn("Precio (USD, VN100)", format="%.2f"),
            "VN estimada": st.column_config.NumberColumn("VN estimada", format="%.0f"),
            "TIR (%)": st.column_config.NumberColumn("TIR (%)", format="%.2f"),
            "Vencimiento": st.column_config.DateColumn("Vencimiento", format="DD/MM/YYYY"),
        },
    )

    _spacer(18)

    # Flujos
    st.markdown("### Flujo de fondos")

    if flows_pivot is None or flows_pivot.empty:
        st.info("No hay flujos futuros para mostrar.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    flows = flows_pivot.copy()

    new_cols = []
    for c in flows.columns:
        if isinstance(c, (pd.Timestamp, dt.datetime)):
            new_cols.append(pd.to_datetime(c).strftime("%b-%Y").capitalize())
        else:
            new_cols.append(str(c))
    flows.columns = new_cols

    flows = flows.round(0)
    h_flows = _height_for_rows(len(flows), row_h=34, header=42, pad=12, max_h=820)

    st.dataframe(
        flows,
        use_container_width=True,
        height=h_flows,
        column_config={col: st.column_config.NumberColumn(col, format="$ %.0f") for col in flows.columns},
    )

    _spacer(14)

    # =========================
    # Export: PDF o Excel (opción)
    # =========================
    st.markdown("### Exportar")
    export_fmt = st.radio(
        "Formato",
        options=["PDF", "Excel"],
        horizontal=True,
        key="cartera_export_fmt",
    )

    # Armamos versiones limpias para export
    export_cartera = show.drop(columns=["Ticker precio"], errors="ignore").copy()
    export_cartera = export_cartera.drop(columns=["Duration", "MD"], errors="ignore")

    if export_fmt == "PDF":
        try:
            pdf_bytes = build_cartera_pdf_bytes(
                capital_usd=float(capital),
                resumen=resumen,
                cartera_show=export_cartera,
                flows_show=flows,
                logo_path=LOGO_PATH,
            )
            fname = f"NEIX_Cartera_Comercial_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.pdf"

            st.download_button(
                "Descargar PDF",
                data=pdf_bytes,
                file_name=fname,
                mime="application/pdf",
                use_container_width=True,
                key="cartera_pdf",
            )
        except Exception as e:
            st.warning(f"No pude generar el PDF: {e}")

    else:  # Excel
        try:
            xlsx_bytes = build_excel_bytes(
                cartera_df=export_cartera,
                flows_df=flows,
                resumen=resumen,
                capital_usd=float(capital),
            )
            fname = f"NEIX_Cartera_Comercial_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

            st.download_button(
                "Descargar Excel",
                data=xlsx_bytes,
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="cartera_xlsx",
            )
        except Exception as e:
            st.warning(f"No pude generar el Excel: {e}")

    st.markdown("</div>", unsafe_allow_html=True)
