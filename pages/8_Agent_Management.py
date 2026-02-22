"""
PAGE 8 — Agent Management Center (The Minion Factory)
Interface Streamlit pour instancier, piloter et monitorer les Agents.
"""
import streamlit as st
import asyncio
from datetime import datetime
from core.models import AgentConfig, ApiKey, GlobalSettings, SessionLocal

st.set_page_config(page_title="🤖 Agent Management Center", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    .agent-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
    }
    .agent-card h3 { color: #e94560; margin: 0 0 8px 0; }
    .status-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }
    .status-idle { background: #1b4332; color: #95d5b2; }
    .status-running { background: #3a2d0a; color: #ffd60a; }
    .status-error { background: #3d0000; color: #ff6b6b; }
    .key-pool { background: #1a1a2e; border: 1px solid #30475e; border-radius: 8px; padding: 12px; margin: 4px 0; }
    .metric-box { background: #16213e; border-radius: 10px; padding: 16px; text-align: center; }
    .metric-box h2 { color: #e94560; margin: 0; font-size: 36px; }
    .metric-box p { color: #a0aec0; margin: 4px 0 0 0; font-size: 14px; }
</style>
""", unsafe_allow_html=True)

def get_status_badge(status: str) -> str:
    status_map = {
        "IDLE": ("status-idle", "⏸️ En attente"),
        "RUNNING": ("status-running", "🔄 En cours"),
        "ERROR": ("status-error", "❌ Erreur"),
    }
    css_class, label = status_map.get(status, ("status-idle", status))
    return f'<span class="status-badge {css_class}">{label}</span>'

st.markdown("# 🤖 Agent Management Center")
st.markdown("*The Minion Factory \u2014 Instancie et pilote tes agents d'extraction.*")
st.markdown("---")

db = SessionLocal()
try:
    all_agents = db.query(AgentConfig).all()
    active_count = sum(1 for a in all_agents if a.is_active)
    running_count = sum(1 for a in all_agents if a.status == "RUNNING")
    error_count = sum(1 for a in all_agents if a.status == "ERROR")
    total_keys = db.query(ApiKey).count()
    active_keys = db.query(ApiKey).filter(ApiKey.is_active == True).count()
finally:
    db.close()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f'<div class="metric-box"><h2>{len(all_agents)}</h2><p>Agents Total</p></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="metric-box"><h2>{active_count}</h2><p>Actifs</p></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="metric-box"><h2>{running_count}</h2><p>En cours</p></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="metric-box"><h2>{active_keys}/{total_keys}</h2><p>Cl\u00e9s API OK</p></div>', unsafe_allow_html=True)

st.markdown("---")

st.markdown("## \u2795 Cr\u00e9er un Agent")

with st.expander("Nouveau Minion", expanded=False):
    col_a, col_b = st.columns(2)
    with col_a:
        agent_nom = st.text_input("Nom de l'agent", placeholder="Scout Carrefour Catalogue Q1")
        agent_url = st.text_input("URL Cible", placeholder="https://www.carrefour.fr/promotions")
    with col_b:
        agent_type = st.selectbox("Type d'agent", ["CATALOGUE", "COUPON", "ODR", "FIDELITE", "TC", "EAN_PIVOT"])
        agent_freq = st.selectbox("Fr\u00e9quence", ["manual", "0 6 * * *", "0 6 * * 1", "0 */6 * * *", "0 0 * * *"])

    if st.button("\ud83d\ude80 Cr\u00e9er l'Agent", type="primary"):
        if agent_nom and agent_url:
            db = SessionLocal()
            try:
                new_agent = AgentConfig(
                    nom=agent_nom, type_agent=agent_type, target_url=agent_url, frequence_cron=agent_freq
                )
                db.add(new_agent)
                db.commit()
                st.success(f"\u2705 Agent '{agent_nom}' cr\u00e9\u00e9 avec succ\u00e8s !")
                st.rerun()
            except Exception as e:
                st.error(f"Erreur: {e}")
                db.rollback()
            finally:
                db.close()
        else:
            st.warning("Remplis tous les champs obligatoires.")

st.markdown("---")

st.markdown("## \ud83d\uddc2\ufe0f Flotte des Agents")

db = SessionLocal()
try:
    agents = db.query(AgentConfig).order_by(AgentConfig.created_at.desc()).all()
    if not agents:
        st.info("Aucun agent cr\u00e9\u00e9. Utilise le formulaire ci-dessus pour instancier ton premier Minion.")
    
    for agent in agents:
        with st.container():
            st.markdown(f"""
            <div class="agent-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h3>\ud83e\udd16 {agent.nom}</h3>
                        <p style="color: #a0aec0; margin: 0;">
                            <strong>Type:</strong> {agent.type_agent} &nbsp;|&nbsp;
                            <strong>Fr\u00e9quence:</strong> {agent.frequence_cron} &nbsp;|&nbsp;
                            {get_status_badge(agent.status)}
                        </p>
                        <p style="color: #718096; font-size: 12px; margin: 4px 0;">
                            \ud83d\udcce <code>{agent.target_url}</code>
                        </p>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            col_run, col_pause, col_del, col_info = st.columns([1, 1, 1, 2])

            with col_run:
                if st.button("\u25b6\ufe0f Lancer", key=f"run_{agent.id}", disabled=agent.status == "RUNNING"):
                    st.info(f"Lancement de l'agent {agent.nom}... (Mode async)")
                    agent_db = db.query(AgentConfig).filter(AgentConfig.id == agent.id).first()
                    if agent_db:
                        agent_db.status = "RUNNING"
                        agent_db.last_run = datetime.utcnow()
                        db.commit()
                    st.rerun()

            with col_pause:
                toggle_label = "\u23f8\ufe0f D\u00e9sactiver" if agent.is_active else "\u25b6\ufe0f Activer"
                if st.button(toggle_label, key=f"toggle_{agent.id}"):
                    agent_db = db.query(AgentConfig).filter(AgentConfig.id == agent.id).first()
                    if agent_db:
                        agent_db.is_active = not agent_db.is_active
                        db.commit()
                    st.rerun()

            with col_del:
                if st.button("\ud83d\uddd1\ufe0f Supprimer", key=f"del_{agent.id}"):
                    agent_db = db.query(AgentConfig).filter(AgentConfig.id == agent.id).first()
                    if agent_db:
                        db.delete(agent_db)
                        db.commit()
                    st.rerun()

            with col_info:
                if agent.error_message:
                    st.error(f"Derni\u00e8re erreur: {agent.error_message[:100]}")
                elif agent.last_run:
                    st.caption(f"Dernier run: {agent.last_run.strftime('%d/%m/%Y %H:%M')}")
                    if agent.last_run_duration_s:
                        st.caption(f"Dur\u00e9e: {agent.last_run_duration_s}s")
            st.markdown("---")
finally:
    db.close()

st.markdown("## \ud83d\udd11 Pool de Cl\u00e9s API")

with st.expander("Ajouter une cl\u00e9 API", expanded=False):
    col_k1, col_k2 = st.columns(2)
    with col_k1:
        key_service = st.selectbox("Service", ["gemini", "scrapingbee", "keepa", "rainforest", "serpapi"])
    with col_k2:
        key_value = st.text_input("Valeur de la cl\u00e9", type="password")

    if st.button("\u2795 Ajouter la cl\u00e9"):
        if key_value:
            from core.credential_manager import CredentialManager
            cm = CredentialManager(service_name=key_service)
            added = cm.add_key(key_value)
            if added:
                st.success(f"\u2705 Cl\u00e9 ajout\u00e9e pour {key_service}")
            else:
                st.warning("Cl\u00e9 d\u00e9j\u00e0 existante.")
            st.rerun()

db = SessionLocal()
try:
    all_keys = db.query(ApiKey).order_by(ApiKey.service).all()
    if all_keys:
        for key in all_keys:
            status_emoji = "\ud83d\udfe2" if key.is_active else "\ud83d\udd34"
            preview = f"{key.key_value[:8]}...{key.key_value[-4:]}" if len(key.key_value) > 12 else "***"
            st.markdown(f"""
            <div class="key-pool">
                {status_emoji} <strong>{key.service.upper()}</strong> \u2014 
                <code>{preview}</code> \u2014 
                Erreurs: {key.error_count} \u2014 
                {'Active' if key.is_active else 'En cooldown'}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("Aucune cl\u00e9 API enregistr\u00e9e. Ajoute tes cl\u00e9s Gemini et autres ci-dessus.")
finally:
    db.close()
