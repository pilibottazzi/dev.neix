import streamlit as st

try:
    from google import genai
except ImportError:
    genai = None


def render():
    st.markdown("<div class='section-title'>Asistente IA Comercial · Gemini</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-sub'>Consulta libre sobre cartera, movimientos y análisis comercial</div>",
        unsafe_allow_html=True
    )

    if genai is None:
        st.error("Falta instalar la librería google-genai en requirements.txt.")
        return

    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        st.error("Falta configurar GEMINI_API_KEY en los secrets de Streamlit.")
        return

    client = genai.Client(api_key=api_key)

    modelo = st.selectbox(
        "Modelo",
        [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ],
        index=0,
        key="gemini_model"
    )

    pregunta = st.text_area(
        "Escribí tu consulta",
        placeholder="Ej: resumime los movimientos más relevantes o explicame las principales variaciones de la cartera.",
        height=120,
        key="gemini_input"
    )

    if st.button("Consultar IA", key="gemini_btn"):
        if not pregunta.strip():
            st.warning("Escribí una consulta primero.")
            return

        prompt = f"""
Sos un analista financiero experto en una ALyC argentina.
Respondé de forma clara, profesional y útil para análisis comercial y de cartera.
No inventes datos.
Si falta contexto, decilo.
Consulta del usuario: {pregunta}
"""

        try:
            with st.spinner("Analizando con Gemini..."):
                response = client.models.generate_content(
                    model=modelo,
                    contents=prompt,
                )

            st.markdown("### Respuesta")
            st.write(response.text)

        except Exception as e:
            msg = str(e).lower()

            if "quota" in msg or "rate limit" in msg or "429" in msg:
                st.error("Se alcanzó el límite de uso de Gemini para esta cuenta/proyecto.")
            elif "api key" in msg or "permission" in msg or "403" in msg or "401" in msg:
                st.error("La API key de Gemini no es válida o no tiene permisos.")
            else:
                st.error("Ocurrió un error al consultar Gemini.")
                st.exception(e)
