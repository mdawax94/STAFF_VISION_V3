"""
AGENT MARKET PROBE — Sonde de Marché (Amazon / Rakuten / Google Shopping).
Flux: EAN réels -> Amazon.fr Playwright -> Google Shopping fallback -> Gemini -> MarketSonde DB.
Stratégie Coût Zéro : Pas d'API Keepa payante.
"""
import json
import logging
from datetime import datetime
import google.generativeai as genai

from agents.base_agent import BaseAgent
from core.models import ProduitReference, MarketSonde, SessionLocal
from core.credential_manager import CredentialManager

logger = logging.getLogger(__name__)

MARKET_EXTRACTION_PROMPT = """Tu es un analyste e-commerce expert en marketplaces.
À partir du texte ci-dessous (venant d'une page de recherche Amazon.fr ou Google Shopping),
identifie les informations du produit suivant :

- Produit recherché : {product_name} ({brand})
- EAN : {ean}

Extrais les données suivantes dans un JSON STRICT :
{{
  "product_found": true,
  "asin": "B0XXXXXXXX ou null",
  "buy_box_price": 99.99,
  "seller_count": 5,
  "bsr_estimate": 15000,
  "fba_available": true,
  "category": "Catégorie principale du produit",
  "confidence": 80
}}

RÈGLES :
- buy_box_price = le prix actuel affiché (le plus bas visible), en euros, nombre décimal.
- seller_count = nombre de vendeurs/offres visibles pour ce produit. Si absent, mets 1.
- bsr_estimate = Best Sellers Rank si visible, sinon estime-le grossièrement ou mets null.
- Si le produit n'est PAS trouvé dans le texte, mets "product_found": false et tout à null.
- confidence = certitude de 0 à 100 que c'est bien le bon produit.

TEXTE DE LA PAGE :
---
{page_text}
---"""

AMAZON_FEE_ESTIMATES = {
    "default": {"commission_pct": 15.0, "fba_fee": 4.50, "shipping": 0.0},
    "electronics": {"commission_pct": 7.0, "fba_fee": 5.00, "shipping": 0.0},
    "toys": {"commission_pct": 15.0, "fba_fee": 4.00, "shipping": 0.0},
    "beauty": {"commission_pct": 15.0, "fba_fee": 3.50, "shipping": 0.0},
    "grocery": {"commission_pct": 8.0, "fba_fee": 3.00, "shipping": 0.0},
}


class MarketProbeAgent(BaseAgent):
    def __init__(self, agent_config_id: int):
        super().__init__(agent_config_id)
        self.gemini_cred = CredentialManager(service_name="gemini")
        self.max_products_per_run = 30

    def _get_products_needing_market_data(self) -> list:
        db = SessionLocal()
        try:
            products = db.query(ProduitReference).filter(
                ~ProduitReference.ean.like("GEN-%")
            ).all()
            result = []
            for p in products:
                latest = db.query(MarketSonde).filter(
                    MarketSonde.ean == p.ean
                ).order_by(MarketSonde.timestamp.desc()).first()
                if not latest or (datetime.utcnow() - latest.timestamp).total_seconds() > 86400:
                    result.append({"ean": p.ean, "nom": p.nom_genere, "marque": p.marque or ""})
            return result[:self.max_products_per_run]
        finally:
            db.close()

    async def _search_amazon(self, page, product_name: str, ean: str) -> str:
        search_query = ean if not ean.startswith("GEN-") else product_name
        url = f"https://www.amazon.fr/s?k={search_query.replace(' ', '+')}"
        try:
            await self.safe_goto(page, url, timeout_ms=25000)
            await page.wait_for_timeout(2000)
            await page.evaluate("window.scrollBy(0, 800)")
            await page.wait_for_timeout(1000)
            text = await page.evaluate("""
                () => {
                    const results = document.querySelectorAll('[data-component-type="s-search-result"]');
                    if (results.length > 0) {
                        return Array.from(results).slice(0, 5).map(r => r.innerText).join('\\n===PRODUCT===\\n');
                    }
                    const main = document.querySelector('#search, .s-main-slot, #dp');
                    return main ? main.innerText.substring(0, 8000) : document.body.innerText.substring(0, 5000);
                }
            """)
            return text[:10000] if text else ""
        except Exception as e:
            logger.warning(f"[{self.agent_nom}] Recherche Amazon échouée: {e}")
            return ""

    async def _search_google_shopping(self, page, product_name: str, ean: str) -> str:
        query = f"{product_name} {ean} prix" if not ean.startswith("GEN-") else f"{product_name} prix achat"
        url = f"https://www.google.fr/search?q={query.replace(' ', '+')}&tbm=shop"
        try:
            await self.safe_goto(page, url, timeout_ms=20000)
            await page.wait_for_timeout(2000)
            text = await page.evaluate("""
                () => {
                    const results = document.querySelectorAll('.sh-dgr__content, .sh-dlr__list-result');
                    if (results.length > 0) {
                        return Array.from(results).slice(0, 5).map(r => r.innerText).join('\\n===RESULT===\\n');
                    }
                    return document.body.innerText.substring(0, 6000);
                }
            """)
            return text[:8000] if text else ""
        except Exception as e:
            logger.warning(f"[{self.agent_nom}] Recherche Google Shopping échouée: {e}")
            return ""

    def _estimate_fees(self, category: str) -> dict:
        cat_lower = (category or "").lower()
        for key in AMAZON_FEE_ESTIMATES:
            if key in cat_lower:
                return AMAZON_FEE_ESTIMATES[key]
        return AMAZON_FEE_ESTIMATES["default"]

    async def extract_data(self, page) -> list:
        return []

    def _persist_market_data(self, ean: str, data: dict, marketplace: str):
        db = SessionLocal()
        try:
            fees = self._estimate_fees(data.get("category", ""))
            market = MarketSonde(
                ean=ean, marketplace=marketplace, asin=data.get("asin"),
                buy_box=float(data.get("buy_box_price") or 0),
                fba_fees=fees["fba_fee"], commission_percent=fees["commission_pct"],
                shipping_cost=fees["shipping"], bsr=data.get("bsr_estimate"),
                seller_count=data.get("seller_count"),
            )
            db.add(market)
            db.commit()
            logger.info(f"[{self.agent_nom}] MarketSonde enregistrée pour EAN={ean}: Buy Box={data.get('buy_box_price')}€")
        except Exception as e:
            logger.error(f"[{self.agent_nom}] Erreur persistence MarketSonde: {e}")
            db.rollback()
        finally:
            db.close()

    async def process(self):
        products = self._get_products_needing_market_data()
        if not products:
            logger.info(f"[{self.agent_nom}] Aucun produit nécessitant des données marché.")
            return
        logger.info(f"[{self.agent_nom}] {len(products)} produits à sonder.")
        context = await self.get_new_context()
        page = await context.new_page()
        probed = 0
        try:
            for product in products:
                ean = product["ean"]
                nom = product["nom"]
                marque = product["marque"]
                page_text = await self._search_amazon(page, nom, ean)
                marketplace = "amazon_fr"
                if len(page_text) < 100:
                    page_text = await self._search_google_shopping(page, nom, ean)
                    marketplace = "google_shopping"
                if len(page_text) < 100:
                    continue
                api_key = self.gemini_cred.get_api_key()
                if not api_key:
                    break
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel(
                        model_name="gemini-1.5-flash",
                        generation_config={"response_mime_type": "application/json"}
                    )
                    prompt = MARKET_EXTRACTION_PROMPT.format(
                        product_name=nom, brand=marque, ean=ean, page_text=page_text[:8000]
                    )
                    response = model.generate_content(prompt)
                    if response.text:
                        raw = response.text.strip()
                        if raw.startswith("```json"):
                            raw = raw[7:-3].strip()
                        data = json.loads(raw)
                        if data.get("product_found") and data.get("confidence", 0) >= 50:
                            self._persist_market_data(ean, data, marketplace)
                            probed += 1
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "quota" in error_str.lower():
                        self.gemini_cred.report_error(api_key, status_code=429)
                    logger.error(f"[{self.agent_nom}] Erreur Gemini Market: {e}")
                await page.wait_for_timeout(2000)
        finally:
            await context.close()
        logger.info(f"[{self.agent_nom}] Sonde terminée: {probed}/{len(products)} produits sondés.")
