"""
PAGE 9 — Collision Dashboard (QA Lab & Pépites Certifiées)
Interface Streamlit pour visualiser les résultats du Moteur de Collision, valider/rejeter les pépites, et déclencher.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from core.models import (
    CollisionResult, OffreRetail, ProduitReference, MarketSonde,
    LevierActif, RulesMatrix, AgentConfig, SessionLocal
)
from engine.collision_engine import CollisionEngine

st.set_page_config(page_title="💥 Collision Dashboard", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    .pepite-card { background: linear-gradient(135deg, #0d1b2a 0%, #1b2838 100%); border-radius: 14px; padding: 20px; margin-bottom: 18px; border-left: 5px solid #00b4d8; }
    .pepite-card.grade-a-plus { border-left-color: #06d6a0; }
    .pepite-card.grade-a { border-left-color: #00b4d8; }
    .pepite-card.grade-b { border-left-color: #ffd60a; }
    .pepite-card.grade-c { border-left-color: #e76f51; }
    .grade-badge { display: inline-block; padding: 6px 16px; border-radius: 20px; font-weight: bold; font-size: 16px; }
    .grade-a-plus { background: #064e3b; color: #06d6a0; }
    .grade-a { background: #0c3547; color: #00b4d8; }
    .grade-b { background: #3a2d0a; color: #ffd60a; }
    .grade-c { background: #3d1a0a; color: #e76f51; }
    .metric-hero { background: linear-gradient(135deg, #16213e 0%, #0f3460 100%); border-radius: 16px; padding: 24px; text-align: center; border: 1px solid #1a3a5c; }
    .metric-hero h1 { color: #e94560; margin: 0; font-size: 48px; }
    .metric-hero p { color: #a0aec0; margin: 4px 0 0 0; }
    .price-line { background: #111827; border-radius: 8px; padding: 10px 14px; margin: 4px 0; font-family: monospace; }
    .pipeline-stat { background: #1a1a2e; border: 1px solid #30475e; border-radius: 10px; padding: 14px; text-align: center; }
    .pipeline-stat h3 { color: #e0e0e0; margin: 0; font-size: 28px; }
    .pipeline-stat p { color: #718096; font-size: 12px; margin: 4px 0 0 0; }
</style>
""", unsafe_allow_html=True)

def get_grade_css(grade: str) -> tuple:
    grades = {"A+": ("grade-a-plus", "💎"), "A": ("grade-a", "⭐"), "B": ("grade-b", "🔶"), "C": ("grade-c", "🔸")}
    return grades.get(grade, ("grade-c", "❓"))

st.markdown("# \ud83d\udca5 Collision Dashboard")
st.markdown("*Centre QA \u2014 Visualisez, validez et exportez vos P\u00e9pites Certifi\u00e9es.*")
st.markdown("---")

db = SessionLocal()
try:
    total_produits = db.query(ProduitReference).count()
    total_offres = db.query(OffreRetail).filter(OffreRetail.is_active == True).count()
    total_leviers = db.query(LevierActif).filter(LevierActif.is_active == True).count()
    total_rules = db.query(RulesMatrix).count()
    total_market = db.query(MarketSonde).count()
    total_collisions = db.query(CollisionResult).count()
    total_certified = db.query(CollisionResult).filter(CollisionResult.status_qa == "CERTIFIED").count()
    total_pending = db.query(CollisionResult).filter(CollisionResult.status_qa == "PENDING_QA").count()
finally:
    db.close()

st.markdown("### \ud83d\udcca Pipeline Data Factory")
cols = st.columns(6)
pipeline_data = [
    (total_produits, "Produits (EAN)"), (total_offres, "Offres Actives"), (total_leviers, "Leviers Actifs"),
    (total_rules, "R\u00e8gles AST"), (total_market, "Sondes Market"), (total_collisions, "Collisions"),
]
for i, (val, label) in enumerate(pipeline_data):
    with cols[i]:
        st.markdown(f'<div class="pipeline-stat"><h3>{val}</h3><p>{label}</p></div>', unsafe_allow_html=True)

st.markdown("---")

col_trigger, col_stats = st.columns([1, 2])

with col_trigger:
    st.markdown("### \u26a1 Lancer la Collision")
    min_roi = st.number_input("ROI Minimum (%)", value=15.0, min_value=0.0, max_value=100.0, step=5.0)
    
    if st.button("\ud83d\udca5 LANCER LE MOTEUR DE COLLISION", type="primary", use_container_width=True):
        with st.spinner("Collision en cours... Croisement des donn\u00e9es..."):
            engine = CollisionEngine(min_roi_percent=min_roi)
            result = engine.run_collision()
        
        if result.get("error"):
            st.error(f"\u274c Erreur: {result['error']}")
        else:
            st.success(f"\u2705 **{result['pepites']}** p\u00e9pites g\u00e9n\u00e9r\u00e9es, **{result['rejected']}** rejet\u00e9es.")
            st.rerun()

with col_stats:
    st.markdown("### \ud83d\udcc8 R\u00e9partition des Grades")
    db = SessionLocal()
    try:
        grade_counts = {}
        for grade_label in ["A+", "A", "B", "C"]:
            count = db.query(CollisionResult).filter(CollisionResult.certification_grade == grade_label).count()
            grade_counts[grade_label] = count
    finally:
        db.close()

    gcols = st.columns(4)
    for i, (grade, count) in enumerate(grade_counts.items()):
        css, emoji = get_grade_css(grade)
        with gcols[i]:
            st.markdown(f'<div class="metric-hero"><h1>{count}</h1><p>{emoji} Grade {grade}</p></div>', unsafe_allow_html=True)

st.markdown("---")
st.markdown("### \u2b50 P\u00e9pites en Attente de Validation")

tab_pending, tab_certified, tab_all = st.tabs(["\u23f3 En attente QA", "\u2705 Certifi\u00e9es", "\ud83d\udccb Toutes"])

def render_pepites(status_filter=None):
    db = SessionLocal()
    try:
        query = db.query(CollisionResult).order_by(CollisionResult.roi_percent.desc())
        if status_filter:
            query = query.filter(CollisionResult.status_qa == status_filter)
        
        pepites = query.limit(50).all()
        if not pepites:
            st.info("Aucune p\u00e9pite dans cette cat\u00e9gorie.")
            return

        for pep in pepites:
            produit = db.query(ProduitReference).filter(ProduitReference.ean == pep.ean).first()
            offre = db.query(OffreRetail).filter(OffreRetail.id == pep.offre_id).first()
            if not produit or not offre:
                continue

            grade_css, grade_emoji = get_grade_css(pep.certification_grade or "C")

            st.markdown(f"""
            <div class="pepite-card {grade_css}">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <h3 style="margin:0; color:#fafafa;">{produit.nom_genere}</h3>
                        <p style="color:#a0aec0; margin:2px 0;">
                            {produit.marque or 'N/A'} \u2014 EAN: <code>{pep.ean}</code> \u2014 {offre.enseigne}
                        </p>
                    </div>
                    <span class="grade-badge {grade_css}">{grade_emoji} {pep.certification_grade or '?'}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            col_price, col_market, col_action = st.columns([2, 2, 1])

            with col_price:
                st.markdown(f"""
                <div class="price-line">
                \ud83d\udcb0 Prix Public: <strong>{offre.prix_public:.2f}\u20ac</strong><br>
                \ud83c\udff7\ufe0f Remise Enseigne: <strong>-{offre.remise_immediate:.2f}\u20ac</strong><br>
                \ud83c\udfab Leviers Cumul\u00e9s: <strong>{len(pep.leviers_appliques_json or [])} levier(s)</strong><br>
                \u2705 <span style="color:#06d6a0; font-size:18px;">Net-Net: <strong>{pep.prix_achat_net:.2f}\u20ac</strong></span>
                </div>
                """, unsafe_allow_html=True)

            with col_market:
                if pep.prix_revente_estime > 0:
                    st.markdown(f"""
                    <div class="price-line">
                    \ud83d\udce6 Revente Estim\u00e9e: <strong>{pep.prix_revente_estime:.2f}\u20ac</strong><br>
                    \ud83d\udcb8 Frais Plateforme: <strong>-{pep.frais_plateforme:.2f}\u20ac</strong><br>
                    \ud83d\udcb5 <span style="color:#06d6a0;">Profit Net: <strong>{pep.profit_net_absolu:.2f}\u20ac</strong></span><br>
                    \ud83d\udcc8 <span style="color:#ffd60a; font-size:18px;">ROI: <strong>{pep.roi_percent:.1f}%</strong></span>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class="price-line" style="color:#718096;">
                    \ud83d\udce6 Aucune donn\u00e9e march\u00e9 disponible.<br>
                    Lancez la Sonde Market pour obtenir le ROI.
                    </div>
                    """, unsafe_allow_html=True)

            with col_action:
                if pep.status_qa == "PENDING_QA":
                    if st.button("\u2705 CERTIFIER", key=f"cert_{pep.id}", type="primary"):
                        pep_db = db.query(CollisionResult).filter(CollisionResult.id == pep.id).first()
                        if pep_db:
                            pep_db.status_qa = "CERTIFIED"
                            db.commit()
                        st.rerun()
                    if st.button("\u274c Rejeter", key=f"rej_{pep.id}"):
                        pep_db = db.query(CollisionResult).filter(CollisionResult.id == pep.id).first()
                        if pep_db:
                            pep_db.status_qa = "REJECTED"
                            pep_db.rejected_reason = "Rejet\u00e9 manuellement par l'op\u00e9rateur QA"
                            db.commit()
                        st.rerun()
                elif pep.status_qa == "CERTIFIED":
                    st.markdown("\u2705 **Certifi\u00e9e**")
                else:
                    st.markdown(f"\u274c {pep.rejected_reason or 'Rejet\u00e9e'}")

            st.markdown("---")
    finally:
        db.close()

with tab_pending:
    render_pepites("PENDING_QA")
with tab_certified:
    render_pepites("CERTIFIED")
with tab_all:
    render_pepites()

st.markdown("---")
st.markdown("### \ud83d\udce4 Export B2B")

col_exp1, col_exp2 = st.columns(2)
with col_exp1:
    export_grade = st.multiselect("Filtrer par grade", ["A+", "A", "B", "C"], default=["A+", "A"])
with col_exp2:
    export_status = st.selectbox("Statut", ["CERTIFIED", "PENDING_QA", "Tous"])

if st.button("\ud83d\udce5 G\u00e9n\u00e9rer Export CSV", use_container_width=True):
    db = SessionLocal()
    try:
        query = db.query(CollisionResult)
        if export_grade:
            query = query.filter(CollisionResult.certification_grade.in_(export_grade))
        if export_status != "Tous":
            query = query.filter(CollisionResult.status_qa == export_status)

        results = query.all()
        if results:
            rows = []
            for r in results:
                produit = db.query(ProduitReference).filter(ProduitReference.ean == r.ean).first()
                offre = db.query(OffreRetail).filter(OffreRetail.id == r.offre_id).first()
                rows.append({
                    "EAN": r.ean, "Produit": produit.nom_genere if produit else "N/A",
                    "Marque": produit.marque if produit else "N/A", "Enseigne": offre.enseigne if offre else "N/A",
                    "Prix Public": offre.prix_public if offre else 0, "Net-Net": r.prix_achat_net,
                    "Revente": r.prix_revente_estime, "Profit": r.profit_net_absolu,
                    "ROI %": r.roi_percent, "Grade": r.certification_grade, "Status": r.status_qa,
                })
            
            df = pd.DataFrame(rows)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label=f"\u2b07\ufe0f T\u00e9l\u00e9charger ({len(rows)} p\u00e9pites)",
                data=csv, file_name=f"pepites_b2b_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", mime="text/csv",
            )
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Aucune p\u00e9pite correspondant aux filtres.")
    finally:
        db.close()
