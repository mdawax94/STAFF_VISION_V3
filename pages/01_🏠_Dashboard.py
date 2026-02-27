"""
PAGE 1 — Dashboard / Vue Macro (B2B SaaS)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from sqlalchemy import func
from core.models import SessionLocal, OffreRetail, MissionConfig, ApiKey

st.set_page_config(page_title="Dashboard | STAFF v3", page_icon="📈", layout="wide")

st.markdown("### 📈 Dashboard Direction (B2B SaaS)")
st.caption("Vue macroscopique sur l'état de l'extraction, la conformité QA et le rendement d'Arbitrage.")

db = SessionLocal()
try:
    total_published = db.query(OffreRetail).filter(OffreRetail.qa_status == "PUBLISHED").count()
    active_missions = db.query(MissionConfig).filter(MissionConfig.is_active == True).count()
    
    avg_conf_query = db.query(func.avg(OffreRetail.reliability_score)).filter(
        OffreRetail.qa_status.in_(["VALIDATED", "PUBLISHED"])
    ).scalar()
    avg_confidence = (avg_conf_query * 100) if avg_conf_query else 0.0

    marges = db.query(
        OffreRetail.prix_revente_marche - OffreRetail.prix_net_net_calcule
    ).filter(
        OffreRetail.qa_status == "PUBLISHED",
        OffreRetail.prix_revente_marche.isnot(None),
        OffreRetail.prix_net_net_calcule.isnot(None)
    ).all()
    avg_marge = sum(m[0] for m in marges) / len(marges) if marges else 0.0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric(label="🟢 Pépites Certifiées", value=total_published, delta="Prêtes B2B")
    with kpi2:
        st.metric(label="⏱️ Missions Actives", value=active_missions, delta="Bots en cours")
    with kpi3:
        st.metric(label="🛡️ Indice de Confiance QA", value=f"{avg_confidence:.1f} %")
    with kpi4:
        st.metric(label="💰 Marge Potentielle Moyenne", value=f"{avg_marge:.2f} €")

    st.markdown("---")

    exhausted_keys = db.query(ApiKey).filter(ApiKey.status == "EXHAUSTED").all()
    if exhausted_keys:
        services_exhausted = set([k.service_name for k in exhausted_keys])
        st.error(
            f"🚨 **ALERTE SYSTÈME : quotas API dépassés !**  \n"
            f"Des clés sont épuisées pour les services suivants : **{', '.join(services_exhausted)}**. "
            "Les bots liés sont potentiellement aveugles. Renouvelez vos quotas dans la Page 05 (Settings)."
        )

    erreurs = db.query(OffreRetail).filter(OffreRetail.qa_status == "ERROR").count()
    doutes = db.query(OffreRetail).filter(OffreRetail.qa_status == "FLAGGED").count()
    
    if erreurs > 0 or doutes > 0:
        c1, c2 = st.columns([3, 1])
        with c1:
            if erreurs > 0:
                st.error(f"🛑 **Centre de Triage : {erreurs} offres en ERREUR FATALE !** Une intervention humaine est requise.")
            if doutes > 0:
                st.warning(f"⚠️ **Centre de Triage : {doutes} offres marquées pour DOUTE.** Confirmez les valeurs (IA suspecte).")
        with c2:
            st.info("💡 Résolvez ces anomalies dans le **QA Lab (Page 3)**.")

    st.markdown("<br>", unsafe_allow_html=True)

    st.subheader("📊 Graphiques de Répartition")
    
    g1, g2 = st.columns(2)
    
    with g1:
        st.markdown("**Répartition des Offres par Enseigne** (Toutes offres non-erreur)")
        enseignes_data = db.query(
            OffreRetail.enseigne, func.count(OffreRetail.id)
        ).filter(
            OffreRetail.qa_status != "ERROR"
        ).group_by(OffreRetail.enseigne).all()

        if enseignes_data:
            df_enseignes = pd.DataFrame(enseignes_data, columns=["Enseigne", "Nombre d'offres"])
            df_enseignes.set_index("Enseigne", inplace=True)
            st.bar_chart(df_enseignes)
        else:
            st.caption("Données insuffisantes.")

    with g2:
        st.markdown("**Typologie des Promos** (Toutes offres non-erreur)")
        has_remise_imm = db.query(OffreRetail).filter(OffreRetail.remise_immediate > 0, OffreRetail.qa_status != "ERROR").count()
        has_coupon = db.query(OffreRetail).filter(OffreRetail.valeur_coupon > 0, OffreRetail.qa_status != "ERROR").count()
        has_odr = db.query(OffreRetail).filter(OffreRetail.valeur_odr > 0, OffreRetail.qa_status != "ERROR").count()
        
        df_promos = pd.DataFrame({
            "Type": ["Remise Immédiate", "Coupon Ligne", "ODR"],
            "Quantité": [has_remise_imm, has_coupon, has_odr]
        })
        if has_remise_imm > 0 or has_coupon > 0 or has_odr > 0:
            df_promos.set_index("Type", inplace=True)
            st.bar_chart(df_promos)
        else:
            st.caption("Aucune promotion extraite pour l'instant.")

except Exception as e:
    st.error(f"Erreur de chargement du Dashboard: {e}")
finally:
    db.close()
