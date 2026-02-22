"""
AGENT SCOUT — Minion de Capture Visuelle & Extraction Produit.
Flux: Navigate -> Scroll -> Capture HD -> Gemini Vision -> ProduitReference + OffreRetail.
"""
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime
from PIL import Image
import google.generativeai as genai

from agents.base_agent import BaseAgent
from core.models import ProduitReference, OffreRetail, SessionLocal
from core.config import SCREENSHOTS_DIR
from core.credential_manager import CredentialManager

logger = logging.getLogger(__name__)

VISION_EXTRACTION_PROMPT = """Tu es un expert en arbitrage retail et en analyse de catalogues promotionnels.
Analyse cette capture d'écran d'un catalogue de manière exhaustive.

Pour CHAQUE produit visible, extrais les informations suivantes de manière très précise.
Ne rien inventer : si une donnée est absente ou illisible, mets null.

Schéma JSON STRICT pour chaque produit :
{
  "brand": "Marque du produit (ex: Samsung, Oral-B, Pampers)",
  "product_name": "Nom complet avec référence/contenance (ex: 'Galaxy S24 Ultra 256Go')",
  "ean": "Code EAN/code-barres si visible (13 chiffres), sinon null",
  "base_price": 99.99,
  "discount_type": "POURCENTAGE ou MONTANT ou CARTE_FIDELITE ou null",
  "discount_value": 20.0,
  "discount_description": "Description brute de la remise vue sur l'image (ex: '-30%', '5\u20ac de remise')",
  "loyalty_benefit": "Avantage fidélité si mentionné (ex: '3\u20ac crédités sur carte'), sinon null",
  "odr_mentioned": false,
  "final_displayed_price": 79.99,
  "confidence_score": 85
}

RÈGLES :
- Les prix doivent être des nombres, pas des chaînes.
- Si le prix barré est visible, utilise-le comme base_price.
- confidence_score = ta certitude de 0 à 100 sur l'exactitude de l'extraction.
- Réponds UNIQUEMENT avec une liste JSON d'objets. Aucun texte autour."""


class ScoutAgent(BaseAgent):
    def __init__(self, agent_config_id: int):
        super().__init__(agent_config_id)
        self.gemini_cred = CredentialManager(service_name="gemini")

    async def extract_data(self, page) -> list:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"scout_{self.agent_nom}_{timestamp}.png"
        screenshot_path = SCREENSHOTS_DIR / filename
        await self.capture_screenshot(page, str(screenshot_path), full_page=True)
        logger.info(f"[{self.agent_nom}] Capture HD enregistrée: {screenshot_path}")

        api_key = self.gemini_cred.get_api_key()
        if not api_key:
            logger.error(f"[{self.agent_nom}] Aucune clé Gemini disponible. Abandon.")
            return []

        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config={"response_mime_type": "application/json"}
            )
            img = Image.open(screenshot_path)
            response = model.generate_content([VISION_EXTRACTION_PROMPT, img])
            if response.text:
                raw = response.text.strip()
                if raw.startswith("```json"):
                    raw = raw[7:-3].strip()
                products = json.loads(raw)
                logger.info(f"[{self.agent_nom}] Gemini a extrait {len(products)} produits.")
                return [{"data": p, "screenshot_path": str(screenshot_path)} for p in products]
            else:
                logger.warning(f"[{self.agent_nom}] Réponse Gemini vide.")
                return []
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                self.gemini_cred.report_error(api_key, status_code=429)
            logger.error(f"[{self.agent_nom}] Erreur Gemini Vision: {e}")
            return []

    def _determine_enseigne(self) -> str:
        url_lower = self.target_url.lower()
        enseignes = {
            "carrefour": "Carrefour", "leclerc": "Leclerc", "auchan": "Auchan",
            "intermarche": "Intermarché", "lidl": "Lidl", "casino": "Casino",
            "cora": "Cora", "monoprix": "Monoprix", "franprix": "Franprix",
            "promobutler": "PromoButler", "bonial": "Bonial",
        }
        for key, val in enseignes.items():
            if key in url_lower:
                return val
        return "Inconnue"

    def _persist_products(self, extracted: list):
        db = SessionLocal()
        enseigne = self._determine_enseigne()
        count = 0
        try:
            for item in extracted:
                p = item["data"]
                screenshot = item["screenshot_path"]
                brand = p.get("brand") or "Inconnue"
                name = p.get("product_name") or "Produit inconnu"
                ean = p.get("ean")
                if not ean:
                    ean = f"GEN-{uuid.uuid4().hex[:12].upper()}"
                existing = db.query(ProduitReference).filter(ProduitReference.ean == ean).first()
                if not existing:
                    ref = ProduitReference(ean=ean, nom_genere=name, marque=brand)
                    db.add(ref)
                    db.flush()
                prix_public = float(p.get("base_price") or 0)
                prix_final = float(p.get("final_displayed_price") or prix_public)
                remise = round(prix_public - prix_final, 2) if prix_public > prix_final else 0.0
                offre = OffreRetail(
                    agent_config_id=self.agent_config_id,
                    ean=ean, enseigne=enseigne, prix_public=prix_public,
                    remise_immediate=remise, image_preuve_path=screenshot,
                    source_url=self.target_url,
                )
                db.add(offre)
                count += 1
            db.commit()
            logger.info(f"[{self.agent_nom}] {count} offres enregistrées en base (enseigne: {enseigne}).")
        except Exception as e:
            logger.error(f"[{self.agent_nom}] Erreur persistence DB: {e}")
            db.rollback()
        finally:
            db.close()

    async def process(self):
        context = await self.get_new_context()
        page = await context.new_page()
        try:
            await self.safe_goto(page, self.target_url)
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(800)
            products = await self.extract_data(page)
            if products:
                self._persist_products(products)
            else:
                logger.warning(f"[{self.agent_nom}] Aucun produit extrait.")
        finally:
            await context.close()
