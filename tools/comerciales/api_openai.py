import streamlit as st

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def render():
    st.markdown("<div class='section-title'>Asistente IA Comercial</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-sub'>Consulta libre sobre cartera, movimientos y análisis comercial</div>",
        unsafe_allow_html=True
    )

    if OpenAI is None:
        st.error("La librería 'openai' no está instalada. Agregala a requirements.txt y redeployá la app.")
        return

    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        st.error("Falta configurar OPENAI_API_KEY en los secrets de Streamlit.")
        return

    client = OpenAI(api_key=api_key)

    pregunta = st.text_area(
        "Escribí tu consulta",
        placeholder="Ej: Resumime los movimientos más relevantes o explicame las principales variaciones de la cartera.",
        height=120,
        key="ia_comercial_input"
    )

    if st.button("Consultar IA", key="ia_comercial_btn"):
        if not pregunta.strip():
            st.warning("Escribí una consulta primero.")
            return

        try:
            with st.spinner("Analizando..."):
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Sos un analista financiero experto en una ALyC argentina. "
                                "Respondés de forma clara, profesional y útil para análisis comercial y de cartera."
                            )
                        },
                        {
                            "role": "user",
                            "content": pregunta
                        }
                    ]
                )

            st.markdown("### Respuesta")
            st.write(response.choices[0].message.content)

        except Exception as e:
            msg = str(e)

            if "insufficient_quota" in msg or "429" in msg:
                st.error(
                    "La API está conectada, pero esta clave/proyecto no tiene cuota disponible. "
                    "Revisá billing, saldo o límites del proyecto en OpenAI."
                )
            else:
                st.error("Ocurrió un error al consultar la API.")
                st.exception(e)
