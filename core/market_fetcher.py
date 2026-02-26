"""
MODULE 10 — Market Fetcher (Bot Phase 2)
Interroge les prix de revente du marché pour les offres validées (qa_status='VALIDATED').
Utilise la rotation multi-clés SerpAPI (Google Shopping).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import time
import requests
import re
from typing import Optional

from core.models import SessionLocal, OffreRetail, ProduitReference
from core.config import serpapi_keys, AllKeysExhaustedError

logger = logging.getLogger("market_fetcher")


class MarketFetcher:
    """Bot automatisé pour chercher le prix de revente marché (prix minimum)."""

    PRICE_PATTERN = re.compile(r"([0-9]+[.,][0-9]+)")

    def __init__(self):
        pass

    def _extract_price(self, price_str: str) -> Optional[float]:
        """Extrait un prix float depuis une string (ex: '24,99 €')."""
        if not price_str:
            return None
            
        # Parfois SerpAPI donne un float direct
        if isinstance(price_str, (int, float)):
            return float(price_str)
            
        m = self.PRICE_PATTERN.search(str(price_str).replace(" ", ""))
        if m:
            clean_str = m.group(1).replace(",", ".")
            try:
                return float(clean_str)
            except ValueError:
                return None
        return None

    def fetch_market_price(self, ean: str, product_name: str) -> Optional[float]:
        """Utilise SerpAPI (Google Shopping) pour trouver le prix le plus bas."""
        if not serpapi_keys.has_keys:
            logger.warning("MarketFetcher: Pas de clé SerpAPI configurée.")
            return None

        query = f"{ean} {product_name}"
        
        while True:
            try:
                current_key = serpapi_keys.get_key()
            except AllKeysExhaustedError:
                raise AllKeysExhaustedError("API Quota Exceeded for SerpAPI (Market Fetcher)")

            try:
                resp = requests.get(
                    "https://serpapi.com/search.json",
                    params={
                        "engine": "google_shopping",
                        "q": query,
                        "gl": "fr",
                        "hl": "fr",
                        "api_key": current_key,
                        "num": 10,
                    },
                    timeout=15,
                )

                if resp.status_code in (401, 403, 429):
                    logger.warning(f"  MarketFetcher SerpAPI: Clé épuisée ({resp.status_code}). Rotation...")
                    serpapi_keys.mark_exhausted(current_key)
                    continue

                if resp.status_code != 200:
                    return None

                data = resp.json()
                prices = []

                # Analyser les résultats Shopping
                for result in data.get("shopping_results", []):
                    price_val = result.get("price") or result.get("extracted_price")
                    if price_val:
                        p = self._extract_price(price_val)
                        if p and p > 0.1:  # Ignorer les prix absurdes
                            prices.append(p)

                # Chercher le prix le plus bas trouvé sur un panel
                if prices:
                    lowest = min(prices)
                    logger.info(f"  MarketFetcher: Plus bas prix trouvé pour {ean} -> {lowest} €")
                    return lowest
                    
                # Pas de prix trouvé
                break

            except requests.RequestException as e:
                logger.warning(f"  MarketFetcher SerpAPI erreur réseau: {e}")
                return None

        logger.info(f"  MarketFetcher: Aucun prix trouvé pour {ean}")
        return None

    def run_batch(self):
        """Trouve toutes les offres VALIDATED sans prix_revente_marche et les met à jour."""
        logger.info("Début du batch Market Fetcher...")
        db = SessionLocal()
        updated = 0
        try:
            # Récupérer les offres validées sans prix de revente
            targets = db.query(OffreRetail).filter(
                OffreRetail.qa_status == "VALIDATED",
                OffreRetail.prix_revente_marche == None
            ).all()

            if not targets:
                logger.info("Aucune offre VALIDATED nécessitant un scan marché.")
                return 0

            logger.info(f"Market Fetcher: {len(targets)} offres à scanner.")

            for offre in targets:
                # Obtenir le nom générique
                prod = db.query(ProduitReference).filter_by(ean=offre.ean).first()
                nom = prod.nom_genere if prod else ""
                
                try:
                    price = self.fetch_market_price(offre.ean, nom)
                    if price is not None:
                        offre.prix_revente_marche = price
                        # NEW Phase 5: Historiser le prix
                        from core.models import PriceHistory
                        history_entry = PriceHistory(ean=offre.ean, prix_revente=price)
                        db.add(history_entry)
                        
                        updated += 1
                        db.commit() # Commit ligne par ligne pour sécuriser le quota
                except AllKeysExhaustedError as e:
                    logger.error(f"Market Fetcher Fatal Error: {e}")
                    # On arrête le batch pour l'instant, on laisse courir
                    break
                    
                time.sleep(1.5) # Anti-ban
                
            logger.info(f"Fin du batch Market Fetcher. {updated} prix mis à jour.")
            return updated

        except Exception as e:
            logger.error(f"Erreur globale Market Fetcher: {e}")
            db.rollback()
            return updated
        finally:
            db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetcher = MarketFetcher()
    fetcher.run_batch()
