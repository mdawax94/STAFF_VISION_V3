"""
MODULE 2 — Scraper Engine v3 (Strategy Pattern — Worker Pool)
3 moteurs d'extraction spécialisés routés par worker_type :
  - API_FURTIF      : Requêtes HTTP pures (requests/httpx) pour APIs/JSON
  - HEADLESS_CAMELEON : Playwright headless avec scroll/pagination/JS rendering
  - VISION_SNIPER    : Playwright screenshot HD pour OCR/Vision IA

Usage:
    from core.scraper_engine import ScraperEngine
    engine = ScraperEngine(agent_config_id=1)
    result = await engine.run()
    # result.pages_html  → list[str]   (Furtif/Cameleon)
    # result.screenshots → list[bytes] (Vision Sniper)

    # Ou depuis une MissionConfig :
    engine = ScraperEngine(mission_config_id=5)
    result = await engine.run()
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json
import logging
import time
import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests
from core.models import SessionLocal, AgentConfig, MissionConfig
from core.config import scrapingbee_keys, AllKeysExhaustedError

logger = logging.getLogger("scraper_engine")

# Valid worker types
WORKER_TYPES = {"API_FURTIF", "HEADLESS_CAMELEON", "VISION_SNIPER"}


# ==========================================================================
# RÉSULTAT D'EXTRACTION — Conteneur universel
# ==========================================================================
@dataclass
class ExtractionResult:
    """Résultat retourné par tous les Workers."""
    worker_type: str
    pages_html: list[str] = field(default_factory=list)
    screenshots: list[bytes] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def has_content(self) -> bool:
        return bool(self.pages_html) or bool(self.screenshots)

    @property
    def content_type(self) -> str:
        if self.screenshots:
            return "image"
        return "html"


# ==========================================================================
# BASE WORKER — Interface commune (Strategy Pattern)
# ==========================================================================
class BaseWorker(ABC):
    """Interface commune pour tous les moteurs d'extraction."""

    @abstractmethod
    async def extract(self, urls: list[str], params: dict, on_url_status=None) -> ExtractionResult:
        """
        Exécute l'extraction sur une liste d'URLs.
        Args:
            urls: Liste d'URLs cibles
            params: Paramètres dynamiques (selectors, headers, scroll, max_pages)
            on_url_status: Callback(url: str, status: str, message: str) pour loguer l'avancement
        Returns:
            ExtractionResult standardisé
        """
        pass

# ==========================================================================
# WORKER 1 : API_FURTIF — Requêtes HTTP pures
# ==========================================================================
class ApiFurtifWorker(BaseWorker):
    """
    Requêtes HTTP directes (GET/POST) sans navigateur.
    Idéal pour : APIs publiques, pages légères, scraping de prix JSON.
    Utilise ScrapingBee en mode non-JS si une clé est disponible.
    """

    def __init__(self):
        pass

    async def extract(self, urls: list[str], params: dict, on_url_status=None) -> ExtractionResult:
        result = ExtractionResult(worker_type="API_FURTIF")
        start = time.time()

        headers = params.get("headers", {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "fr-FR,fr;q=0.9",
        })
        timeout = params.get("timeout", 30)

        for url in urls:
            if on_url_status: on_url_status(url, "PROCESSING")
            try:
                if scrapingbee_keys.has_keys:
                    # ScrapingBee mode non-JS avec rotation
                    while True:
                        try:
                            current_key = scrapingbee_keys.get_key()
                        except AllKeysExhaustedError:
                            raise AllKeysExhaustedError("API Quota Exceeded for ScrapingBee")

                        resp = requests.get(
                            "https://app.scrapingbee.com/api/v1/",
                            params={
                                "api_key": current_key,
                                "url": url,
                                "render_js": "false",
                                "premium_proxy": "true",
                                "country_code": "fr",
                            },
                            timeout=timeout,
                        )

                        if resp.status_code in (401, 403, 429):
                            logger.warning(f"  ScrapingBee: Clé épuisée ({resp.status_code}). Rotation...")
                            scrapingbee_keys.mark_exhausted(current_key)
                            continue
                            
                        # Si succès ou autre erreur sans lien avec le quota
                        break
                else:
                    resp = requests.get(url, headers=headers, timeout=timeout)

                if resp.status_code == 200:
                    result.pages_html.append(resp.text)
                    logger.info(f"  Furtif OK: {url} ({len(resp.text)} chars)")
                    if on_url_status: on_url_status(url, "SUCCESS")
                else:
                    result.errors.append(f"HTTP {resp.status_code}: {url}")
                    if on_url_status: on_url_status(url, "FAILED", f"HTTP {resp.status_code}")

            except AllKeysExhaustedError:
                if on_url_status: on_url_status(url, "FAILED", "Quota ScrapingBee Exhausted")
                raise # Propagation pour le scheduler
            except Exception as e:
                result.errors.append(f"Furtif error on {url}: {str(e)[:200]}")
                if on_url_status: on_url_status(url, "FAILED", str(e))

            # Petit délai anti-ban
            await asyncio.sleep(1)

        result.duration_s = time.time() - start
        return result


# ==========================================================================
# WORKER 2 : HEADLESS_CAMELEON — Playwright complet
# ==========================================================================
class HeadlessCameleonWorker(BaseWorker):
    """
    Playwright headless avec rendu JS, scroll infini et pagination CSS.
    Contourne les protections anti-bot grâce au rendu complet du navigateur.
    """

    async def _scroll_to_bottom(self, page, max_scrolls: int = 20, pause: float = 1.5):
        """Scroll progressif jusqu'à stabilisation de la hauteur."""
        previous_height = 0
        for i in range(max_scrolls):
            current_height = await page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                logger.info(f"  Scroll stable après {i} itérations.")
                break
            previous_height = current_height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(pause)

    async def _click_next_page(self, page, selector: str) -> bool:
        """Clique le bouton pagination. Retourne False si fin."""
        try:
            next_btn = await page.query_selector(selector)
            if not next_btn:
                return False

            is_disabled = await next_btn.get_attribute("disabled")
            aria_disabled = await next_btn.get_attribute("aria-disabled")
            classes = await next_btn.get_attribute("class") or ""

            if is_disabled or aria_disabled == "true" or "disabled" in classes:
                return False

            await next_btn.click()
            await page.wait_for_load_state("networkidle", timeout=10000)
            await asyncio.sleep(1.5)
            return True
        except Exception as e:
            logger.warning(f"  Pagination click échoué: {e}")
            return False

    async def extract(self, urls: list[str], params: dict, on_url_status=None) -> ExtractionResult:
        result = ExtractionResult(worker_type="HEADLESS_CAMELEON")
        start = time.time()

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            result.errors.append("Playwright non installé: pip install playwright")
            return result

        max_pages = params.get("max_pages", 1)
        pagination_selector = params.get("pagination_selector")
        requires_scroll = params.get("requires_scroll", False)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            # Smart Batching: Group URLs by root domain
            from collections import defaultdict
            from urllib.parse import urlparse
            domain_groups = defaultdict(list)
            for u in urls:
                domain = urlparse(u).netloc
                domain_groups[domain].append(u)

            for domain, domain_urls in domain_groups.items():
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                try:
                    page = await context.new_page()
                    for url in domain_urls:
                        if on_url_status: on_url_status(url, "PROCESSING")
                        try:
                            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            await page.wait_for_load_state("networkidle", timeout=15000)

                            for page_num in range(1, max_pages + 1):
                                logger.info(f"  Caméléon page {page_num}/{max_pages}: {url}")

                                if requires_scroll:
                                    await self._scroll_to_bottom(page)

                                html = await page.content()
                                result.pages_html.append(html)

                                if page_num < max_pages and pagination_selector:
                                    if not await self._click_next_page(page, pagination_selector):
                                        break
                                elif page_num < max_pages:
                                    break

                                await asyncio.sleep(1.5)

                            if on_url_status: on_url_status(url, "SUCCESS")

                        except Exception as e:
                            logger.error(f"Caméléon error on {url}: {e}")
                            result.errors.append(f"Caméléon error on {url}: {str(e)[:200]}")
                            if on_url_status: on_url_status(url, "FAILED", str(e))
                            
                            # Si erreur fatale, on recrée la page pour l'URL suivante du batch pour repartir sur de bonnes bases
                            try:
                                await page.close()
                            except: pass
                            page = await context.new_page()
                finally:
                    await context.close()

            await browser.close()

            await browser.close()

        result.duration_s = time.time() - start
        return result


# ==========================================================================
# WORKER 3 : VISION_SNIPER — Screenshot HD pour OCR/Vision IA
# ==========================================================================
class VisionSniperWorker(BaseWorker):
    """
    Capture des screenshots haute définition de pages complètes.
    Les images sont envoyées au parser Vision de Gemini pour OCR promotionnel.
    Idéal pour : Prospectus digitaux, catalogues image, PDFs rendus en HTML.
    """

    async def extract(self, urls: list[str], params: dict, on_url_status=None) -> ExtractionResult:
        result = ExtractionResult(worker_type="VISION_SNIPER")
        start = time.time()

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            result.errors.append("Playwright non installé: pip install playwright")
            return result

        requires_scroll = params.get("requires_scroll", False)
        viewport_width = params.get("viewport_width", 1920)
        viewport_height = params.get("viewport_height", 1080)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            # Smart Batching: Group URLs by root domain
            from collections import defaultdict
            from urllib.parse import urlparse
            domain_groups = defaultdict(list)
            for u in urls:
                domain = urlparse(u).netloc
                domain_groups[domain].append(u)

            for domain, domain_urls in domain_groups.items():
                context = await browser.new_context(
                    viewport={"width": viewport_width, "height": viewport_height},
                    device_scale_factor=2,  # Retina-quality screenshots
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                try:
                    page = await context.new_page()
                    for url in domain_urls:
                        if on_url_status: on_url_status(url, "PROCESSING")
                        try:
                            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            await page.wait_for_load_state("networkidle", timeout=15000)

                            # Scroll pour charger le contenu lazy si nécessaire
                            if requires_scroll:
                                previous_height = 0
                                for _ in range(10):
                                    current_height = await page.evaluate("document.body.scrollHeight")
                                    if current_height == previous_height:
                                        break
                                    previous_height = current_height
                                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                    await asyncio.sleep(1)

                            # Screenshot full-page en PNG haute résolution
                            screenshot_bytes = await page.screenshot(
                                full_page=True,
                                type="png",
                            )
                            result.screenshots.append(screenshot_bytes)
                            logger.info(f"  Vision OK: {url} ({len(screenshot_bytes)} bytes)")

                            if on_url_status: on_url_status(url, "SUCCESS")

                        except Exception as e:
                            logger.error(f"Vision error on {url}: {e}")
                            result.errors.append(f"Vision error on {url}: {str(e)[:200]}")
                            if on_url_status: on_url_status(url, "FAILED", str(e))
                            
                            # Récupération sur erreur fatale
                            try:
                                await page.close()
                            except: pass
                            page = await context.new_page()
                finally:
                    await context.close()

            await browser.close()

        result.duration_s = time.time() - start
        return result


# ==========================================================================
# WORKER REGISTRY — Routing table
# ==========================================================================
WORKER_REGISTRY = {
    "API_FURTIF": ApiFurtifWorker,
    "HEADLESS_CAMELEON": HeadlessCameleonWorker,
    "VISION_SNIPER": VisionSniperWorker,
}


def get_worker(worker_type: str) -> BaseWorker:
    """Factory pour instancier le bon Worker."""
    worker_class = WORKER_REGISTRY.get(worker_type)
    if not worker_class:
        raise ValueError(f"Worker '{worker_type}' inconnu. Valides: {list(WORKER_REGISTRY.keys())}")

    if worker_type == "API_FURTIF":
        return worker_class(scrapingbee_key=SCRAPINGBEE_API_KEY)
    return worker_class()


# ==========================================================================
# MOTEUR PRINCIPAL — Orchestre le Worker selon la config
# ==========================================================================
class ScraperEngine:
    """
    Moteur de scraping v3.
    Lit la config (AgentConfig OU MissionConfig), instancie le bon Worker,
    et retourne un ExtractionResult standardisé.
    """

    def __init__(
        self,
        agent_config_id: int = None,
        mission_config_id: int = None,
    ):
        if not agent_config_id and not mission_config_id:
            raise ValueError("Fournir agent_config_id ou mission_config_id.")
        self.agent_config_id = agent_config_id
        self.mission_config_id = mission_config_id
        self.config = None
        self._load_config()

    def _load_config(self):
        """Charge la config depuis AgentConfig ou MissionConfig."""
        db = SessionLocal()
        try:
            if self.mission_config_id:
                mission = db.query(MissionConfig).filter(
                    MissionConfig.id == self.mission_config_id
                ).first()
                if not mission:
                    raise ValueError(f"MissionConfig ID {self.mission_config_id} introuvable.")

                self.config = {
                    "source": "mission",
                    "id": mission.id,
                    "nom": mission.nom,
                    "worker_type": mission.worker_type,
                    "urls": mission.target_urls or [],
                    "params": mission.extraction_params or {},
                    "output_schema": mission.output_schema or "catalogue",
                    "ai_prompt_override": mission.ai_prompt_override,
                    "tenant_id": mission.tenant_id,
                }
            else:
                agent = db.query(AgentConfig).filter(
                    AgentConfig.id == self.agent_config_id
                ).first()
                if not agent:
                    raise ValueError(f"AgentConfig ID {self.agent_config_id} introuvable.")

                self.config = {
                    "source": "agent",
                    "id": agent.id,
                    "nom": agent.nom,
                    "worker_type": agent.worker_type or "HEADLESS_CAMELEON",
                    "urls": [agent.target_url],
                    "params": {
                        "pagination_selector": agent.pagination_selector,
                        "max_pages": agent.max_pages or 1,
                        "requires_scroll": agent.requires_scroll or False,
                    },
                    "output_schema": agent.template_type or "catalogue",
                    "ai_prompt_override": None,
                    "tenant_id": agent.tenant_id,
                }
        finally:
            db.close()

    def _update_status(self, status: str, duration: float = None, error_msg: str = None):
        """Met à jour le statut dans la table source."""
        db = SessionLocal()
        try:
            if self.config["source"] == "mission":
                obj = db.query(MissionConfig).filter(
                    MissionConfig.id == self.config["id"]
                ).first()
            else:
                obj = db.query(AgentConfig).filter(
                    AgentConfig.id == self.config["id"]
                ).first()

            if obj:
                obj.status = status
                obj.last_run = datetime.utcnow()
                if duration is not None:
                    obj.last_run_duration_s = duration
                if error_msg:
                    obj.error_message = error_msg[:500]
                elif status != "ERROR":
                    obj.error_message = None
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def _log_url_status(self, url: str, status: str, error_msg: str = None):
        """Callback pour mettre à jour la base MissionLogs depuis les workers."""
        if self.config["source"] != "mission":
            return
        db = SessionLocal()
        from core.models import MissionLog
        try:
            log = db.query(MissionLog).filter(
                MissionLog.mission_id == self.config["id"],
                MissionLog.url_cible == url
            ).first()
            if not log:
                log = MissionLog(mission_id=self.config["id"], url_cible=url)
                db.add(log)
            log.statut = status
            if error_msg:
                log.message_erreur = error_msg[:2000]
            db.commit()
        except Exception as e:
            logger.error(f"Failed to log url status: {e}")
            db.rollback()
        finally:
            db.close()

    async def run(self) -> ExtractionResult:
        """
        Point d'entrée principal.
        Route vers le bon Worker et retourne un ExtractionResult.
        """
        cfg = self.config
        worker_type = cfg["worker_type"]
        urls = cfg["urls"]

        if not urls:
            return ExtractionResult(
                worker_type=worker_type,
                errors=["Aucune URL configurée."],
            )

        self._update_status("RUNNING")

        try:
            worker = get_worker(worker_type)
            result = await worker.extract(urls, cfg["params"], on_url_status=self._log_url_status)
            self._update_status("IDLE", duration=result.duration_s)

            logger.info(
                f"Engine '{cfg['nom']}' [{worker_type}]: "
                f"{len(result.pages_html)} pages, {len(result.screenshots)} screenshots "
                f"en {result.duration_s:.1f}s"
            )

        except Exception as e:
            logger.error(f"Engine '{cfg['nom']}' erreur: {e}")
            self._update_status("ERROR", error_msg=str(e))
            result = ExtractionResult(
                worker_type=worker_type,
                errors=[str(e)],
            )

        return result
