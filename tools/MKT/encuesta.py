import streamlit as st
import streamlit.components.v1 as components

FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSemUHA9xQP8iMkeBf-DkNl8QKJ_2gqToDzXd9k72VYhbe0IDw/viewform?usp=sharing&ouid=111449706457807508532"

def _to_embed(url: str) -> str:
    # Google Forms embed: reemplazar /viewform por /viewform?embedded=true
    if "embedded=true" in url:
        return url
    if "viewform" in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}embedded=true"
    return url

def render(_=None):
    st.markdown("<div class='section-title'>Marketing</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-sub'>Cargar gasto desde el formulario (queda registrado automáticamente en Google Sheets)</div>",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        st.link_button("Abrir formulario en una pestaña nueva", FORM_URL)
    with c2:
        st.caption("Si no se ve el embed, usá el botón de abrir arriba.")

    st.divider()

    # Embed
    embed_url = _to_embed(FORM_URL)
    components.iframe(embed_url, height=980, scrolling=True)
