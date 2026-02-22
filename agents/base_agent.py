import asyncio
import logging
import time
from datetime import datetime
from typing import Any
from abc import ABC, abstractmethod
from playwright.async_api import async_playwright, Page, BrowserContext
from core.models import AgentConfig, SessionLocal
from core.credential_manager import CredentialManager

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Cadre Asynchrone de la 'Flotte des Minions'.
    Chaque agent spécifique (Scout, LogicMiner, MarketProbe) héritera de cette classe.
    Intègre Playwright pour la capture Headless Anti-Bot et la rotation des Proxies/Clés.
    """

    def __init__(self, agent_config_id: int):
        self.agent_config_id = agent_config_id
        self._load_config()
        self.playwright = None
        self.browser = None
        self.gemini_cred = CredentialManager(service_name="gemini")

    def _load_config(self):
        db = SessionLocal()
        try:
            config = db.query(AgentConfig).filter(AgentConfig.id == self.agent_config_id).first()
            if not config:
                raise ValueError(f"AgentConfig introuvable pour ID={self.agent_config_id}")
            self.agent_nom = config.nom
            self.agent_type = config.type_agent
            self.target_url = config.target_url
            self.frequence_cron = config.frequence_cron
        finally:
            db.close()

    def _update_status(self, status: str, error_message: str = None, duration_s: float = None):
        db = SessionLocal()
        try:
            db_config = db.query(AgentConfig).filter(AgentConfig.id == self.agent_config_id).first()
            if db_config:
                db_config.status = status
                if status == "RUNNING":
                    db_config.last_run = datetime.utcnow()
                if error_message is not None:
                    db_config.error_message = error_message
                if duration_s is not None:
                    db_config.last_run_duration_s = duration_s
                db.commit()
        except Exception as e:
            logger.error(f"[{self.agent_nom}] Erreur MAJ statut DB: {e}")
            db.rollback()
        finally:
            db.close()

    async def init_browser(self):
        logger.info(f"[{self.agent_nom}] Initialisation Playwright Headless.")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ]
        )

    async def get_new_context(self) -> BrowserContext:
        context = await self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="fr-FR",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        return context

    async def teardown(self):
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.warning(f"[{self.agent_nom}] Erreur lors du cleanup: {e}")
        logger.info(f"[{self.agent_nom}] Arrêt complet du navigateur.")

    async def capture_screenshot(self, page: Page, path: str, full_page: bool = True):
        await page.screenshot(path=path, full_page=full_page, type="png")
        logger.debug(f"[{self.agent_nom}] Capture enregistrée: {path}")

    async def safe_goto(self, page: Page, url: str, timeout_ms: int = 30000):
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            logger.info(f"[{self.agent_nom}] Page chargée: {url}")
        except Exception as e:
            logger.error(f"[{self.agent_nom}] Échec navigation vers {url}: {e}")
            raise

    @abstractmethod
    async def extract_data(self, page: Page) -> Any:
        pass

    @abstractmethod
    async def process(self):
        pass

    async def run(self):
        start_time = time.time()
        try:
            logger.info(f"═══ Démarrage Agent [{self.agent_nom}] ({self.agent_type}) ═══")
            logger.info(f"    URL Cible: {self.target_url}")
            self._update_status("RUNNING")
            await self.init_browser()
            await self.process()
            duration = time.time() - start_time
            self._update_status("IDLE", duration_s=round(duration, 2))
            logger.info(f"═══ Agent [{self.agent_nom}] terminé en {duration:.1f}s ═══")
        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"{type(e).__name__}: {str(e)[:500]}"
            logger.error(f"L'agent [{self.agent_nom}] a échoué après {duration:.1f}s: {error_msg}", exc_info=True)
            self._update_status("ERROR", error_message=error_msg, duration_s=round(duration, 2))
        finally:
            await self.teardown()
