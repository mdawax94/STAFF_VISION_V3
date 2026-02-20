import streamlit as st
import pandas as pd
from core.models import SessionLocal, ProduitBrut

st.set_page_config(page_title="Explorateur", layout="wide")

st.title("🔎 Explorateur Global & Stacking")

search_query = st.text_input("Rechercher un produit (Marque, Nom...)", placeholder="ex: Nintendo, Ariel...")

if search_query:
    session = SessionLocal()
    # Recherche SQL LIKE
    like_query = f"%{search_query}%"
    results = session.query(ProduitBrut).filter(
        (ProduitBrut.produit.like(like_query)) | 
        (ProduitBrut.marque.like(like_query))
    ).all()
    
    if results:
        data = [{
            "Levier": r.levier_type,
            "Marque": r.marque,
            "Produit": r.produit,
            "Prix Net": r.prix_net_net,
            "Status": r.status
        } for r in results]
        
        df = pd.DataFrame(data)
        
        # Color coding basé sur le profit (ici on n'a que le prix net, mais l'explorateur sert à comparer)
        st.dataframe(df, use_container_width=True)
        
        st.success(f"{len(results)} résultats trouvés.")
    else:
        st.warning("Aucun résultat pour cette recherche.")
    session.close()
else:
    st.info("Entrez un terme de recherche pour explorer la base de données brute.")
