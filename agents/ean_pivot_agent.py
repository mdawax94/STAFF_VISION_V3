"""
AGENT PIVOT EAN — Minion de Résolution d'Identité Produit.
Flux: Read GEN-XXXX products -> DuckDuckGo -> Regex -> Gemini fallback -> Update EAN + merge.
"""
import re
import json
import logging
from datetime import datetime
import google.generativeai as genai

from agents.base_agent import BaseAgent
from core.models import ProduitReference, OffreRetail, SessionLocal
from core.credential_manager import CredentialManager

logger = logging.getLogger(__name__)

EAN_EXTRACTION_PROMPT = """Tu es un assistant spécialisé dans l'identification de produits de grande consommation.

À partir du texte ci-dessous (résultats de recherche web), trouve le code EAN (code-barres à 13 chiffres) du produit suivant :
- Nom : {product_name}
- Marque : {brand}

Réponds UNIQUEMENT avec un JSON strict :
{{
  "ean_found": "1234567890123 ou null si introuvable",
  "confidence": 85,
  "source_hint": "Site ou contexte d'où vient l'EAN"
}}

TEXTE DE RECHERCHE :
---
{search_text}
---

RÈGLES :
- L'EAN doit faire exactement 13 chiffres.
- Si plusieurs EAN sont visibles, choisis celui qui correspond le mieux au produit.
- Si aucun EAN n'est trouvable, mets "ean_found": null.
- confidence = ta certitude de 0 à 100."""


class EanPivotAgent(BaseAgent):
    def __init__(self, agent_config_id: int):
        super().__init__(agent_config_id)
        self.gemini_cred = CredentialManager(service_name="gemini")

    def _get_pending_products(self) -> list:
        db = SessionLocal()
        try:
            products = db.query(ProduitReference).filter(
                ProduitReference.ean.like("GEN-%")
            ).limit(50).all()
            return [{"ean": p.ean, "nom": p.nom_genere, "marque": p.marque or "Inconnue"} for p in products]
        finally:
            db.close()

    async def _search_ean_web(self, page, product_name: str, brand: str) -> str:
        query = f"{brand} {product_name} EAN code barre fiche produit"
        search_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
        try:
            await self.safe_goto(page, search_url, timeout_ms=20000)
            await page.wait_for_timeout(2000)
            text = await page.evaluate("""
                () => {
                    const results = document.querySelectorAll('.result__body, .results--main .result, .web-result');
                    if (results.length > 0) {
                        return Array.from(results).slice(0, 5).map(r => r.innerText).join('\\n---\\n');
                    }
                    return document.body.innerText.substring(0, 5000);
                }
            """)
            return text[:8000] if text else ""
        except Exception as e:
            logger.warning(f"[{self.agent_nom}] Recherche web échouée: {e}")
            return ""

    def _extract_ean_regex(self, text: str) -> str | None:
        matches = re.findall(r'\b(\d{13})\b', text)
        return matches[0] if matches else None

    async def _extract_ean_gemini(self, product_name: str, brand: str, search_text: str) -> dict:
        api_key = self.gemini_cred.get_api_key()
        if not api_key:
            return {"ean_found": None, "confidence": 0}
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config={"response_mime_type": "application/json"}
            )
            prompt = EAN_EXTRACTION_PROMPT.format(
                product_name=product_name, brand=brand, search_text=search_text[:6000]
            )
            response = model.generate_content(prompt)
            if response.text:
                raw = response.text.strip()
                if raw.startswith("```json"):
                    raw = raw[7:-3].strip()
                return json.loads(raw)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                self.gemini_cred.report_error(api_key, status_code=429)
            logger.error(f"[{self.agent_nom}] Erreur Gemini EAN: {e}")
        return {"ean_found": None, "confidence": 0}

    def _update_ean(self, old_ean: str, new_ean: str):
        db = SessionLocal()
        try:
            existing = db.query(ProduitReference).filter(ProduitReference.ean == new_ean).first()
            temp_product = db.query(ProduitReference).filter(ProduitReference.ean == old_ean).first()
            if not temp_product:
                return
            if existing:
                db.query(OffreRetail).filter(OffreRetail.ean == old_ean).update(
                    {"ean": new_ean}, synchronize_session="fetch"
                )
                db.delete(temp_product)
                logger.info(f"[{self.agent_nom}] Fusion: {old_ean} \u2192 {new_ean} (produit existant)")
            else:
                db.query(OffreRetail).filter(OffreRetail.ean == old_ean).update(
                    {"ean": new_ean}, synchronize_session="fetch"
                )
                temp_product.ean = new_ean
                logger.info(f"[{self.agent_nom}] EAN r\u00e9solu: {old_ean} \u2192 {new_ean}")
            db.commit()
        except Exception as e:
            logger.error(f"[{self.agent_nom}] Erreur MAJ EAN: {e}")
            db.rollback()
        finally:
            db.close()

    async def extract_data(self, page) -> list:
        return []

    async def process(self):
        pending = self._get_pending_products()
        if not pending:
            logger.info(f"[{self.agent_nom}] Aucun produit en attente d'EAN.")
            return
        logger.info(f"[{self.agent_nom}] {len(pending)} produits en attente de r\u00e9solution EAN.")
        context = await self.get_new_context()
        page = await context.new_page()
        resolved = 0
        try:
            for product in pending:
                old_ean = product["ean"]
                nom = product["nom"]
                marque = product["marque"]
                search_text = await self._search_ean_web(page, nom, marque)
                if not search_text:
                    continue
                ean_regex = self._extract_ean_regex(search_text)
                if ean_regex:
                    self._update_ean(old_ean, ean_regex)
                    resolved += 1
                    continue
                result = await self._extract_ean_gemini(nom, marque, search_text)
                found_ean = result.get("ean_found")
                confidence = result.get("confidence", 0)
                if found_ean and len(found_ean) == 13 and found_ean.isdigit() and confidence >= 60:
                    self._update_ean(old_ean, found_ean)
                    resolved += 1
                else:
                    logger.info(f"[{self.agent_nom}] EAN non r\u00e9solu pour: {nom} (confiance: {confidence}%)")
                await page.wait_for_timeout(1500)
        finally:
            await context.close()
        logger.info(f"[{self.agent_nom}] R\u00e9solution termin\u00e9e: {resolved}/{len(pending)} EAN trouv\u00e9s.")
