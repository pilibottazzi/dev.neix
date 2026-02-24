import streamlit as st

from tools.mesa import cartera, ons, vencimientos, bonos, cartera2
from tools.comerciales import cauciones_mae, cauciones_byma, alquileres, cn

# ✅ Marketing (MKT) — preferible minúscula en cloud (case-sensitive)
try:
    from tools.mkt import encuesta  # si renombraste tools/mkt
except Exception:
    from tools.MKT import encuesta  # fallback si sigue como tools/MKT

BACKOFFICE_URL = "https://neix-workbench-bo.streamlit.app/"
BI_BANCA_PRIVADA = "https://lookerstudio.google.com/reporting/75c2a6d0-0086-491f-b112-88fe3d257ef9"
BI_BANCA_CORP = "https://lookerstudio.google.com/reporting/4f70efa8-2b86-4134-a9cb-9e6f90117f3b"
BI_MIDDLE = "https://lookerstudio.google.com/reporting/5b834e5f-aeef-4042-ac0f-e1ed3564a010"

# ✅ SharePoint Marketing (carpetas)
SP_MKT_INSTRUCTIVOS = "https://neixcom.sharepoint.com/sites/NEIXSOCIEDADDEBOLSAS.A-Marketingprueba/Shared%20Documents/Forms/AllItems.aspx?id=%2Fsites%2FNEIXSOCIEDADDEBOLSAS%2EA%2DMarketingprueba%2FShared%20Documents%2FMarketing%2FInstructivos&viewid=74e4d9a3%2Dd2c9%2D4f09%2D9bc8%2Deb59e613117f&p=true"
SP_MKT_MATERIALES = "https://neixcom.sharepoint.com/sites/NEIXSOCIEDADDEBOLSAS.A-Marketingprueba/Shared%20Documents/Forms/AllItems.aspx?id=%2Fsites%2FNEIXSOCIEDADDEBOLSAS%2EA%2DMarketingprueba%2FShared%20Documents%2FMarketing%2FMateriales%20de%20Marketing&viewid=74e4d9a3%2Dd2c9%2D4f09%2D9bc8%2Deb59e613117f&p=true"
SP_MKT_PRESENTACIONES = "https://neixcom.sharepoint.com/sites/NEIXSOCIEDADDEBOLSAS.A-Marketingprueba/Shared%20Documents/Forms/AllItems.aspx?id=%2Fsites%2FNEIXSOCIEDADDEBOLSAS%2EA%2DMarketingprueba%2FShared%20Documents%2FMarketing%2FPresentaciones&viewid=74e4d9a3%2Dd2c9%2D4f09%2D9bc8%2Deb59e613117f&p=true"


# =========================
# CONFIG
# =========================
st.set_page_config(
    page_title="NEIX Workbench",
    page_icon="🧰",
    layout="wide"
)


# =========================
# ESTÉTICA PREMIUM
# =========================
st.markdown(
    """
    <style>
    /* ===== Contenedor general ===== */
    .block-container{
        padding-top: 2.4rem;
        max-width: 1240px;
    }

    /* Oculta header nativo SIN romper layout */
    header[data-testid="stHeader"]{
        visibility: hidden;
        height: 3.25rem;
    }

    /* ===== Header ===== */
    .neix-title{
        text-align: center;
        font-weight: 900;
        letter-spacing: .12em;
        font-size: 1.55rem;
        margin-top: .2rem;
        margin-bottom: 4px;
    }
    .neix-caption{
        text-align: center;
        color:#6b7280;
        font-size:.95rem;
        margin-bottom: 18px;
    }

    /* ===== Tabs arriba (alineadas a la izquierda) ===== */
    .stTabs [data-baseweb="tab-list"]{
        justify-content: flex-start;
        gap: 6px;
        border-bottom: 1px solid rgba(0,0,0,0.08);
        padding-left: 2px;
        margin-top: 6px;
    }

    .stTabs [data-baseweb="tab"]{
        background: transparent;
        border: none;
        font-weight: 700;
        color: #6b7280;
        padding: 10px 14px;
        font-size: .95rem;
    }

    .stTabs [data-baseweb="tab"]:hover{
        color:#111827;
        background: transparent;
    }

    .stTabs [aria-selected="true"]{
        color:#111827;
        border-bottom: 3px solid #ef4444; /* rojo NEIX */
    }

    /* ===== Secciones ===== */
    .section-title{
        font-size:1.35rem;
        font-weight:800;
        margin-top: 6px;
        margin-bottom: 2px;
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
        padding:14px 18px;
        border-radius:14px;
        border:1px solid rgba(0,0,0,0.08);
        background:white;
        text-decoration:none !important;
        font-weight:700;
        color:#0f172a;
        min-width:240px;
        box-shadow:0 2px 10px rgba(0,0,0,0.04);
        transition: all .08s ease;
    }

    .tool-btn:hover{
        transform: translateY(-1px);
        box-shadow:0 8px 22px rgba(0,0,0,0.08);
        border-color: rgba(239,68,68,.35);
    }

    /* Botón destacado rojo (link externo Backoffice) */
    .tool-btn-primary{
        background:#ef4444 !important;
        color:white !important;
        border-color: rgba(0,0,0,0) !important;
    }
    .tool-btn-primary:hover{
        filter: brightness(.96);
        box-shadow:0 10px 26px rgba(239,68,68,.18);
    }
    </style>
    """,
    unsafe_allow_html=True
)


def _header():
    st.markdown("<div class='neix-title'>N E I X &nbsp;&nbsp;Workbench</div>", unsafe_allow_html=True)
    st.markdown("<div class='neix-caption'>Navegación por áreas y proyectos</div>", unsafe_allow_html=True)
    st.divider()


# =========================
# ROUTER (?tool=...)
# =========================
tool = (st.query_params.get("tool") or "").lower().strip()

if tool:
    _header()

    try:
        # -------------------------
        # Mesa
        # -------------------------
        if tool == "bonos":
            bonos.render(None)
            st.stop()
        elif tool == "ons":
            ons.render(None)
            st.stop()
        elif tool == "cartera":
            cartera.render(None)
            st.stop()
        elif tool == "cartera2":
            cartera2.render(None)
            st.stop()
        elif tool in ("tenencia", "tenencias", "vencimientos"):
            vencimientos.render(None)
            st.stop()

        # -------------------------
        # Comercial
        # -------------------------
        elif tool == "cauciones_mae":
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

        # -------------------------
        # Marketing (Encuesta embebida)
        # -------------------------
        elif tool in ("encuesta", "mkt", "marketing", "mkt_encuesta"):
            encuesta.render(None)
            st.stop()

        # -------------------------
        # Marketing (links a SharePoint)
        # -------------------------
        elif tool == "mkt_instructivos":
            st.markdown("<div class='section-title'>Marketing · Instructivos</div>", unsafe_allow_html=True)
            st.markdown("<div class='section-sub'>Carpeta compartida (SharePoint)</div>", unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="tool-grid">
                  <a class="tool-btn" href="{SP_MKT_INSTRUCTIVOS}" target="_blank" rel="noopener noreferrer">
                    Abrir Instructivos
                  </a>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.stop()

        elif tool == "mkt_materiales":
            st.markdown("<div class='section-title'>Marketing · Materiales</div>", unsafe_allow_html=True)
            st.markdown("<div class='section-sub'>Carpeta compartida (SharePoint)</div>", unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="tool-grid">
                  <a class="tool-btn" href="{SP_MKT_MATERIALES}" target="_blank" rel="noopener noreferrer">
                    Abrir Materiales de Marketing
                  </a>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.stop()

        elif tool == "mkt_presentaciones":
            st.markdown("<div class='section-title'>Marketing · Presentaciones</div>", unsafe_allow_html=True)
            st.markdown("<div class='section-sub'>Carpeta compartida (SharePoint)</div>", unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="tool-grid">
                  <a class="tool-btn" href="{SP_MKT_PRESENTACIONES}" target="_blank" rel="noopener noreferrer">
                    Abrir Presentaciones
                  </a>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.stop()

        # -------------------------
        # Operaciones -> solo link externo
        # -------------------------
        elif tool in ("operaciones", "backoffice"):
            st.markdown(
                f"""
                <div class="section-title">Operaciones</div>
                <div class="section-sub">Backoffice se abre en web externa (para evitar saturación del Workbench)</div>
                <div class="tool-grid">
                  <a class="tool-btn tool-btn-primary" href="{BACKOFFICE_URL}" target="_blank" rel="noopener noreferrer">
                    Abrir Backoffice
                  </a>
                </div>
                """,
                unsafe_allow_html=True,
            )
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

tabs = st.tabs(["Mesa", "Comercial", "Operaciones", "Performance · BI", "Marketing"])

# MESA
with tabs[0]:
    st.markdown("<div class='section-title'>Mesa</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-sub'>Bonos, ONs y carteras</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="tool-grid">
          <a class="tool-btn" href="?tool=bonos">Bonos</a>
          <a class="tool-btn" href="?tool=ons">Obligaciones Negociables</a>
          <a class="tool-btn" href="?tool=cartera">Carteras (rendimiento)</a>
          <a class="tool-btn" href="?tool=cartera2">Carteras (ARG)</a>
        </div>
        """,
        unsafe_allow_html=True
    )

# COMERCIAL
with tabs[1]:
    st.markdown("<div class='section-title'>Comercial</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-sub'>Seguimiento y herramientas comerciales</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="tool-grid">
          <a class="tool-btn" href="?tool=cauciones_mae">Cauciones MAE</a>
          <a class="tool-btn" href="?tool=cauciones_byma">Cauciones BYMA</a>
          <a class="tool-btn" href="?tool=alquileres">Alquileres</a>
          <a class="tool-btn" href="?tool=tenencia">Tenencia</a>
          <a class="tool-btn" href="?tool=cn">CN</a>
        </div>
        """,
        unsafe_allow_html=True
    )

# OPERACIONES (solo link externo)
with tabs[2]:
    st.markdown("<div class='section-title'>Operaciones</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-sub'>Se abre en web externa</div>", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="tool-grid">
          <a class="tool-btn tool-btn-primary" href="{BACKOFFICE_URL}" target="_blank" rel="noopener noreferrer">
            Abrir Backoffice
          </a>
        </div>
        """,
        unsafe_allow_html=True
    )

# PERFORMANCE / BI
with tabs[3]:
    st.markdown("<div class='section-title'>Performance · BI</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-sub'>Dashboards de performance y seguimiento por área</div>",
        unsafe_allow_html=True
    )

    st.markdown(
        f"""
        <div class="tool-grid">
          <a class="tool-btn" href="{BI_BANCA_PRIVADA}" target="_blank" rel="noopener noreferrer">
            Banca Privada
          </a>
          <a class="tool-btn" href="{BI_BANCA_CORP}" target="_blank" rel="noopener noreferrer">
            Banca Corporativa
          </a>
          <a class="tool-btn" href="{BI_MIDDLE}" target="_blank" rel="noopener noreferrer">
            Middle Office
          </a>
        </div>
        """,
        unsafe_allow_html=True
    )

# MARKETING
with tabs[4]:
    st.markdown("<div class='section-title'>Marketing</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-sub'>Encuestas y carpetas compartidas</div>", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="tool-grid">
          <a class="tool-btn" href="?tool=encuesta">Encuesta</a>
          <a class="tool-btn" href="?tool=mkt_instructivos" target="_self">Instructivos</a>
          <a class="tool-btn" href="?tool=mkt_materiales" target="_self">Materiales de Marketing</a>
          <a class="tool-btn" href="?tool=mkt_presentaciones" target="_self">Presentaciones</a>
        </div>
        """,
        unsafe_allow_html=True
    )
