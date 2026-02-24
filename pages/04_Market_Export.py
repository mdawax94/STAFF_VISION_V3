"""
PAGE 4 — Market Export (B2B CSV Pipeline)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from core.models import SessionLocal, CollisionResult, ProduitReference

st.set_page_config(page_title="Market Export | Project COLLISION", page_icon="🛒", layout="wide")
st.markdown('<style>.stApp { background-color: #0d1117; color: #c9d1d9; font-family: "Inter", sans-serif; }</style>', unsafe_allow_html=True)
st.markdown("### 🛒 Market Export — B2B Data Pipeline")
st.caption("Filter certified opportunities and generate CSV exports for wholesale buyers.")

fc1, fc2, fc3 = st.columns([1, 1, 1])
with fc1: grade_filter = st.multiselect("Grade", ["A+", "A", "B", "C"], default=["A+", "A"])
with fc2: min_roi = st.slider("Min ROI %", 0, 100, 10)
with fc3: min_profit = st.number_input("Min Profit (EUR)", min_value=0.0, value=5.0, step=1.0)
st.divider()

db = SessionLocal()
try:
    query = db.query(CollisionResult).filter(CollisionResult.status_qa == "CERTIFIED", CollisionResult.roi_percent >= min_roi, CollisionResult.profit_net_absolu >= min_profit)
    if grade_filter: query = query.filter(CollisionResult.certification_grade.in_(grade_filter))
    results = query.order_by(CollisionResult.roi_percent.desc()).all()
    rows = []
    for r in results:
        prod = db.query(ProduitReference).filter(ProduitReference.ean == r.ean).first()
        rows.append({"EAN": r.ean, "Product": prod.nom_genere if prod else r.ean, "Brand": prod.marque if prod else "N/A", "Buy Price": r.prix_achat_net, "Sell Price": r.prix_revente_estime, "Fees": r.frais_plateforme, "Profit": r.profit_net_absolu, "ROI %": r.roi_percent, "Grade": r.certification_grade, "Date": r.timestamp.strftime("%Y-%m-%d") if r.timestamp else ""})
except Exception as e:
    st.error(f"Database error: {e}")
    rows = []
finally:
    db.close()

total = len(rows)
if total > 0:
    total_profit = sum(r["Profit"] for r in rows)
    avg_roi = sum(r["ROI %"] for r in rows) / total
    st.markdown(f"**{total} items** | **{total_profit:,.2f} EUR total profit** | **{avg_roi:.1f}% avg ROI**")
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, sep=";", encoding="utf-8")
    st.download_button(label="Download B2B CSV Export", data=csv_buffer.getvalue(), file_name=f"collision_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", mime="text/csv", use_container_width=True, type="primary")
else:
    st.info("No certified items match these filters.")
