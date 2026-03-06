import streamlit as st
from openai import OpenAI


def render():
    st.header("Asistente NEIX IA")

    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        st.error("Falta configurar OPENAI_API_KEY en los secrets de Streamlit.")
        return

    client = OpenAI(api_key=api_key)

    pregunta = st.text_input("Hacé una pregunta sobre la cartera", key="ia_input")

    if pregunta:
        with st.spinner("Analizando..."):
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Sos un analista financiero experto en carteras propias de una ALyC."
                    },
                    {
                        "role": "user",
                        "content": pregunta
                    }
                ]
            )

        st.write(response.choices[0].message.content)
