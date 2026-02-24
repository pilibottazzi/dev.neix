from __future__ import annotations

import json
from datetime import datetime

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
st.write("Secrets keys:", list(st.secrets.keys()))
# =========================
# CONFIG
# =========================
SPREADSHEET_ID = "1or-OBykeL0gb44V26ZJqszi027hLJWAPffKqCeVathc"
SHEET_MARKETING = "Marketing"

CATEGORIAS = [
    "Eventos",
    "Merchandising y regalos",
    "Medios/Prensa",
    "Cartel edificio",
    "Sponsorship Santi",
    "Audiovisual",
    "Fee RRSS",
    "Loyalty",
    "Web",
    "Eventos internos",
    "Eventos industria",
    "Research + plan",
    "Curaduría branding",
]

# =========================
# Helpers
# =========================
def _ar_to_float_or_none(x: str):
    if x is None:
        return None
    s = str(x).strip()
    if s == "":
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _get_creds_info():
    """
    Soporta:
    - st.secrets["gcp_service_account"] como dict (TOML section)
    - st.secrets["gcp_service_account"] como string JSON (triple quotes)
    """
    raw = st.secrets.get("gcp_service_account")
    if raw is None:
        raise RuntimeError("Falta st.secrets['gcp_service_account']")

    if isinstance(raw, str):
        return json.loads(raw)

    if isinstance(raw, dict):
        return raw

    raise RuntimeError("Formato inválido en st.secrets['gcp_service_account']")


def _gs_client():
    creds_info = _get_creds_info()
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    return gspread.authorize(creds)


def _ensure_worksheet(sh, name: str, headers: list[str]):
    try:
        ws = sh.worksheet(name)
    except Exception:
        ws = sh.add_worksheet(title=name, rows=2000, cols=max(10, len(headers)))

    existing = ws.get_all_values()
    if not existing:
        ws.append_row(headers, value_input_option="USER_ENTERED")
    return ws


def _append_marketing_row(ts: str, categoria: str, monto_ars: float, monto_usd, observacion: str):
    gc = _gs_client()
    sh = gc.open_by_key(SPREADSHEET_ID)

    headers = ["timestamp", "categoria", "monto_ars", "monto_usd", "observacion"]
    ws = _ensure_worksheet(sh, SHEET_MARKETING, headers)

    ws.append_row(
        [ts, categoria, monto_ars, "" if monto_usd is None else monto_usd, observacion],
        value_input_option="USER_ENTERED",
    )


# =========================
# TOOL ENTRYPOINT
# =========================
def render(_=None):
    st.markdown("<div class='section-title'>Marketing</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-sub'>Cargar gasto (año y tipo se completan al bajar a Excel)</div>",
        unsafe_allow_html=True,
    )

    with st.form("marketing_form", clear_on_submit=True):
        categoria = st.selectbox("categoría *", CATEGORIAS)
        monto_ars_raw = st.text_input("monto_ars *", placeholder="Ej: 1200000,50")
        monto_usd_raw = st.text_input("monto_usd", placeholder="Ej: 350,75 (opcional)")
        observacion = st.text_area("observacion *", placeholder="Detalle / comentario", height=120)
        submitted = st.form_submit_button("Enviar")

    if submitted:
        errores = []
        if not categoria:
            errores.append("Completar **categoría**.")
        if not monto_ars_raw.strip():
            errores.append("Completar **monto_ars**.")
        if not observacion.strip():
            errores.append("Completar **observacion**.")

        monto_ars = _ar_to_float_or_none(monto_ars_raw)
        if monto_ars is None:
            errores.append("**monto_ars** inválido (ej: 1200000,50).")

        monto_usd = _ar_to_float_or_none(monto_usd_raw) if monto_usd_raw.strip() else None
        if monto_usd_raw.strip() and monto_usd is None:
            errores.append("**monto_usd** inválido (ej: 350,75).")

        if errores:
            for e in errores:
                st.error(e)
        else:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                _append_marketing_row(ts, categoria, monto_ars, monto_usd, observacion.strip())
                st.success("Enviado ✅ (guardado en Google Sheets)")
            except Exception as ex:
                st.error("No pude guardar en Google Sheets. Revisá permisos del Sheet y Secrets.")
                st.exception(ex)
