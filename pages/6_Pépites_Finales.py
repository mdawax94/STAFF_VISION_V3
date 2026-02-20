import streamlit as st
import pandas as pd
from core.models import SessionLocal, PepiteFinale

st.set_page_config(page_title="Pépites Finales", layout="wide")

st.title("🏆 Hall of Fame : Pépites Finales")

session = SessionLocal()
pepites = session.query(PepiteFinale).order_by(PepiteFinale.timestamp.desc()).all()

if pepites:
    data = [{
        "ID": p.id,
        "Produit": p.produit_name,
        "Marge Net (€)": p.marge_nette,
        "Score Fiabilité": p.reliability_score,
        "Date Détection": p.timestamp.strftime("%Y-%m-%d %H:%M")
    } for p in pepites]
    
    df = pd.DataFrame(data)
    
    # Style conditionnel pour les pépites
    def color_pepite(val):
        if val > 20: return "color: #2e7d32; font-weight: bold;"
        return ""

    st.dataframe(df.style.applymap(color_pepite, subset=["Marge Net (€)"]), use_container_width=True)
else:
    st.info("Aucune pépite validée pour le moment. Allez dans les pages Leviers pour approuver des produits !")

session.close()
