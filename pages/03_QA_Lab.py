"""
PAGE 3 — QA Lab (The Certification Chamber)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import streamlit as st
from core.models import SessionLocal, CollisionResult, ProduitReference, OffreRetail

st.set_page_config(page_title="QA Lab | Project COLLISION", page_icon="🧪", layout="wide")
st.markdown('<style>.stApp { background-color: #0d1117; color: #c9d1d9; font-family: "Inter", sans-serif; } .qa-panel { background: rgba(22,27,34,0.7); border: 1px solid #30363d; border-radius: 12px; padding: 24px; } .score-bar-bg { height: 14px; width: 100%; background: #21262d; border-radius: 7px; margin-top: 6px; margin-bottom: 20px; border: 1px solid #30363d; } .score-bar-fill { height: 14px; border-radius: 7px; }</style>', unsafe_allow_html=True)
st.markdown("### QA Lab — Reliability Inspection")
st.caption("Inspect extraction proofs. Validate the financial breakdown. Certify or Reject for B2B export.")

db = SessionLocal()
try:
    pending = db.query(CollisionResult).filter(CollisionResult.status_qa == "PENDING_QA").order_by(CollisionResult.roi_percent.desc()).all()
    if not pending: st.success("Queue is clear."); st.stop()
    options = {p.id: f"[{p.certification_grade}] ROI {p.roi_percent}% | Profit {p.profit_net_absolu}E | EAN {p.ean}" for p in pending}
    selected_id = st.selectbox("Select item to inspect", options=list(options.keys()), format_func=lambda x: options[x])
    pepite = db.query(CollisionResult).filter(CollisionResult.id == selected_id).first()
    if not pepite: st.error("Not found."); st.stop()
    produit = db.query(ProduitReference).filter(ProduitReference.ean == pepite.ean).first()
    offre = db.query(OffreRetail).filter(OffreRetail.id == pepite.offre_id).first()
    nom = produit.nom_genere if produit else "Unknown"
    marque = produit.marque if produit else "N/A"
    ean = pepite.ean
    enseigne = offre.enseigne if offre else "Unknown"
    prix_public = offre.prix_public if offre else 0
    remise = offre.remise_immediate if offre else 0
    image_path = offre.image_preuve_path if offre else None
    offre_timestamp = offre.timestamp.strftime('%d/%m/%Y %H:%M') if offre and offre.timestamp else "N/A"
    scenario_json = pepite.scenario_detail_json
    levers = len(pepite.leviers_appliques_json) if pepite.leviers_appliques_json else 0
    pepite_id, prix_achat_net, prix_revente = pepite.id, pepite.prix_achat_net, pepite.prix_revente_estime
    frais, profit, roi = pepite.frais_plateforme, pepite.profit_net_absolu, pepite.roi_percent
    grade = pepite.certification_grade or "B"
except Exception as e:
    st.error(f"Database error: {e}"); db.close(); st.stop()
db.close()

col_img, col_data = st.columns([1.1, 1])
with col_img:
    st.markdown("**Source Proof**")
    has_image = image_path and os.path.exists(image_path)
    if has_image:
        try: st.image(image_path, use_container_width=True, caption=f"Source: {enseigne} | {offre_timestamp}")
        except Exception: st.warning("Image could not be loaded.")
    else:
        st.warning("No screenshot available.")
        if image_path: st.caption(f"Expected: `{image_path}`")
    if scenario_json:
        with st.expander("AST Scenario Trace"): st.json(scenario_json)

with col_data:
    st.markdown(f"**{nom}** ({marque})")
    st.caption(f"EAN: `{ean}`")
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Purchase ({enseigne})**")
        st.metric("Prix Public", f"{prix_public} E")
        st.metric("Remise", f"-{remise} E")
        st.markdown(f"**Net-Net:** :blue[**{prix_achat_net} E**]")
        st.caption(f"{levers} levers stacked.")
    with c2:
        st.markdown("**Resale (BuyBox)**")
        st.metric("Est. Revente", f"{prix_revente} E")
        st.metric("Frais", f"-{frais} E")
        st.markdown(f"**Profit:** :green[**{profit} E**]")
    st.divider()
    penalty = 0
    if not has_image: penalty += 35
    if levers > 3: penalty += 15
    if levers == 0 and prix_public > 0 and remise < (0.30 * prix_public): penalty += 20
    score = max(0, min(100, 100 - penalty))
    color = "#3fb950" if score >= 80 else ("#d29922" if score >= 50 else "#f85149")
    st.markdown(f"**Reliability Score:** <span style='color:{color};font-size:24px;font-weight:800;'>{score}</span>/100", unsafe_allow_html=True)
    st.markdown(f'<div class="score-bar-bg"><div class="score-bar-fill" style="width:{score}%;background:{color};"></div></div>', unsafe_allow_html=True)
    st.markdown(f"**Grade:** `{grade}` | **ROI:** :green[**{roi}%**]")
    ca, cb = st.columns(2)
    with ca:
        if st.button("CERTIFY", key=f"cert_{pepite_id}", use_container_width=True, type="primary"):
            db2 = SessionLocal()
            try:
                item = db2.query(CollisionResult).filter(CollisionResult.id == pepite_id).first()
                if item: item.status_qa = "CERTIFIED"; db2.commit()
            except Exception as e: st.error(str(e))
            finally: db2.close()
            st.rerun()
    with cb:
        if st.button("REJECT", key=f"rej_{pepite_id}", use_container_width=True):
            db2 = SessionLocal()
            try:
                item = db2.query(CollisionResult).filter(CollisionResult.id == pepite_id).first()
                if item: item.status_qa = "REJECTED"; item.rejected_reason = "Manual QA rejection."; db2.commit()
            except Exception as e: st.error(str(e))
            finally: db2.close()
            st.rerun()
