"""
PAGE 2 — Minion Factory (Agent Fleet Control)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from datetime import datetime
from sqlalchemy.orm import joinedload
from core.models import SessionLocal, AgentConfig, DbTenant, JobQueue

st.set_page_config(page_title="Minion Factory | Project COLLISION", page_icon="🤖", layout="wide")
st.markdown('<style>.stApp { background-color: #0d1117; color: #c9d1d9; font-family: "Inter", sans-serif; } .agent-card { background: rgba(22,27,34,0.7); border: 1px solid #30363d; border-radius: 12px; padding: 20px; margin-bottom: 16px; }</style>', unsafe_allow_html=True)
st.markdown("### 🤖 Minion Factory")
st.caption("Manage your fleet of scraping agents.")

col_grid, col_form = st.columns([2, 1])
db = SessionLocal()
try:
    agents = db.query(AgentConfig).options(joinedload(AgentConfig.tenant)).order_by(AgentConfig.created_at.desc()).all()
    tenants = db.query(DbTenant).filter(DbTenant.is_active == True).all()
    agents_data = []
    for agent in agents:
        dot = "🟢" if agent.status == "RUNNING" else ("🔴" if agent.status == "ERROR" else "⚪")
        last_run_str = agent.last_run.strftime("%d/%m %H:%M") if agent.last_run else "Never"
        duration_str = f"{agent.last_run_duration_s:.1f}s" if agent.last_run_duration_s else "N/A"
        tenant_name = agent.tenant.name if agent.tenant else "Default"
        agents_data.append({"id": agent.id, "nom": agent.nom, "type": agent.type_agent, "url": agent.target_url, "dot": dot, "status": agent.status, "last_run": last_run_str, "duration": duration_str, "tenant_name": tenant_name})
    tenant_options_data = [{"id": t.id, "name": t.name} for t in tenants]
except Exception as e:
    st.error(f"Database error: {e}")
    agents_data, tenant_options_data = [], []
finally:
    db.close()

with col_grid:
    st.markdown("**Active Agents**")
    if not agents_data:
        st.info("No agents deployed yet.")
    else:
        for a in agents_data:
            st.markdown(f'<div class="agent-card"><div style="display:flex;justify-content:space-between;align-items:center;"><div><div style="font-size:17px;font-weight:700;color:#e6edf3;">{a["dot"]} {a["nom"]}</div><div style="font-size:12px;color:#8b949e;text-transform:uppercase;">{a["type"]} -> {a["tenant_name"]}</div></div><div style="text-align:right;"><div style="font-size:12px;color:#8b949e;">Last: {a["last_run"]}</div><div style="font-size:12px;color:#8b949e;">Duration: {a["duration"]}</div></div></div><div style="font-size:13px;color:#58a6ff;word-break:break-all;margin-top:8px;">{a["url"]}</div></div>', unsafe_allow_html=True)
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                if st.button("Start", key=f"start_{a['id']}", use_container_width=True):
                    db2 = SessionLocal()
                    try:
                        agent_obj = db2.query(AgentConfig).filter(AgentConfig.id == a['id']).first()
                        if agent_obj:
                            db2.add(JobQueue(task_type="SCOUT", target_id=str(a['id']), payload={"agent_config_id": a['id']}, priority=5))
                            agent_obj.status = "RUNNING"
                            db2.commit()
                    except Exception as e: st.error(str(e))
                    finally: db2.close()
                    st.rerun()
            with bc2:
                if st.button("Stop", key=f"stop_{a['id']}", use_container_width=True):
                    db2 = SessionLocal()
                    try:
                        agent_obj = db2.query(AgentConfig).filter(AgentConfig.id == a['id']).first()
                        if agent_obj: agent_obj.status = "IDLE"; agent_obj.is_active = False; db2.commit()
                    except Exception as e: st.error(str(e))
                    finally: db2.close()
                    st.rerun()
            with bc3:
                if st.button("Delete", key=f"del_{a['id']}", use_container_width=True):
                    db2 = SessionLocal()
                    try:
                        agent_obj = db2.query(AgentConfig).filter(AgentConfig.id == a['id']).first()
                        if agent_obj: db2.delete(agent_obj); db2.commit()
                    except Exception as e: st.error(str(e))
                    finally: db2.close()
                    st.rerun()

with col_form:
    st.markdown("**Deploy New Agent**")
    with st.form("create_agent_form"):
        agent_name = st.text_input("Agent Name", placeholder="Scout Carrefour Promos")
        agent_type = st.selectbox("Type", ["CATALOGUE", "COUPON", "ODR", "FIDELITE", "TC"])
        target_url = st.text_input("Target URL", placeholder="https://carrefour.fr/promos")
        cron_rule = st.text_input("Schedule (cron)", value="manual")
        tenant_opts = {None: "Default (Main)"}
        for t in tenant_options_data: tenant_opts[t["id"]] = t["name"]
        selected_tenant = st.selectbox("Target Database", options=list(tenant_opts.keys()), format_func=lambda x: tenant_opts[x])
        submitted = st.form_submit_button("Deploy Agent", use_container_width=True, type="primary")
        if submitted and agent_name and target_url:
            db2 = SessionLocal()
            try:
                db2.add(AgentConfig(nom=agent_name, type_agent=agent_type, target_url=target_url, frequence_cron=cron_rule, tenant_id=selected_tenant))
                db2.commit()
            except Exception as e: st.error(str(e))
            finally: db2.close()
            st.rerun()
