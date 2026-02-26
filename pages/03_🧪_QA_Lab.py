"""
PAGE 3 — Le QA Lab (Phase 5: Split-Screen Kanban)
Centre de Triage B2B. Interface séparée en deux pour traiter les flux massifs d'extractions.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from datetime import datetime

from core.models import SessionLocal, OffreRetail, ProduitReference

st.set_page_config(page_title="Le QA Lab (Kanban)", page_icon="🧪", layout="wide")

st.markdown("""
<style>
    /* Styling for Kanban look */
    .card-pending { border-left: 5px solid #ffcc00; padding-left:10px; margin-bottom: 20px;}
    .card-validated { border-left: 5px solid #28a745; padding-left:10px; margin-bottom: 20px;}
    .card-rejected { border-left: 5px solid #dc3545; padding-left:10px; margin-bottom: 20px;}
    .metric-value { font-size: 1.2em; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


st.title("🧪 Le QA Lab — Split-Screen Kanban")

db = next(get_db())

# Initialize session states
if "selected_offre_id" not in st.session_state:
    st.session_state.selected_offre_id = None
if "bulk_selection" not in st.session_state:
    st.session_state.bulk_selection = []

# Fetch Data
pending_offres = db.query(OffreRetail).filter(OffreRetail.qa_status.in_(["PENDING", "FLAGGED"])).order_by(OffreRetail.id.desc()).all()


# ==========================================================
# UI LAYOUT: LEFT_COLUMN (KANBAN LIST) | RIGHT_COLUMN (INSPECTION)
# ==========================================================
col_list, col_inspect = st.columns([1, 1.2], gap="large")

# ----------------- COLONNE GAUCHE (FILE D'ATTENTE) -----------------
with col_list:
    st.subheader(f"📥 À Valider ({len(pending_offres)})")
    
    if pending_offres:
        # Bulk Actions Select All
        if st.button("Tout Supprimer (Flush)"):
            for o in pending_offres:
                db.delete(o)
            db.commit()
            st.rerun()

        # Display Kanban format
        for o in pending_offres:
            prod_name = o.produit.nom_genere if o.produit else "Nettoyage Orphelin"
            badge = "⚠️ FLAG" if o.qa_status == "FLAGGED" else "⏳ PENDING"
            score_color = "red" if o.reliability_score < 0.5 else "orange" if o.reliability_score < 0.8 else "green"
            
            with st.container():
                st.markdown(f'<div class="card-pending">', unsafe_allow_html=True)
                
                cols = st.columns([3, 1, 1])
                cols[0].write(f"**{prod_name[:40]}**")
                cols[1].write(f"**{o.prix_net_net_calcule}€**")
                
                # Select Event
                if cols[2].button("Inspector", key=f"inspect_{o.id}", use_container_width=True):
                    st.session_state.selected_offre_id = o.id
                    st.rerun()
                
                # Meta line
                st.write(f"🏭 {o.enseigne} | EAN: {o.ean} | **Score:** :{score_color}[{int(o.reliability_score*100)}%] | {badge}")
                st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.success("File d'attente vide. Le travail de l'IA est à jour !")


# ----------------- COLONNE DROITE (LE MICROSCOPE) -----------------
with col_inspect:
    st.subheader("🔬 L'Inspecteur")
    st.divider()
    
    if st.session_state.selected_offre_id:
        target_offre = db.query(OffreRetail).filter_by(id=st.session_state.selected_offre_id).first()
        
        if target_offre:
            prod = target_offre.produit
            
            # En-tête du Panneau
            st.header(prod.nom_genere if prod else "Inconnu")
            st.metric("EAN Associé", target_offre.ean)
            
            # Les Chiffres (Décomposition du Prix)
            c1, c2, c3 = st.columns(3)
            c1.metric("Prix Magasin Brut", f"{target_offre.prix_brut or target_offre.prix_public} €")
            c2.metric("Remises / Coupons", f"- {target_offre.valeur_coupon or 0} €")
            c3.metric("Prix Target B2B (Net-Net) ✨", f"**{target_offre.prix_net_net_calcule} €**")
            
            st.divider()
            
            # Les Preuves IA
            st.markdown("### 📸 Source Originelle & Preuve")
            sc1, sc2 = st.columns(2)
            with sc1:
                st.write(f"**Enseigne:** {target_offre.enseigne}")
                st.write(f"**Source URL:** [Lien direct]({target_offre.source_url})")
            with sc2:
                 st.write(f"**Score de Fiabilité:** {int(target_offre.reliability_score*100)}%")
                 if target_offre.flag_reason:
                     st.error(f"**Attention (FLAG):** {target_offre.flag_reason}")
                 else:
                     st.info("Tout semble cohérent.")
            
            # Boutons Moteurs d'Action Finale
            st.markdown("### Décision")
            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("✅ VALIDER STRICT", use_container_width=True, type="primary"):
                    target_offre.qa_status = "VALIDATED"
                    # On le pousse automatique au format certifié phase 1
                    target_offre.validation_humaine_phase_1 = "VALIDATED"
                    db.commit()
                    st.session_state.selected_offre_id = None
                    st.rerun()
            with b2:
                if st.button("❌ REJETER FAUX-POSITIF", use_container_width=True):
                    db.delete(target_offre)
                    db.commit()
                    st.session_state.selected_offre_id = None
                    st.rerun()
            with b3:
                if st.button("⚠️ CORRIGER EAN", use_container_width=True):
                    st.warning("Fonctionnalité d'édition in-place (Bientôt dispo)")

            
        else:
             st.error("Cette offre n'existe plus en base (déjà traitée ?).")
             st.session_state.selected_offre_id = None
    else:
        st.write("👈 Sélectionnez un produit dans la file d'attente pour l'inspecter.")
