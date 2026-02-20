import streamlit as st
import pandas as pd
from datetime import datetime
from core.models import SessionLocal, Source
from agents.flyer_capture import capture_page
from agents.vision_analyzer import analyze_image

st.set_page_config(page_title="Sources & Scheduler", layout="wide")

def add_source(url, levier, frequence):
    session = SessionLocal()
    new_source = Source(url=url, levier=levier, frequence=frequence)
    session.add(new_source)
    session.commit()
    session.close()

def run_agent_pipeline(source_id, url):
    session = SessionLocal()
    src = session.query(Source).filter(Source.id == source_id).first()
    if not src:
        session.close()
        return
    
    try:
        src.status = "SCRAPING..."
        session.commit()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_name = f"capture_{src.id}_{timestamp}.png"
        
        if capture_page(url, screenshot_name):
            src.status = "ANALYZING..."
            session.commit()
            
            from core.config import TEMP_FLYERS_DIR
            image_path = TEMP_FLYERS_DIR / screenshot_name
            products = analyze_image(str(image_path))
            
            # Sauvegarde des produits bruts
            from core.models import ProduitBrut
            for p in products:
                new_prod = ProduitBrut(
                    source_id=src.id,
                    image_path=str(image_path),
                    marque=p.get("brand"),
                    produit=p.get("product_name"),
                    prix_catalogue=p.get("original_price"),
                    remise=p.get("discount_amount"),
                    prix_net_net=p.get("final_net_price"),
                    levier_type=src.levier,
                    status="PENDING"
                )
                session.add(new_prod)
            
            src.status = "DONE"
            src.last_scan = datetime.now()
        else:
            src.status = "FAILED"
    except Exception as e:
        st.error(f"Erreur: {e}")
        src.status = "ERROR"
    finally:
        session.commit()
        session.close()

st.title("🔗 Sources & Scheduler")

# Formulaire d'ajout
with st.expander("➕ Ajouter une nouvelle source", expanded=True):
    with st.form("new_source_form"):
        col1, col2, col3 = st.columns(3)
        url = col1.text_input("URL du catalogue / page")
        levier = col2.selectbox("Levier", ["Catalogues", "Coupons", "ODR"])
        frequence = col3.selectbox("Fréquence (Jours)", [1, 2, 5, 7])
        submit = st.form_submit_button("Sauvegarder la Source")
        
        if submit and url:
            add_source(url, levier, frequence)
            st.success("Source ajoutée avec succès !")

# Liste des Sources
st.subheader("📋 Sources configurées")
session = SessionLocal()
sources = session.query(Source).all()
session.close()

if sources:
    df = pd.DataFrame([{
        "ID": s.id,
        "URL": s.url,
        "Levier": s.levier,
        "Fréquence": f"{s.frequence}j",
        "Dernier Scan": s.last_scan,
        "Statut": s.status
    } for s in sources])
    
    for _, row in df.iterrows():
        cols = st.columns([1, 4, 2, 1, 2, 2, 2])
        cols[0].write(row["ID"])
        cols[1].write(row["URL"])
        cols[2].write(row["Levier"])
        cols[3].write(row["Fréquence"])
        cols[4].write(row["Dernier Scan"])
        
        # Badge de statut
        status = row["Statut"]
        color = "blue" if "..." in status else "green" if status == "DONE" else "gray"
        cols[5].markdown(f":{color}[**{status}**]")
        
        if cols[6].button("RUN NOW", key=f"run_{row['ID']}"):
            run_agent_pipeline(row["ID"], row["URL"])
            st.rerun()
else:
    st.info("Aucune source configurée.")
