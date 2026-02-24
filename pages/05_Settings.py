"""
PAGE 5 — Settings (System Administration)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from datetime import datetime
from core.models import SessionLocal, DbTenant, ApiKey, SystemEventLog

st.set_page_config(page_title="Settings | Project COLLISION", page_icon="⚙️", layout="wide")
st.markdown('<style>.stApp { background-color: #0d1117; color: #c9d1d9; font-family: "Inter", sans-serif; } .terminal-log { font-family: monospace; font-size: 12px; background: #0d1117; padding: 12px; border-radius: 8px; border: 1px solid #30363d; max-height: 300px; overflow-y: auto; } .log-line { margin-bottom: 3px; }</style>', unsafe_allow_html=True)
st.markdown("### Settings & Logs")
st.caption("Manage database tenants, API key pool, and monitor system events.")

db = SessionLocal()
try:
    tenants = db.query(DbTenant).order_by(DbTenant.created_at.desc()).all()
    tenants_data = [{"id": t.id, "name": t.name, "masked": t.connection_string[:25] + "..." if len(t.connection_string) > 25 else t.connection_string, "active": t.is_active} for t in tenants]
    keys = db.query(ApiKey).order_by(ApiKey.service, ApiKey.created_at.desc()).all()
    now = datetime.utcnow()
    keys_data = []
    for k in keys:
        masked_key = k.key_value[:8] + "..." + k.key_value[-4:] if len(k.key_value) > 12 else "***"
        if k.cooldown_until and k.cooldown_until > now: status, icon = f"Cooldown ({int((k.cooldown_until - now).total_seconds() / 60)}m)", "🟡"
        elif k.is_active: status, icon = "Active", "🟢"
        else: status, icon = "Disabled", "🔴"
        keys_data.append({"service": k.service.upper(), "masked": masked_key, "status": status, "icon": icon, "errors": k.error_count})
    events = db.query(SystemEventLog).order_by(SystemEventLog.timestamp.desc()).limit(30).all()
    log_entries = [{"time": ev.timestamp.strftime('%Y-%m-%d %H:%M:%S') if ev.timestamp else "", "severity": ev.severity, "type": ev.event_type, "message": ev.message} for ev in events]
except Exception as e:
    st.error(f"Database error: {e}")
    tenants_data, keys_data, log_entries = [], [], []
finally:
    db.close()

col_tenants, col_keys = st.columns(2)
with col_tenants:
    st.markdown("#### Database Tenants")
    if tenants_data:
        for t in tenants_data:
            st.markdown(f"{'\U0001f7e2' if t['active'] else '\U0001f534'} **{t['name']}** - `{t['masked']}`")
            if st.button(f"Remove '{t['name']}'", key=f"del_tenant_{t['id']}"):
                db2 = SessionLocal()
                try:
                    obj = db2.query(DbTenant).filter(DbTenant.id == t["id"]).first()
                    if obj: db2.delete(obj); db2.commit()
                except Exception as e: st.error(str(e))
                finally: db2.close()
                st.rerun()
    else: st.caption("No tenants configured.")
    with st.expander("Add New Database Tenant"):
        with st.form("add_tenant"):
            t_name = st.text_input("Tenant Name", placeholder="Client B")
            t_conn = st.text_input("Connection String", placeholder="postgresql://user:pass@host:5432/db", type="password")
            if st.form_submit_button("Save Tenant", use_container_width=True, type="primary"):
                if t_name and t_conn:
                    db2 = SessionLocal()
                    try: db2.add(DbTenant(name=t_name, connection_string=t_conn, is_active=True)); db2.commit()
                    except Exception as e: st.error(str(e))
                    finally: db2.close()
                    st.rerun()
                else: st.warning("Both fields are required.")

with col_keys:
    st.markdown("#### API Key Pool")
    if keys_data:
        for k in keys_data: st.markdown(f"{k['icon']} **{k['service']}** - `{k['masked']}` - {k['status']} (Errors: {k['errors']})")
    else: st.caption("No API keys registered.")
    with st.expander("Register New API Key"):
        with st.form("add_key"):
            k_service = st.selectbox("Service", ["gemini", "scrapingbee", "serpapi", "keepa", "rainforest"])
            k_value = st.text_input("API Key Value", type="password")
            if st.form_submit_button("Save Key", use_container_width=True, type="primary"):
                if k_value:
                    db2 = SessionLocal()
                    try: db2.add(ApiKey(service=k_service, key_value=k_value, is_active=True)); db2.commit()
                    except Exception as e: st.error(str(e))
                    finally: db2.close()
                    st.rerun()
                else: st.warning("Key value is required.")

st.divider()
st.markdown("#### System Event Logs")
logs_html = ""
if log_entries:
    for entry in log_entries:
        color = "#f85149" if entry["severity"] in ["ERROR", "CRITICAL"] else ("#d29922" if entry["severity"] == "WARNING" else "#58a6ff")
        logs_html += f"<div class='log-line'><span style='color:#8b949e;margin-right:8px;'>[{entry['time']}]</span><span style='color:{color};'>[{entry['severity']}]</span> {entry['type']} - {entry['message']}</div>"
else: logs_html = "<div class='log-line' style='color:#484f58;'>No events recorded.</div>"
st.markdown(f"<div class='terminal-log'>{logs_html}</div>", unsafe_allow_html=True)
