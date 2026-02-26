"""
PAGE 4 — L'Arène des Acheteurs B2B (Phase 5 LineCharts)
Visualisation des pépites avec historique des prix de revente.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from datetime import datetime

from core.models import SessionLocal, OffreRetail, ProduitReference, PriceHistory

st.set_page_config(page_title="Market Export", page_icon="📈", layout="wide")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


st.title("📈 Market Export & Analytics")
st.markdown("Vos opportunités certifiées B2B avec graphiques temporels de revente.")

db = next(get_db())

# On cherche uniquement le flux "Validated" de la Phase 1
offres = db.query(OffreRetail).filter(OffreRetail.qa_status == "VALIDATED").order_by(OffreRetail.id.desc()).all()

if not offres:
    st.info("Aucune offre validée disponible pour l'export. Traitez vos produits dans le QA Lab d'abord.")
else:
    # Mode Dashboard
    st.markdown("### 🏆 Pépites Actives")
    
    # Filter
    filter_val = st.text_input("Filtrer par Nom / EAN")
    
    for offre in offres:
        prod = offre.produit
        nom = prod.nom_genere if prod else "N/A"
        
        if filter_val and (filter_val.lower() not in nom.lower() and filter_val not in offre.ean):
            continue
            
        with st.container(border=True):
            st.markdown(f"#### {nom}")
            
            col_info, col_chart = st.columns([1, 2])
            
            with col_info:
                st.write(f"**EAN:** {offre.ean}")
                st.write(f"**Enseigne:** {offre.enseigne}")
                st.metric("Cost Target (NetNet)", f"{offre.prix_net_net_calcule} €")
                
                if offre.prix_revente_marche:
                     st.metric("Prix Revente Market (MIN)", f"{offre.prix_revente_marche} €")
                     
                     profit = offre.prix_revente_marche - (offre.prix_net_net_calcule or 0)
                     roi = (profit / (offre.prix_net_net_calcule or 1)) * 100
                     
                     st.write(f"**Profit BRUT estimé:** {profit:.2f}€")
                     st.write(f"**ROI:** {roi:.1f}%")
                else:
                     st.warning("Prix de marché non encore scanné. Le bot prendra le relai au prochain passage.")
                     
            with col_chart:
                # Historique du prix
                history = db.query(PriceHistory).filter_by(ean=offre.ean).order_by(PriceHistory.fetch_date.asc()).all()
                if history:
                    st.write("**Tendance du prix de revente sur internet :**")
                    # Prepare dataframe for line_chart
                    df_chart = pd.DataFrame([{
                        "Date": h.fetch_date,
                        "Prix Revente": h.prix_revente
                    } for h in history])
                    
                    df_chart = df_chart.set_index("Date")
                    st.line_chart(df_chart, use_container_width=True, height=200)
                else:
                    st.info("Pas encore assez d'historique recueilli pour générer un graphique.")
