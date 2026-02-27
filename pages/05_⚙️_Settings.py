"""
PAGE 5 — Settings (API Keys & Preferences)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from core.models import SessionLocal, ApiKey
from core.config import gemini_keys, serpapi_keys, scrapingbee_keys

st.set_page_config(page_title="Settings | STAFF v3", page_icon="⚙️", layout="wide")

st.markdown("### ⚙️ Paramètres & Système")
st.caption("Gérez les clés API (Moteurs) et les préférences de l'outil SaaS.")

tab_api, tab_prefs = st.tabs([
    "🔑 Gestionnaire de Clés API",
    "⚙️ Préférences SaaS"
])

with tab_api:
    st.subheader("🔑 Clés API et Rotations (Tier Gratuit)")
    st.markdown("Editez vos clés. Les clés repérées *EXHAUSTED* sont ignorées par les moteurs jusqu'à leur réinitialisation.")

    if st.button("🔄 Réinitialiser le Quota (Passer EXHAUSTED en ACTIVE)"):
        with st.spinner("Réinitialisation..."):
            gemini_keys.reset()
            serpapi_keys.reset()
            scrapingbee_keys.reset()
            st.success("Toutes les clés sont à nouveau paramétrées sur ACTIVE.")
            st.rerun()

    db = SessionLocal()
    try:
        keys_data = db.query(ApiKey).all()
        
        rows = []
        for k in keys_data:
            badge = "🟢 ACTIVE" if k.status == "ACTIVE" else "🔴 EXHAUSTED"
            rows.append({
                "id": k.id,
                "Service": k.service_name,
                "API Key": k.api_key,
                "Statut": badge,
                "Dernière Utilisation": k.last_used.strftime("%Y-%m-%d %H:%M:%S") if k.last_used else "Jamais",
                "Action": False
            })

        df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["id", "Service", "API Key", "Statut", "Dernière Utilisation", "Supprimer"])
        
        with st.expander("➕ Ajouter une nouvelle clé"):
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                new_service = st.selectbox("Service", ["GEMINI", "SERPAPI", "SCRAPINGBEE", "FIRECRAWL"])
            with c2:
                new_key = st.text_input("Clé Secrète", type="password")
            with c3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Ajouter", type="primary", use_container_width=True):
                    if new_key.strip():
                        new_api_key = ApiKey(service_name=new_service, api_key=new_key.strip())
                        db.add(new_api_key)
                        db.commit()
                        st.success(f"Clé pour {new_service} ajoutée.")
                        st.rerun()
                    else:
                        st.error("Gné?")

        if not df.empty:
            edited_df = st.data_editor(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": None,
                    "Action": st.column_config.CheckboxColumn("Supprimer 🗑️"),
                    "Service": st.column_config.SelectboxColumn(
                        "Service", 
                        options=["GEMINI", "SERPAPI", "SCRAPINGBEE", "FIRECRAWL"],
                        required=True
                    ),
                    "API Key": st.column_config.TextColumn("Clé complète", required=True),
                    "Statut": st.column_config.TextColumn(disabled=True),
                    "Dernière Utilisation": st.column_config.TextColumn(disabled=True),
                },
                num_rows="dynamic"
            )

            if st.button("💾 Enregistrer les modifications de la table"):
                updated = 0
                deleted = 0
                
                for index, row in edited_df.iterrows():
                    k_id = row.get("id")
                    if pd.isna(k_id) or k_id is None:
                        if row.get("API Key"):
                            db.add(ApiKey(service_name=row["Service"], api_key=row["API Key"]))
                            updated += 1
                        continue

                    k_obj = db.query(ApiKey).get(k_id)
                    if k_obj:
                        if row.get("Action") is True:
                            db.delete(k_obj)
                            deleted += 1
                        else:
                            if k_obj.api_key != row["API Key"]:
                                k_obj.api_key = row["API Key"]
                                updated += 1
                            if k_obj.service_name != row["Service"]:
                                k_obj.service_name = row["Service"]
                                updated += 1
                
                if updated > 0 or deleted > 0:
                    db.commit()
                    st.success(f"Opération réussie. {updated} mises à jour, {deleted} suppressions.")
                    st.rerun()

    except Exception as e:
        st.error(f"Erreur UI Settings ApiKeys: {e}")
    finally:
        db.close()


with tab_prefs:
    st.subheader("⚙️ Préférences de l'application SaaS")
    
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Nom de l'entreprise", value="STAFF Arbitrage Intelligence")
        st.text_input("Email Admin (Notification système)", value="admin@staff-ai.com")
        st.selectbox("Devise d'export", ["€ (EUR)", "$ (USD)", "£ (GBP)"])
    
    with col2:
        st.selectbox("Thème par défaut", ["Sombre (STAFF)", "Clair (Light)"])
        st.selectbox("Langue Base de Connaissance", ["Français", "Anglais"])
        st.slider("Délai de relance du bot QA (heures)", 1, 24, 2)
        
    st.divider()
    st.button("Sauvegarder les préférences", type="primary", disabled=True)
    st.caption("L'édition des préférences globales est verrouillée en mode MVP.")
