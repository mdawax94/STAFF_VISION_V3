import streamlit as st

# Point d'entrée principal pour garantir la détection du dossier 'pages/'
st.set_page_config(page_title="STAFF v3", page_icon="🏢", layout="wide")

# Redirection automatique vers le Dashboard Macro
st.switch_page("pages/01_🏠_Dashboard.py")
