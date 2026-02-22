"""
AGENT LOGIC MINER — Minion d'Extraction de Conditions Légales (T&C / Fidélité).
Flux: Navigate -> Extract Text -> Gemini AST Prompt -> RulesMatrix Upsert.
"""
import json
import logging
from datetime import datetime
import google.generativeai as genai

from agents.base_agent import BaseAgent
from core.models import RulesMatrix, SessionLocal
from core.credential_manager import CredentialManager

logger = logging.getLogger(__name__)

AST_EXTRACTION_PROMPT = """Tu es un analyste juridique spécialisé dans les conditions générales de vente et les programmes de fidélité des enseignes de grande distribution française.

Ton rôle : Lire le texte juridique ci-dessous et en extraire TOUTES les règles de cumul et de compatibilité des promotions sous forme d'un JSON structuré strict.

TEXTE JURIDIQUE À ANALYSER :
---
{legal_text}
---

Tu dois retourner un JSON avec la structure STRICTE suivante :

{{
  "enseigne": "Nom de l'enseigne (ex: Carrefour, Leclerc)",
  "type_programme": "CARTE_FIDELITE | CGV_PROMO | CONDITIONS_ODR | REGLEMENT_JEU",
  "rules": [
    {{
      "rule_id": "R1",
      "description_fr": "Description lisible de la r\u00e8gle",
      "ast": {{
        "operator": "AND | OR | NOT | IF_THEN",
        "conditions": [
          {{
            "type": "CUMUL_AUTORISE | CUMUL_INTERDIT | PLAFOND_MONTANT | PLAFOND_QUANTITE | REQUIERT_CARTE | EXCLUT_CATEGORIE | EXCLUT_MARQUE | PERIODE_VALIDITE",
            "value": "valeur ou true/false",
            "details": "Pr\u00e9cisions si n\u00e9cessaire"
          }}
        ]
      }}
    }}
  ],
  "global_flags": {{
    "promo_enseigne_cumulable_coupon_marque": true,
    "odr_cumulable_promo_enseigne": true,
    "carte_fidelite_cumulable_promo": true,
    "limite_cumul_par_foyer": null,
    "periode_exclusion": null
  }},
  "extraction_confidence": 75,
  "ambiguites_detectees": ["Liste des points ambigus"]
}}

R\u00c8GLES IMP\u00c9RATIVES :
- Si le texte est vague, mets la valeur \u00e0 null et ajoute-le aux ambigu\u00eft\u00e9s.
- N'invente AUCUNE r\u00e8gle.
- R\u00e9ponds UNIQUEMENT avec le JSON."""


class LogicMiner(BaseAgent):
    def __init__(self, agent_config_id: int):
        super().__init__(agent_config_id)
        self.gemini_cred = CredentialManager(service_name="gemini")

    async def _extract_page_text(self, page) -> str:
        text = await page.evaluate("""
            () => {
                const selectors = ['main', 'article', '.content', '#content', '.main-content', 'body'];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText && el.innerText.length > 200) {
                        return el.innerText;
                    }
                }
                return document.body.innerText;
            }
        """)
        return text.strip() if text else ""

    async def extract_data(self, page) -> dict:
        legal_text = await self._extract_page_text(page)
        if len(legal_text) < 100:
            logger.warning(f"[{self.agent_nom}] Texte trop court ({len(legal_text)} chars).")
            return {}
        if len(legal_text) > 30000:
            legal_text = legal_text[:30000]
        logger.info(f"[{self.agent_nom}] Texte juridique extrait: {len(legal_text)} caract\u00e8res.")

        api_key = self.gemini_cred.get_api_key()
        if not api_key:
            return {}

        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config={"response_mime_type": "application/json"}
            )
            prompt = AST_EXTRACTION_PROMPT.format(legal_text=legal_text)
            response = model.generate_content(prompt)
            if response.text:
                raw = response.text.strip()
                if raw.startswith("```json"):
                    raw = raw[7:-3].strip()
                ast_result = json.loads(raw)
                logger.info(f"[{self.agent_nom}] AST extrait. Confiance: {ast_result.get('extraction_confidence', '?')}%")
                return {"ast": ast_result, "raw_text": legal_text}
            return {}
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                self.gemini_cred.report_error(api_key, status_code=429)
            logger.error(f"[{self.agent_nom}] Erreur Gemini AST: {e}")
            return {}

    def _persist_rules(self, result: dict):
        db = SessionLocal()
        try:
            ast_data = result.get("ast", {})
            raw_text = result.get("raw_text", "")
            enseigne = ast_data.get("enseigne", "Inconnue")
            type_regle = ast_data.get("type_programme", "INCONNU")
            confidence = float(ast_data.get("extraction_confidence", 0))

            existing = db.query(RulesMatrix).filter(
                RulesMatrix.enseigne_concernee == enseigne,
                RulesMatrix.type_regle == type_regle
            ).first()

            if existing:
                existing.ast_rules = ast_data
                existing.raw_text_extract = raw_text[:5000]
                existing.confidence = confidence
                existing.source_url = self.target_url
                existing.updated_at = datetime.utcnow()
                logger.info(f"[{self.agent_nom}] R\u00e8gle MAJ pour {enseigne}/{type_regle} (confiance: {confidence}%)")
            else:
                new_rule = RulesMatrix(
                    enseigne_concernee=enseigne, type_regle=type_regle,
                    ast_rules=ast_data, raw_text_extract=raw_text[:5000],
                    confidence=confidence, source_url=self.target_url,
                )
                db.add(new_rule)
                logger.info(f"[{self.agent_nom}] Nouvelle r\u00e8gle cr\u00e9\u00e9e pour {enseigne}/{type_regle}")
            db.commit()
        except Exception as e:
            logger.error(f"[{self.agent_nom}] Erreur persistence r\u00e8gles DB: {e}")
            db.rollback()
        finally:
            db.close()

    async def process(self):
        context = await self.get_new_context()
        page = await context.new_page()
        try:
            await self.safe_goto(page, self.target_url, timeout_ms=45000)
            await page.wait_for_timeout(2000)
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(500)
            result = await self.extract_data(page)
            if result and result.get("ast"):
                self._persist_rules(result)
            else:
                logger.warning(f"[{self.agent_nom}] Aucune r\u00e8gle extraite de {self.target_url}")
        finally:
            await context.close()
