import streamlit as st

from tools.comerciales import (
    cauciones_mae,
    cauciones_byma,
    alquileres,
    cn,
    transactions_analyzer,
    api_openai,
)

# =========================
# CONFIG
# =========================
st.set_page_config(
    page_title="NEIX Workbench · DEV",
    page_icon="🧰",
    layout="wide"
)

# =========================
# ESTÉTICA
# =========================
st.markdown(
    """
    <style>
    /* ===== Contenedor general ===== */
    .block-container{
        padding-top: 2.2rem;
        max-width: 1240px;
    }

    header[data-testid="stHeader"]{
        visibility: hidden;
        height: 3rem;
    }

    /* ===== Header ===== */
    .neix-title{
        text-align:center;
        font-weight:900;
        letter-spacing:.14em;
        font-size:1.6rem;
        margin-bottom:4px;
    }

    .neix-caption{
        text-align:center;
        color:#6b7280;
        font-size:.95rem;
        margin-bottom:10px;
    }

    .neix-line{
        width:60px;
        height:3px;
        background:#ef4444;
        margin:0 auto 22px auto;
        border-radius:4px;
    }

    /* ===== Tabs ===== */
    .stTabs [data-baseweb="tab-list"]{
        justify-content:flex-start;
        gap:8px;
        border-bottom:1px solid rgba(0,0,0,0.08);
        padding-left:2px;
        margin-top:4px;
    }

    .stTabs [data-baseweb="tab"]{
        background:transparent;
        border:none;
        font-weight:700;
        color:#64748b;
        padding:10px 14px;
        font-size:.95rem;
    }

    .stTabs [data-baseweb="tab"]:hover{
        color:#1e3a8a;
    }

    .stTabs [aria-selected="true"]{
        color:#1e3a8a;
        border-bottom:3px solid #ef4444;
    }

    /* ===== Section Titles ===== */
    .section-title{
        font-size:1.35rem;
        font-weight:800;
        margin-top:6px;
        margin-bottom:2px;
        color:#111827;
    }

    .section-sub{
        color:#6b7280;
        font-size:.92rem;
        margin-bottom:14px;
    }

    /* ===== Cards ===== */
    .tool-grid{
        display:flex;
        gap:14px;
        flex-wrap:wrap;
        margin-top:6px;
    }

    .tool-btn{
        display:flex;
        align-items:center;
        justify-content:center;
        padding:12px 18px;
        min-height:52px;
        border-radius:14px;
        border:1px solid rgba(0,0,0,0.08);
        background:white;
        text-decoration:none !important;
        color:#1e3a8a !important;
        font-weight:700;
        min-width:240px;
        box-shadow:0 2px 10px rgba(0,0,0,0.04);
        transition: all .10s ease;
    }

    .tool-btn:hover{
        transform: translateY(-1px);
        box-shadow:0 8px 22px rgba(0,0,0,0.08);
        border-color: rgba(239,68,68,.35);
        color:#1e3a8a !important;
    }

    .tool-btn-primary{
        background:#ef4444 !important;
        color:white !important;
        border-color:transparent !important;
    }

    .tool-btn-primary:hover{
        filter:brightness(.96);
        box-shadow:0 10px 26px rgba(239,68,68,.18);
    }

    </style>
    """,
    unsafe_allow_html=True
)

def _header():
    st.markdown("<div class='neix-title'>N E I X &nbsp;&nbsp;Workbench · DEV</div>", unsafe_allow_html=True)
    st.markdown("<div class='neix-caption'>Entorno de pruebas · Comercial</div>", unsafe_allow_html=True)
    st.markdown("<div class='neix-line'></div>", unsafe_allow_html=True)
    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

# =========================
# ROUTER (?tool=...)
# =========================
tool = (st.query_params.get("tool") or "").lower().strip()

if tool:
    _header()

    try:
        if tool == "cauciones_mae":
            cauciones_mae.render(None)
            st.stop()

        elif tool == "cn":
            cn.render(None)
            st.stop()

        elif tool == "cauciones_byma":
            cauciones_byma.render(None)
            st.stop()

        elif tool == "alquileres":
            alquileres.render(None)
            st.stop()

        elif tool == "transactions_analyzer":
            transactions_analyzer.render()
            st.stop()

        elif tool == "asistente_ia":
            api_openai.render()
            st.stop()

        else:
            st.error("Herramienta no encontrada")
            st.stop()

    except Exception as e:
        st.error("Error cargando la herramienta.")
        st.exception(e)
        st.stop()

# =========================
# HOME
# =========================
_header()

tabs = st.tabs(["Comercial"])

# =========================
# COMERCIAL
# =========================
with tabs[0]:
    st.markdown("<div class='section-title'>Comercial</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-sub'>Entorno dev para seguimiento y herramientas comerciales</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="tool-grid">
            <a class="tool-btn" href="?tool=cauciones_mae">Cauciones MAE</a>
            <a class="tool-btn" href="?tool=cauciones_byma">Cauciones BYMA</a>
            <a class="tool-btn" href="?tool=alquileres">Alquileres</a>
            <a class="tool-btn" href="?tool=cn">CN</a>
            <a class="tool-btn" href="?tool=transactions_analyzer">Movimientos CV</a>
            <a class="tool-btn tool-btn-primary" href="?tool=asistente_ia">Asistente IA</a>
        </div>
        """,
        unsafe_allow_html=True
    )
