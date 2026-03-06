import streamlit as st
import anthropic


def render():
    st.markdown("<div class='section-title'>Asistente IA Comercial</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-sub'>Consulta libre sobre cartera, movimientos y análisis comercial</div>",
        unsafe_allow_html=True
    )

    api_key = st.secrets.get("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("Falta configurar ANTHROPIC_API_KEY en los secrets de Streamlit.")
        return

    client = anthropic.Anthropic(api_key=api_key)

    pregunta = st.text_area(
        "Escribí tu consulta",
        placeholder="Ej: resumime los movimientos más frecuentes o explicame las principales variaciones.",
        height=120,
        key="claude_input"
    )

    if st.button("Consultar IA", key="claude_btn"):
        if not pregunta.strip():
            st.warning("Escribí una consulta primero.")
            return

        try:
            with st.spinner("Analizando..."):
                response = client.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=800,
                    system="Sos un analista financiero experto en una ALyC argentina. Respondés de forma clara, profesional y útil para análisis comercial y de cartera.",
                    messages=[
                        {"role": "user", "content": pregunta}
                    ]
                )

            st.markdown("### Respuesta")
            st.write(response.content[0].text)

        except Exception as e:
            st.error("Error al consultar Claude.")
            st.exception(e)
