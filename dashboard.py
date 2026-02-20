import streamlit as st
from core.models import engine, Base

# Configuration de la page
st.set_page_config(
    page_title="STAFF VISION - Dashboard pro",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Application du style sombre et compact (via CSS personnalisé)
st.markdown("""
<style>
    [data-testid="stSidebar"] {
        background-color: #0e1117;
    }
    .stDataFrame {
        font-size: 12px;
    }
    .stBadge {
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

def init_db():
    Base.metadata.create_all(bind=engine)

def main():
    init_db()
    st.title("🛡️ STAFF VISION : Orchestrateur Arbitrage")
    st.sidebar.success("Système prêt.")
    
    st.markdown("""
    ### Bienvenue sur votre centre de commandement STAFF.
    Utilisez le menu à gauche pour :
    - **Sources & Scheduler** : Gérer vos points d'entrée et lancer des scans.
    - **Catalogues / Coupons / ODR** : Nettoyer et valider vos données brutes.
    - **Explorateur** : Rechercher des opportunités de Stacking.
    """)
    
    st.info("Sélectionnez une page dans la barre latérale pour commencer.")

if __name__ == "__main__":
    main()
