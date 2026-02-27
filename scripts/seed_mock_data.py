"""
SEED SCRIPT — Injection de données factices réalistes pour le Crash-Test UI/UX V5.
Fonctionne avec SQLite ET PostgreSQL. Ne touche PAS aux clés API existantes.
Usage: python scripts/seed_mock_data.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timedelta
import random

from core.models import (
    SessionLocal, init_db,
    ProduitReference, MissionConfig, MissionLog,
    OffreRetail, PriceHistory
)

PRODUCTS = [
    {"ean": "3145891345123", "nom_genere": "Aspirateur Dyson V15 Detect Absolute", "marque": "Dyson", "categorie": "Electroménager"},
    {"ean": "8710103987154", "nom_genere": "Philips Hue White & Color Ambiance Kit E27", "marque": "Philips", "categorie": "High-Tech"},
    {"ean": "5025155027581", "nom_genere": "Lego Star Wars Faucon Millenium 75192", "marque": "Lego", "categorie": "Jouets"},
    {"ean": "4005900543669", "nom_genere": "Nivea Crème Soin de Jour 50ml", "marque": "Nivea", "categorie": "Beauté"},
    {"ean": "3017620422003", "nom_genere": "Nutella Pâte à Tartiner 1kg", "marque": "Ferrero", "categorie": "Alimentaire"},
    {"ean": "0194252020861", "nom_genere": "Apple MacBook Air M1 256Go", "marque": "Apple", "categorie": "High-Tech"},
    {"ean": "0045496420597", "nom_genere": "Nintendo Switch OLED Blanche", "marque": "Nintendo", "categorie": "Gaming"},
    {"ean": "8806090623696", "nom_genere": "Samsung Galaxy S21 Ultra 5G 128Go", "marque": "Samsung", "categorie": "Smartphones"},
    {"ean": "4006501115206", "nom_genere": "Krups Essential Machine à Café EA81", "marque": "Krups", "categorie": "Electroménager"},
    {"ean": "3165140810757", "nom_genere": "Perceuse Visseuse Bosch Professional 18V", "marque": "Bosch", "categorie": "Bricolage"},
]

ENSEIGNES = ["Carrefour", "Leclerc", "Boulanger", "Cdiscount", "Amazon"]

FLAG_REASONS = [
    "Marge suspecte (>80%) — confirmation humaine requise",
    "EAN deviné via NLP SerpAPI (confiance faible)",
    "Prix barré absent — impossible de confirmer la remise",
    "Produit similaire détecté par l'IA, EAN potentiellement dupliqué",
]

ERROR_MESSAGES = [
    "TimeoutError: page.goto timed out after 30000ms",
    "net::ERR_CONNECTION_REFUSED at https://www.carrefour.fr/promo/12345",
    "Playwright: Locator .product-price not found on page",
    "SerpAPI: 429 Too Many Requests — API Quota Exceeded",
]


def seed():
    print("Initialisation de la base de données...")
    init_db()
    db = SessionLocal()

    try:
        print("  Injection des Produits Référence...")
        for p_data in PRODUCTS:
            existing = db.query(ProduitReference).filter_by(ean=p_data["ean"]).first()
            if not existing:
                db.add(ProduitReference(**p_data))
        db.commit()
        print(f"     {len(PRODUCTS)} produits injectés/vérifiés.")

        print("  Injection des Missions & Logs...")
        m1_urls = [
            "https://www.carrefour.fr/promotions/high-tech",
            "https://www.carrefour.fr/promotions/smartphones",
            "https://www.carrefour.fr/promotions/gaming",
        ]
        m1 = MissionConfig(
            nom="Scan Promo Carrefour — High-Tech Q1 2026",
            mission_type="PROMO_SCAN",
            worker_type="HEADLESS_CAMELEON",
            target_urls=m1_urls,
            extraction_params={"max_pages": 3, "requires_scroll": True},
            frequence_cron="daily",
            status="RUNNING",
            is_active=True,
        )
        db.add(m1)
        db.commit()

        db.add(MissionLog(mission_id=m1.id, url_cible=m1_urls[0], statut="SUCCESS", timestamp=datetime.utcnow() - timedelta(minutes=5)))
        db.add(MissionLog(mission_id=m1.id, url_cible=m1_urls[1], statut="FAILED",
                          message_erreur="TimeoutError: page.goto exceeded timeout of 30000ms on Cloudflare challenge page",
                          timestamp=datetime.utcnow() - timedelta(minutes=3)))
        db.add(MissionLog(mission_id=m1.id, url_cible=m1_urls[2], statut="PROCESSING", timestamp=datetime.utcnow()))
        db.commit()

        m2_urls = [f"https://www.boulanger.com/c/electromenager?page={i}" for i in range(1, 6)]
        m2 = MissionConfig(
            nom="Veille Catalogue Boulanger — Electroménager",
            mission_type="CATALOGUE_FULL",
            worker_type="VISION_SNIPER",
            target_urls=m2_urls,
            extraction_params={"max_pages": 1},
            frequence_cron="weekly",
            status="IDLE",
            is_active=True,
            last_run=datetime.utcnow() - timedelta(hours=2),
            last_run_duration_s=145.3,
        )
        db.add(m2)
        db.commit()

        for i, url in enumerate(m2_urls):
            stat = "FAILED" if i == 2 else "SUCCESS"
            msg = "net::ERR_CONNECTION_RESET — le serveur a fermé la connexion" if stat == "FAILED" else None
            db.add(MissionLog(mission_id=m2.id, url_cible=url, statut=stat, message_erreur=msg,
                              timestamp=datetime.utcnow() - timedelta(hours=2, minutes=i * 3)))
        db.commit()
        print(f"     2 missions + {len(m1_urls) + len(m2_urls)} logs injectés.")

        print("  Injection des offres QA Lab (PENDING/FLAGGED/ERROR)...")
        qa_statuses_cycle = ["PENDING", "PENDING", "FLAGGED", "FLAGGED", "ERROR"]

        for i in range(15):
            p = PRODUCTS[i % len(PRODUCTS)]
            prix_brut = round(random.uniform(15.0, 450.0), 2)
            coupon = round(random.choice([0, 0, 5.0, 10.0, 15.0, 20.0]), 2)
            remise = round(random.choice([0, 0, 2.0, 5.0, 8.0]), 2)
            net_net = round(max(1.0, prix_brut - remise - coupon), 2)

            qa_stat = qa_statuses_cycle[i % len(qa_statuses_cycle)]
            flag_reason = random.choice(FLAG_REASONS) if qa_stat == "FLAGGED" else None
            if qa_stat == "ERROR":
                flag_reason = "EAN manquant — l'IA n'a pas pu identifier le code-barres"

            reliability = round(random.uniform(0.25, 0.65), 2) if qa_stat in ("FLAGGED", "ERROR") else round(random.uniform(0.70, 0.95), 2)

            db.add(OffreRetail(
                ean=p["ean"],
                enseigne=random.choice(ENSEIGNES),
                prix_public=round(prix_brut + random.uniform(5, 50), 2),
                prix_brut=prix_brut,
                remise_immediate=remise,
                valeur_coupon=coupon,
                prix_net_net_calcule=net_net,
                qa_status=qa_stat,
                flag_reason=flag_reason,
                reliability_score=reliability,
                source_url=f"https://www.{random.choice(ENSEIGNES).lower()}.fr/p/{p['ean']}",
                image_preuve_path=f"https://picsum.photos/seed/{p['ean'][:6]}{i}/600/400",
                is_active=True,
            ))
        db.commit()
        print(f"     15 offres QA injectées (PENDING/FLAGGED/ERROR).")

        print("  Injection des offres VALIDATED + PriceHistory...")
        for i in range(10):
            p = PRODUCTS[i % len(PRODUCTS)]
            prix_brut = round(random.uniform(20.0, 350.0), 2)
            net_net = round(prix_brut - random.uniform(0, 25), 2)
            market_price = round(net_net * random.uniform(1.25, 2.2), 2)

            status = "VALIDATED" if i < 5 else "PUBLISHED"

            db.add(OffreRetail(
                ean=p["ean"],
                enseigne=random.choice(ENSEIGNES),
                prix_public=round(prix_brut * 1.15, 2),
                prix_brut=prix_brut,
                prix_net_net_calcule=net_net,
                qa_status=status,
                reliability_score=round(random.uniform(0.85, 0.98), 2),
                prix_revente_marche=market_price,
                source_url=f"https://www.{random.choice(ENSEIGNES).lower()}.fr/p/{p['ean']}",
                image_preuve_path=f"https://picsum.photos/seed/val{p['ean'][:4]}{i}/600/400",
                is_active=True,
            ))

            for d in range(7, -1, -1):
                hist_price = round(market_price * random.uniform(0.93, 1.07), 2)
                db.add(PriceHistory(
                    ean=p["ean"],
                    prix_revente=hist_price,
                    fetch_date=datetime.utcnow() - timedelta(days=d, hours=random.randint(0, 12)),
                ))

        db.commit()
        print(f"     10 offres (5 VALIDATED + 5 PUBLISHED) + 80 points d'historique injectés.")

        print("\nSEED COMPLET. La base est remplie et prête pour le crash-test UI !")

    except Exception as e:
        print(f"\nERREUR pendant le seeding : {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
