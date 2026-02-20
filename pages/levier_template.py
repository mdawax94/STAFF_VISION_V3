import streamlit as st
import pandas as pd
from core.models import SessionLocal, ProduitBrut, PepiteFinale
from agents.reliability_engine import get_market_price, calculate_arbitrage
import os

def render_levier_page(levier_title, levier_type):
    st.title(f"🔍 Leviers : {levier_title}")
    
    session = SessionLocal()
    query = session.query(ProduitBrut).filter(ProduitBrut.levier_type == levier_type)
    prods = query.all()
    
    if not prods:
        st.info(f"Aucun produit brut trouvé pour {levier_type}.")
        session.close()
        return

    # Préparation des données pour le DataFrame éditable
    data = []
    for p in prods:
        data.append({
            "ID": p.id,
            "Image": "📸",
            "Marque": p.marque,
            "Produit": p.produit,
            "Prix Cat.": p.prix_catalogue,
            "Remise": p.remise,
            "Prix Net-Net": p.prix_net_net,
            "Status": p.status,
            "image_path": p.image_path
        })
    
    df = pd.DataFrame(data)

    # Ajout d'une colonne de profit estimé pour le style (ici on simule une marge car on a pas encore le prix de marché sur tout)
    def color_profit(val):
        if val > 20: return "background-color: #2e7d32; color: white;" # Vert
        if val > 10: return "background-color: #ef6c00; color: white;" # Orange
        return "background-color: #c62828; color: white;" # Rouge

    # On affiche le tableau avec style si possible, sinon on utilise le standard car data_editor est limité en style direct
    # Alternative: use st.table with HTML or st.dataframe with style.
    st.dataframe(df.style.applymap(lambda x: color_profit(15) if isinstance(x, (int, float)) and x > 50 else "", subset=["Prix Net-Net"]), use_container_width=True)
    
    edited_df = st.data_editor(
        df,
        column_config={
            "ID": st.column_config.NumberColumn(disabled=True),
            "Image": st.column_config.TextColumn(help="Cliquez sur l'icône dans la ligne pour voir l'image"),
            "Prix Net-Net": st.column_config.NumberColumn(format="%.2f €"),
        },
        disabled=["ID", "Image", "image_path"],
        hide_index=True,
        key=f"editor_{levier_type}"
    )

    # Logique de mise à jour en base au clic sur "Sauvegarder les modifications"
    if st.button("💾 Sauvegarder les modifications", key=f"save_{levier_type}"):
        for index, row in edited_df.iterrows():
            orig = session.query(ProduitBrut).filter(ProduitBrut.id == row["ID"]).first()
            if orig:
                orig.marque = row["Marque"]
                orig.produit = row["Produit"]
                orig.prix_catalogue = row["Prix Cat."]
                orig.remise = row["Remise"]
                orig.prix_net_net = row["Prix Net-Net"]
                orig.status = row["Status"]
        session.commit()
        st.success("Base de données mise à jour.")

    # Visualisation de preuve et Validation
    st.divider()
    selected_id = st.selectbox("Sélectionnez un produit pour Action / Aperçu", df["ID"].tolist(), key=f"select_{levier_type}")
    
    if selected_id:
        p_row = df[df["ID"] == selected_id].iloc[0]
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("🖼️ Aperçu de Preuve")
            if os.path.exists(p_row["image_path"]):
                st.image(p_row["image_path"], use_container_width=True)
            else:
                st.warning("Image non trouvée sur le disque.")
        
        with col2:
            st.subheader("⚖️ Validation Juge")
            if st.button("✅ APPROVE & ANALYZE (Agent Juge)", key=f"approve_{selected_id}"):
                with st.spinner("Le Juge analyse les prix du marché..."):
                    market_data = get_market_price(p_row["Produit"])
                    if market_data:
                        # On récupère le score de vision (si disponible, sinon 0)
                        # Pour simplifier on va dire 80 par défaut si validé manuellement
                        decision = calculate_arbitrage(p_row["Prix Net-Net"], market_data, 80, p_row["Produit"])
                        
                        # Création de la Pépite
                        new_pepite = PepiteFinale(
                            produit_brut_id=selected_id,
                            produit_name=p_row["Produit"],
                            marge_nette=decision["potential_profit"],
                            reliability_score=decision["similarity_score"]
                        )
                        session.add(new_pepite)
                        
                        # Mise à jour du statut
                        db_p = session.query(ProduitBrut).filter(ProduitBrut.id == selected_id).first()
                        db_p.status = "APPROVED"
                        
                        session.commit()
                        st.success(f"Pépite enregistrée ! Profit: {decision['potential_profit']}€ | Fiabilité: {decision['confidence_index']}")
                        st.balloons()
    
    session.close()

if __name__ == "__main__":
    # Ce script sert de base pour 2_Catalogues.py, 3_Coupons.py, 4_ODR.py
    pass
