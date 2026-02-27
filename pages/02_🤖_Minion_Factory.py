"""
PAGE 2 — Mission Control (Phase 4)
QG Granulaire pour piloter les missions et chaque URL spécifiquement.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import asyncio
from datetime import datetime

from core.models import SessionLocal, MissionConfig, MissionLog

st.set_page_config(page_title="Mission Control | STAFF v3", page_icon="🤖", layout="wide")
st.title("🤖 Mission Control — QG Granulaire")
st.caption("Pilotez individuellement chaque URL, tracez les échecs et dupliquez vos missions.")

tab_builder, tab_radar, tab_history = st.tabs([
    "🎯 Éditeur de Mission",
    "📡 Radar Live",
    "🗄️ Historique"
])

if "edit_mission_id" not in st.session_state:
    st.session_state["edit_mission_id"] = None
if "form_defaults" not in st.session_state:
    st.session_state["form_defaults"] = {}

def load_mission_to_editor(mission_id, duplicate=False):
    db = SessionLocal()
    try:
        m = db.query(MissionConfig).filter(MissionConfig.id == mission_id).first()
        if m:
            st.session_state["edit_mission_id"] = None if duplicate else m.id
            prefix = "Copie de " if duplicate else ""
            urls_list = [{"URLs Cibles": u} for u in (m.target_urls or [])]
            if not urls_list: urls_list = [{"URLs Cibles": ""}]
            
            st.session_state["form_defaults"] = {
                "nom": prefix + m.nom,
                "mission_type": m.mission_type,
                "worker_type": m.worker_type,
                "urls": urls_list,
                "output_schema": m.output_schema,
                "ai_prompt": m.ai_prompt_override or "",
            }
            if m.extraction_params:
                st.session_state["form_defaults"].update(m.extraction_params)
    finally:
        db.close()

def get_def(key, default):
    return st.session_state["form_defaults"].get(key, default)

with tab_builder:
    is_editing = st.session_state["edit_mission_id"] is not None
    st.subheader("🎯 Éditeur de Mission" if is_editing else "🎯 Déployer une nouvelle mission")
    
    if is_editing:
        st.info(f"✏️ Mode Édition: Modification de la mission #{st.session_state['edit_mission_id']}")
        if st.button("❌ Annuler l'édition"):
            st.session_state["edit_mission_id"] = None
            st.session_state["form_defaults"] = {}
            st.rerun()

    with st.form("mission_builder", clear_on_submit=False):
        st.markdown("### 1️⃣ Paramètres Principaux")
        c1, c2 = st.columns(2)
        with c1:
            mission_name = st.text_input("Nom de la mission", value=get_def("nom", ""))
        with c2:
            m_types = ["PRICE_CHECK", "PROMO_SCAN", "CATALOGUE_FULL"]
            cur_type = get_def("mission_type", "PRICE_CHECK")
            mission_type = st.selectbox("Type", m_types, index=m_types.index(cur_type) if cur_type in m_types else 0)

        st.markdown("### 2️⃣ URLs Cibles (Gestion Unitaire)")
        initial_urls = get_def("urls", [{"URLs Cibles": "https://"}])
        df_urls = pd.DataFrame(initial_urls)
        edited_urls_df = st.data_editor(
            df_urls,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        st.markdown("### 3️⃣ Moteur & IA")
        w_types = ["HEADLESS_CAMELEON", "API_FURTIF", "VISION_SNIPER"]
        cur_w = get_def("worker_type", "HEADLESS_CAMELEON")
        worker_type = st.radio("Moteur", w_types, index=w_types.index(cur_w) if cur_w in w_types else 0, horizontal=True)

        c3, c4 = st.columns(2)
        with c3:
            s_types = ["catalogue", "regles"]
            cur_s = get_def("output_schema", "catalogue")
            output_schema = st.selectbox("Schéma de Sortie IA", s_types, index=s_types.index(cur_s) if cur_s in s_types else 0)
        with c4:
            ai_prompt_override = st.text_input("Prompt Custom (Optionnel)", value=get_def("ai_prompt", ""))

        st.divider()
        
        btn_label = "💾 Mettre à jour la mission" if is_editing else "🚀 Déployer la mission"
        submitted = st.form_submit_button(btn_label, type="primary", use_container_width=True)

        if submitted:
            final_urls = [row["URLs Cibles"].strip() for _, row in edited_urls_df.iterrows() if "URLs Cibles" in row and row["URLs Cibles"].strip() and row["URLs Cibles"].startswith("http")]
            
            if not mission_name or len(mission_name) < 3:
                st.error("Le nom doit faire 3 caractères minimum.")
            elif not final_urls:
                st.error("Ajoutez au moins 1 URL valide.")
            else:
                db_save = SessionLocal()
                try:
                    params = {"max_pages": get_def("max_pages", 1), "requires_scroll": get_def("requires_scroll", False)}
                    
                    if is_editing:
                        mission = db_save.query(MissionConfig).filter(MissionConfig.id == st.session_state["edit_mission_id"]).first()
                        mission.nom = mission_name
                        mission.mission_type = mission_type
                        mission.worker_type = worker_type
                        mission.target_urls = final_urls
                        mission.output_schema = output_schema
                        mission.ai_prompt_override = ai_prompt_override
                        mission.extraction_params = params
                        st.success("Mission mise à jour avec succès!")
                    else:
                        mission = MissionConfig(
                            nom=mission_name,
                            mission_type=mission_type,
                            worker_type=worker_type,
                            target_urls=final_urls,
                            output_schema=output_schema,
                            ai_prompt_override=ai_prompt_override,
                            extraction_params=params,
                            status="IDLE",
                            is_active=True
                        )
                        db_save.add(mission)
                        st.success("Mission créée avec succès!")
                    db_save.commit()
                    st.session_state["edit_mission_id"] = None
                    st.session_state["form_defaults"] = {}
                except Exception as e:
                    st.error(f"Erreur DB: {e}")
                    db_save.rollback()
                finally:
                    db_save.close()


with tab_radar:
    st.subheader("📡 Radar Live & Suivi Granulaire")
    
    db_radar = SessionLocal()
    try:
        live_missions = db_radar.query(MissionConfig).filter(MissionConfig.status == "RUNNING").all()
        
        if not live_missions:
            st.info("Aucune mission en cours de traitement par le moteur. 🟢")
            
        for m in live_missions:
            st.markdown(f"#### 🚀 Mission : {m.nom} ({m.worker_type})")
            
            logs = db_radar.query(MissionLog).filter(MissionLog.mission_id == m.id).all()
            total_urls = len(m.target_urls) if m.target_urls else 1
            completed = sum(1 for l in logs if l.statut in ("SUCCESS", "FAILED"))
            successes = sum(1 for l in logs if l.statut == "SUCCESS")
            failures = sum(1 for l in logs if l.statut == "FAILED")
            
            progress = min(1.0, completed / total_urls)
            st.progress(progress, text=f"Progression : {completed} / {total_urls} URLs traitées")
            
            k1, k2, k3 = st.columns(3)
            k1.metric("✅ Succès", successes)
            k2.metric("❌ Échecs", failures)
            k3.metric("⏳ En attente/En cours", total_urls - completed)
            
            with st.expander(f"Logs Détaillés URL par URL ({len(logs)} enregistrés)", expanded=(failures > 0)):
                if not logs:
                    st.caption("Aucun log encore généré pour cette exécution.")
                else:
                    log_data = []
                    for log in logs:
                        log_data.append({
                            "Status": "✅ OK" if log.statut=="SUCCESS" else ("❌ FAILED" if log.statut=="FAILED" else "🔄 PROC"),
                            "URL": log.url_cible,
                            "Message": log.message_erreur or "",
                            "Heure": log.timestamp.strftime("%H:%M:%S")
                        })
                    st.dataframe(pd.DataFrame(log_data), use_container_width=True)
                    
                    if failures > 0:
                        st.warning(f"⚠️ {failures} URL(s) ont échoué. Examinez les messages dans le tableau ci-dessus.")
                        if st.button("🔄 Lancer un Mini-Batch pour les FAILED", key=f"relaunch_{m.id}"):
                            failed_urls = [l.url_cible for l in logs if l.statut == "FAILED"]
                            sub = MissionConfig(
                                nom=f"[RETRY] {m.nom}",
                                mission_type=m.mission_type,
                                worker_type=m.worker_type,
                                target_urls=failed_urls,
                                output_schema=m.output_schema,
                                ai_prompt_override=m.ai_prompt_override,
                                extraction_params=m.extraction_params,
                                status="IDLE",
                            )
                            db_radar.add(sub)
                            db_radar.commit()
                            st.success("Sous-mission créée pour traiter uniquement les URLs en échec. Lancez-la depuis l'Historique.")
            st.divider()
    finally:
        db_radar.close()

with tab_history:
    st.subheader("🗄️ Historique & Bibliothèque")
    
    db_hist = SessionLocal()
    try:
        history_missions = db_hist.query(MissionConfig).filter(MissionConfig.status != "RUNNING").order_by(MissionConfig.id.desc()).all()
        
        if not history_missions:
            st.info("Aucune archive de mission pour le moment.")
        else:
            colA, colB = st.columns([3, 1])
            with colB:
                st.write("Actions Rapides")
                hm_map = {f"#{m.id} {m.nom}": m.id for m in history_missions}
                selected_hm = st.selectbox("Mission cible", list(hm_map.keys()))
                sel_id = hm_map.get(selected_hm)
                
                if st.button("▶️ Forcer le lancement", type="primary", use_container_width=True):
                    from core.scraper_engine import ScraperEngine
                    st.toast(f"Moteur engagé sur '{selected_hm}'...", icon="🚀")
                    def run_engine_sync(mid):
                        engine = ScraperEngine(mission_config_id=mid)
                        asyncio.run(engine.run())
                    
                    run_engine_sync(sel_id)
                    st.success("Mission exécutée !")
                    st.rerun()

                if st.button("🔄 Dupliquer", use_container_width=True):
                    load_mission_to_editor(sel_id, duplicate=True)
                    st.success("Formulaire pré-rempli dans l'éditeur.")
                
                if st.button("✏️ Éditer", use_container_width=True):
                    load_mission_to_editor(sel_id, duplicate=False)
                    st.success("Mode Édition activé dans l'éditeur.")
                    
                if st.button("🗑️ Supprimer", use_container_width=True):
                    db_hist.query(MissionLog).filter(MissionLog.mission_id == sel_id).delete()
                    db_hist.query(MissionConfig).filter(MissionConfig.id == sel_id).delete()
                    db_hist.commit()
                    st.rerun()

            with colA:
                rows = []
                for m in history_missions:
                    logs = db_hist.query(MissionLog).filter(MissionLog.mission_id == m.id).all()
                    t_urls = len(m.target_urls) if m.target_urls else 0
                    successes = sum(1 for l in logs if l.statut == "SUCCESS")
                    rate = f"{(successes / t_urls * 100):.0f}%" if t_urls > 0 else "N/A"
                    
                    rows.append({
                        "ID": m.id,
                        "Nom": m.nom,
                        "Moteur": m.worker_type,
                        "URLs": t_urls,
                        "Durée": f"{m.last_run_duration_s:.1f}s" if m.last_run_duration_s else "-",
                        "Taux Succès": rate,
                        "Statut Final": m.status,
                        "Date": m.last_run.strftime("%d/%m/%Y %H:%M") if m.last_run else "-"
                    })
                
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                
    finally:
        db_hist.close()
