import argparse
import logging
import json
import csv
import os
from datetime import datetime
from agents.flyer_capture import capture_page
from agents.vision_analyzer import analyze_image
from agents.reliability_engine import get_market_price, calculate_arbitrage
from core.models import engine, Base, SessionLocal, Arbitrage
from core.config import DATA_DIR, TEMP_FLYERS_DIR

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def init_system():
    """Initialise la base de données au démarrage."""
    logger.info("Initialisation du système STAFF_VISION...")
    Base.metadata.create_all(bind=engine)

def run_arbitrage(url: str):
    """
    Orchestre le workflow complet : Capture -> Vision -> Reliability -> SQL -> Export.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_name = f"capture_{timestamp}.png"
    screenshot_path = TEMP_FLYERS_DIR / screenshot_name
    
    # ÉTAPE 1 : Capture par l'Agent Scout
    logger.info("--- ÉTAPE 1 : CAPTURE ---")
    if not capture_page(url, screenshot_name):
        logger.error("Échec de la capture du catalogue. Arrêt.")
        return

    # ÉTAPE 2 : Analyse par l'Agent Visionnaire
    logger.info("--- ÉTAPE 2 : ANALYSE VISION ---")
    found_products = analyze_image(str(screenshot_path))
    
    if not found_products:
        logger.warning("Aucun produit extrait du catalogue.")
        # Nettoyage si aucune donnée
        if screenshot_path.exists():
            os.remove(screenshot_path)
        return

    logger.info(f"{len(found_products)} produits trouvés. Passage au Juge...")

    # ÉTAPE 3 : Validation par l'Agent Juge et Sauvegarde
    logger.info("--- ÉTAPE 3 : JUGEMENT ET PERSISTENCE ---")
    session = SessionLocal()
    saved_data = [] # Pour l'export CSV
    pepites = [] # Pour le rapport final
    
    try:
        for p in found_products:
            name = p.get("product_name")
            buy_price = p.get("final_net_price")
            vision_score = p.get("reliability_score") or 0
            
            if not name or buy_price is None:
                continue
                
            # Appel du Juge pour les prix de marché
            market_data = get_market_price(name)
            if not market_data:
                continue
                
            # Calcul d'arbitrage
            decision = calculate_arbitrage(
                purchase_price=buy_price,
                market_data=market_data,
                vision_score=vision_score,
                original_name=name
            )
            
            # Score de Fiabilité Global
            similarity_score = decision.get("similarity_score", 0)
            global_reliability = (vision_score + similarity_score) / 2
            
            # Seuil de persistence : Score Global > 50
            if global_reliability > 50:
                new_entry = Arbitrage(
                    produit=name,
                    prix_achat_net=float(buy_price),
                    prix_revente=float(decision["market_price"]),
                    marge=float(decision["potential_profit"]),
                    fiabilite=int(global_reliability),
                    image_preuve=str(screenshot_path),
                    details_promo=json.dumps({
                        "vision_data": p,
                        "market_data": decision
                    })
                )
                session.add(new_entry)
                
                # Buffer pour CSV
                saved_data.append({
                    "Timestamp": timestamp,
                    "Produit": name,
                    "Prix Achat Net": buy_price,
                    "Prix Revente": decision["market_price"],
                    "Profit": decision["potential_profit"],
                    "Marge %": decision["margin_percentage"],
                    "Fiabilite": global_reliability,
                    "Image": str(screenshot_path)
                })

                # Détection Pépites: Marge > 20% ET Fiabilité > 80
                if decision["margin_percentage"] > 20 and global_reliability > 80:
                    pepites.append({
                        "name": name,
                        "profit": decision["potential_profit"],
                        "image": str(screenshot_path)
                    })
        
        session.commit()
        
        # ÉTAPE 4 : EXPORT CSV
        if saved_data:
            csv_file = DATA_DIR / f"scan_export_{timestamp}.csv"
            keys = saved_data[0].keys()
            with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=keys, delimiter=";")
                writer.writeheader()
                writer.writerows(saved_data)
            logger.info(f"Export CSV créé : {csv_file}")

        # RAPPORT FINAL
        logger.info("--- RAPPORT FINAL STAFF_VISION ---")
        logger.info(f"Produits analysés : {len(found_products)}")
        logger.info(f"Opportunités enregistrées (Score > 50) : {len(saved_data)}")
        
        if pepites:
            print("\n" + "="*40)
            print("🚀 PÉPITES DÉTECTÉES")
            print("="*40)
            for pep in pepites:
                print(f"💎 PROD: {pep['name']}")
                print(f"💰 MARGE NETTE: {pep['profit']}€")
                print(f"📸 PREUVE: {pep['image']}")
                print("-" * 20)
            print("="*40 + "\n")
        else:
            logger.info("Aucune pépite détectée (Marge > 20% & Fiabilité > 80).")

        # ÉTAPE 5 : NETTOYAGE SÉCURISÉ
        # On supprime l'image seulement si aucune pépite n'est présente
        if not pepites and screenshot_path.exists():
            try:
                os.remove(screenshot_path)
                logger.info(f"Nettoyage : Image temporaire supprimée ({screenshot_name})")
            except Exception as e:
                logger.warning(f"Erreur lors de la suppression de l'image : {e}")
        elif pepites:
            logger.info(f"Image de preuve conservée pour les pépites : {screenshot_path}")

    except Exception as e:
        logger.error(f"Erreur durant l'orchestration : {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="STAFF_VISION - Orchestrateur d'Arbitrage Retail")
    parser.add_argument("--url", type=str, required=True, help="URL du catalogue à analyser")
    
    args = parser.parse_args()
    
    init_system()
    run_arbitrage(args.url)
