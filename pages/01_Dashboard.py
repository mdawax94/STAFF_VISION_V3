"""
PAGE 1 — Dashboard (The Bird's Eye View)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import func
from core.models import (
    SessionLocal, ProduitReference, OffreRetail,
    LevierActif, CollisionResult, JobQueue, SystemEventLog
)

st.set_page_config(page_title="Dashboard | Project COLLISION", page_icon="🏠", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #c9d1d9; font-family: 'Inter', sans-serif; }
    .kpi-card { background: rgba(22, 27, 34, 0.6); border: 1px solid #30363d; border-radius: 12px; padding: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.2); }
    .kpi-label { font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; margin-bottom: 8px; }
    .kpi-value { font-size: 42px; font-weight: 800; color: #ffffff; line-height: 1.1; }
    .panel-box { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; }
    .status-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
    .status-healthy { background-color: #3fb950; box-shadow: 0 0 8px #3fb950; }
    .status-warning { background-color: #d29922; box-shadow: 0 0 8px #d29922; }
    .status-critical { background-color: #f85149; box-shadow: 0 0 8px #f85149; }
    .pepite-item { background: rgba(13,17,23,0.8); border: 1px solid #30363d; border-left: 4px solid #a371f7; padding: 16px; border-radius: 8px; margin-bottom: 12px; }
    .terminal-log { font-family: monospace; font-size: 12px; background: #0d1117; padding: 10px; border-radius: 6px; border: 1px solid #30363d; max-height: 250px; overflow-y: auto; }
    .log-line { margin-bottom: 4px; }
</style>
""", unsafe_allow_html=True)

st.markdown("### 🏠 STAFF v3 — Project COLLISION Dashboard")
st.caption("Real-time Operations Dashboard & Analytics Hub")

db = SessionLocal()
try:
    total_offres = db.query(OffreRetail).filter(OffreRetail.is_active == True).count()
    total_leviers = db.query(LevierActif).filter(LevierActif.is_active == True).count()
    total_certifiees = db.query(CollisionResult).filter(CollisionResult.status_qa == "CERTIFIED").count()
    total_profit_est = db.query(func.sum(CollisionResult.profit_net_absolu)).filter(CollisionResult.status_qa == "CERTIFIED").scalar() or 0.0
    total_qa = db.query(CollisionResult).filter(CollisionResult.status_qa.in_(["CERTIFIED", "REJECTED"])).count()
    success_rate = (total_certifiees / total_qa * 100) if total_qa > 0 else 0.0
    jobs_pending = db.query(JobQueue).filter(JobQueue.status == "PENDING").count()
    jobs_running = db.query(JobQueue).filter(JobQueue.status == "RUNNING").count()
    jobs_failed = db.query(JobQueue).filter(JobQueue.status == "FAILED").count()
    recent_events = db.query(SystemEventLog).order_by(SystemEventLog.timestamp.desc()).limit(15).all()
    top_pepites = db.query(CollisionResult).filter(CollisionResult.status_qa == "CERTIFIED", CollisionResult.certification_grade.in_(["A+", "A"])).order_by(CollisionResult.roi_percent.desc()).limit(4).all()
    pepite_display = []
    for pep in top_pepites:
        prod = db.query(ProduitReference).filter(ProduitReference.ean == pep.ean).first()
        nom = prod.nom_genere if prod else f"EAN: {pep.ean}"
        if len(nom) > 35: nom = nom[:32] + "..."
        pepite_display.append({"nom": nom, "grade": pep.certification_grade, "profit": pep.profit_net_absolu, "roi": pep.roi_percent})
    log_entries = [{"time": ev.timestamp.strftime('%H:%M:%S') if ev.timestamp else "", "severity": ev.severity, "message": ev.message} for ev in recent_events]
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()
finally:
    db.close()

col1, col2, col3, col4 = st.columns(4)
with col1: st.markdown(f'<div class="kpi-card"><div class="kpi-label">🎯 Success Rate</div><div class="kpi-value">{success_rate:.1f}%</div></div>', unsafe_allow_html=True)
with col2: st.markdown(f'<div class="kpi-card"><div class="kpi-label">💎 Pepites Certifiees</div><div class="kpi-value">{total_certifiees}</div></div>', unsafe_allow_html=True)
with col3: st.markdown(f'<div class="kpi-card"><div class="kpi-label">📦 Offres Actives</div><div class="kpi-value">{total_offres}</div></div>', unsafe_allow_html=True)
with col4: st.markdown(f'<div class="kpi-card"><div class="kpi-label">💰 Profit Locked</div><div class="kpi-value" style="color:#58a6ff;">{total_profit_est:,.0f} €</div></div>', unsafe_allow_html=True)

col_left, col_right = st.columns([1.5, 1])
with col_left:
    st.markdown("#### 🛡️ JobQueue Conductor")
    status_class = "status-healthy"
    status_text = "Operational"
    if jobs_failed > 0: status_class, status_text = "status-warning", "Degraded"
    if jobs_failed > 10: status_class, status_text = "status-critical", "Critical"
    st.markdown(f'<div class="panel-box" style="margin-bottom:20px;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;border-bottom:1px solid #30363d;padding-bottom:12px;"><div style="font-weight:600;font-size:16px;">System Health</div><div><span class="status-indicator {status_class}"></span><span style="color:#8b949e;font-size:13px;">{status_text}</span></div></div><div style="display:flex;gap:40px;"><div><div style="color:#8b949e;font-size:12px;">Pending</div><div style="font-size:22px;font-weight:600;">{jobs_pending}</div></div><div><div style="color:#58a6ff;font-size:12px;">Running</div><div style="font-size:22px;font-weight:600;">{jobs_running}</div></div><div><div style="color:#f85149;font-size:12px;">Failed</div><div style="font-size:22px;font-weight:600;">{jobs_failed}</div></div></div></div>', unsafe_allow_html=True)
    st.caption("Terminal Logs")
    logs_html = ""
    for entry in log_entries:
        color = "#f85149" if entry["severity"] in ["ERROR","CRITICAL"] else ("#d29922" if entry["severity"] == "WARNING" else "#58a6ff")
        logs_html += f"<div class='log-line'><span style='color:#8b949e;margin-right:8px;'>[{entry['time']}]</span><span style='color:{color};'>[{entry['severity']}]</span> {entry['message']}</div>"
    if not logs_html: logs_html = "<div class='log-line' style='color:#484f58;'>System idle. Awaiting jobs...</div>"
    st.markdown(f"<div class='terminal-log'>{logs_html}</div>", unsafe_allow_html=True)

with col_right:
    st.markdown("#### 💎 Top A+ Pepites")
    if pepite_display:
        for p in pepite_display:
            st.markdown(f'<div class="pepite-item"><div style="font-weight:600;font-size:15px;color:#e6edf3;">{p["nom"]}</div><div style="font-size:13px;color:#8b949e;">Grade <span style="color:#a371f7;">{p["grade"]}</span> | Profit: <strong>{p["profit"]}€</strong> | <span style="color:#3fb950;font-weight:700;">ROI: {p["roi"]}%</span></div></div>', unsafe_allow_html=True)
    else:
        st.info("Aucune pepite A/A+ certifiee. Rendez-vous au QA Lab !")
