"""
PAGE 2 — Minion Factory (Création de Missions & Agents)
Version 4 : "Mission Control Hub"
Tabs : Éditeur de Mission (Data Editor), Jauge/Logs en temps réel, Historique.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from datetime import datetime

from core.models import SessionLocal, MissionConfig, MissionLog
# Import direct asyncio is often tricky in Streamlit, better to spawn subprocesses or rely on the background worker
from core.scraper_engine import WORKER_TYPES

st.set_page_config(page_title="Minion Factory HQ", page_icon="🤖", layout="wide")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def load_missions(db: Session, status_filter=None):
    q = db.query(MissionConfig)
    if status_filter:
        q = q.filter(MissionConfig.status == status_filter)
    return q.order_by(MissionConfig.id.desc()).all()


st.title("🤖 Minion Factory HQ")
st.markdown("Créez, lancez et monitorez vos campagnes d'extraction en masse.")


# ---- TABS INTERFACE ----
tab1, tab2, tab3 = st.tabs(["🎯 Éditeur de Missions", "📡 Live Radar", "📚 Bibliothèque"])

# ==========================================================
# TAB 1 : CRÉATEUR DE MISSION
# ==========================================================
with tab1:
    st.subheader("Créer une nouvelle Mission")
    
    with st.form("new_mission_form"):
        col1, col2 = st.columns(2)
        with col1:
            nom = st.text_input("Nom de la Mission (ex: 'Scrap Carrefour ODR')", max_chars=100)
            worker_type = st.selectbox("Moteur", options=list(WORKER_TYPES), index=1)
            mission_type = st.selectbox("Type d'Extraction", ["PRICE_CHECK", "PROMO_SCAN", "CATALOGUE_FULL"])
        with col2:
             frequence = st.selectbox("Fréquence", ["manual", "daily", "weekly", "hourly"])
             max_pages = st.number_input("Max Pages / URL", min_value=1, max_value=100, value=1)
             schema_type = st.selectbox("Schéma attendu (IA)", ["catalogue", "regles", "custom"])
             
        st.markdown("### 📋 URLs Cibles")
        st.markdown("Ajoutez/Modifiez/Supprimez les URLs à cibler dans la grille ci-dessous.")
        
        # Le fameux data_editor
        if "url_df" not in st.session_state:
            st.session_state.url_df = pd.DataFrame([{"URLs Cibles": "https://"}])
            
        edited_df = st.data_editor(
            st.session_state.url_df, 
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "URLs Cibles": st.column_config.LinkColumn(display_text="https://")
            }
        )

        submit = st.form_submit_button("🚀 Déployer la Mission", type="primary")
        
        if submit:
            if not nom:
                st.error("Le nom est obligatoire.")
            else:
                # Filtrer les URLs vides ou par défaut
                urls = [u for u in edited_df["URLs Cibles"].tolist() if u and str(u).strip() != "https://"]
                if not urls:
                    st.error("Ajoutez au moins une URL valide !")
                else:
                    db = next(get_db())
                    new_m = MissionConfig(
                        nom=nom,
                        worker_type=worker_type,
                        mission_type=mission_type,
                        target_urls=urls,
                        frequence_cron=frequence,
                        output_schema=schema_type,
                        extraction_params={"max_pages": max_pages, "requires_scroll": True}
                    )
                    db.add(new_m)
                    db.commit()
                    # Pre-populate logs
                    for u in urls:
                        db.add(MissionLog(mission_id=new_m.id, url_cible=u, statut="PENDING"))
                    db.commit()
                    
                    st.success(f"Mission '{nom}' déployée dans le pipeline ! ID: {new_m.id}")


# ==========================================================
# TAB 2 : LIVE RADAR (Suivi des URLs en temps réel)
# ==========================================================
with tab2:
    st.subheader("Scan Actuel")
    db = next(get_db())
    
    # Trouver une mission en cours
    running_mission = db.query(MissionConfig).filter(MissionConfig.status == "RUNNING").order_by(MissionConfig.id.desc()).first()
    
    if running_mission:
        st.info(f"⚡ **Mission en cours :** {running_mission.nom} (Moteur: {running_mission.worker_type})")
        
        logs = db.query(MissionLog).filter(MissionLog.mission_id == running_mission.id).all()
        total = len(logs)
        success = len([l for l in logs if l.statut == "SUCCESS"])
        failed = len([l for l in logs if l.statut == "FAILED"])
        processing = len([l for l in logs if l.statut == "PROCESSING"])
        pending = len([l for l in logs if l.statut == "PENDING"])
        
        # Jauge
        if total > 0:
            progress_val = (success + failed) / total
            st.progress(progress_val, text=f"Progression globale ({success+failed}/{total})")
            
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("✅ Succès", success)
        c2.metric("❌ Échecs", failed)
        c3.metric("⏳ En traitement", processing)
        c4.metric("🕰️ En attente", pending)
        
        # Expander de Logs avec dataframe style
        with st.expander("🔍 Logs Détaillés URL par URL", expanded=True):
            if logs:
                log_data = []
                for l in logs:
                    log_data.append({
                        "Statut": "✅" if l.statut=="SUCCESS" else "❌" if l.statut=="FAILED" else "🔄" if l.statut=="PROCESSING" else "⏳",
                        "URL": l.url_cible,
                        "Erreur": l.message_erreur or "",
                        "Dernière M.A.J": l.timestamp.strftime("%H:%M:%S") if l.timestamp else ""
                    })
                df_logs = pd.DataFrame(log_data)
                st.dataframe(df_logs, use_container_width=True, hide_index=True)
    else:
        st.info("😴 Aucune mission en cours d'exécution.")
        
        if st.button("🔄 Rafraîchir l'Etat du Serveur"):
             st.rerun()

# ==========================================================
# TAB 3 : BIBLIOTHEQUE (Historique des missions)
# ==========================================================
with tab3:
    st.subheader("Historique des Missions")
    db = next(get_db())
    missions = db.query(MissionConfig).order_by(MissionConfig.id.desc()).limit(50).all()
    
    if not missions:
         st.write("Aucune mission enregistrée.")
    else:
        cols = st.columns((1, 3, 2, 2, 2, 2))
        cols[0].write("**ID**")
        cols[1].write("**Nom**")
        cols[2].write("**Statut**")
        cols[3].write("**Nombre URLs**")
        cols[4].write("**Dernière exéc**")
        cols[5].write("**Action**")

        st.divider()
        
        for m in missions:
            c = st.columns((1, 3, 2, 2, 2, 2))
            c[0].write(str(m.id))
            c[1].write(m.nom)
            
            # Colored Status
            color = "green" if m.status == "IDLE" and not m.error_message else "orange" if m.status == "RUNNING" else "red"
            c[2].markdown(f"**:{color}[{m.status}]**")
            
            c[3].write(str(len(m.target_urls) if m.target_urls else 0))
            c[4].write(m.last_run.strftime("%Y-%m-%d %H:%M") if m.last_run else "Jamais")
            
            # Action button
            if c[5].button("⚡ RE-RUN", key=f"run_{m.id}"):
                # Changer status et remettre tous les logs en PENDING
                m.status = "RUNNING"
                
                # Update logs back to pending
                logs = db.query(MissionLog).filter(MissionLog.mission_id == m.id).all()
                for l in logs:
                    db.delete(l)
                db.commit()
                
                for u in m.target_urls:
                    db.add(MissionLog(mission_id=m.id, url_cible=u, statut="PENDING"))
                    
                db.commit()
                st.success(f"Mission {m.id} réinsérée dans la boucle !")
                st.rerun()
