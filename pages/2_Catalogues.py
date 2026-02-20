import streamlit as st
from pages.levier_template import render_levier_page

st.set_page_config(page_title="Catalogues", layout="wide")
render_levier_page("Catalogues", "Catalogues")
