import os
import logging
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # python-dotenv non installé, on continue sans

logger = logging.getLogger("config")

# Base directory using pathlib
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
TEMP_FLYERS_DIR = BASE_DIR / "temp_flyers"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
SCREENSHOTS_DIR.mkdir(exist_ok=True)
TEMP_FLYERS_DIR.mkdir(exist_ok=True)

# Path to .env file
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists() and load_dotenv is not None:
    load_dotenv(dotenv_path=ENV_PATH)
elif not ENV_PATH.exists():
    logger.warning(f".env file not found at {ENV_PATH}. Using environment variables or defaults.")

def get_env_variable(var_name: str, required: bool = True) -> str:
    """Retrieves environment variables. Raises only if required=True."""
    value = os.getenv(var_name)
    if value is None and required:
        raise ValueError(f"Missing mandatory environment variable: {var_name}")
    return value or ""

def get_env_list(var_name: str, fallback_var_name: str = None, required: bool = True) -> list[str]:
    """Retrieves a comma-separated list of values."""
    value = os.getenv(var_name)
    if not value and fallback_var_name:
        value = os.getenv(fallback_var_name)
    if not value and required:
        raise ValueError(f"Missing mandatory environment variable: {var_name} (or {fallback_var_name})")
    
    if not value:
        return []
        
    # Split by comma and clean up spaces
    return [v.strip() for v in value.split(",") if v.strip()]

# ==============================================================================
# KEY MANAGER (API Key Rotation)
# ==============================================================================

class AllKeysExhaustedError(Exception):
    """Exception levée quand TOUTES les clés d'un service sont épuisées."""
    pass

class KeyManager:
    """
    Gère une liste de clés API pour un service donné BDD (table ApiKey).
    Permet la rotation automatique en ignorant les clés épuisées.
    """
    def __init__(self, service_name: str):
        self.service_name = service_name.upper()
        
    @property
    def has_keys(self) -> bool:
        """Vérifie si au moins une clé (ACTIVE ou EXHAUSTED) existe en BDD."""
        from core.models import SessionLocal, ApiKey
        db = SessionLocal()
        try:
            return db.query(ApiKey).filter(ApiKey.service_name == self.service_name).count() > 0
        finally:
            db.close()

    def get_key(self) -> str:
        """Retourne la première clé ACTIVE trouvée en BDD pour ce service."""
        from core.models import SessionLocal, ApiKey
        from datetime import datetime
        db = SessionLocal()
        try:
            key_obj = db.query(ApiKey).filter(
                ApiKey.service_name == self.service_name,
                ApiKey.status == "ACTIVE"
            ).first()
            
            if not key_obj:
                raise AllKeysExhaustedError(f"API Quota Exceeded (or no keys) for {self.service_name}")
                
            key_obj.last_used = datetime.utcnow()
            key_value = key_obj.api_key
            db.commit()
            return key_value
            
        except AllKeysExhaustedError:
            raise
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Database error while fetching key for {self.service_name}: {e}")
        finally:
            db.close()
        
    def mark_exhausted(self, key_str: str):
        """Marque une clé comme épuisée (EXHAUSTED) en BDD."""
        from core.models import SessionLocal, ApiKey
        db = SessionLocal()
        try:
            key_obj = db.query(ApiKey).filter(
                ApiKey.api_key == key_str,
                ApiKey.service_name == self.service_name
            ).first()
            if key_obj:
                key_obj.status = "EXHAUSTED"
                db.commit()
        except Exception as e:
            db.rollback()
        finally:
            db.close()
            
    def reset(self):
        """Réinitialise l'état de toutes les clés de ce service à ACTIVE."""
        from core.models import SessionLocal, ApiKey
        db = SessionLocal()
        try:
            db.query(ApiKey).filter(ApiKey.service_name == self.service_name).update({"status": "ACTIVE"})
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


# --- Initialisation des KeyManagers ---
gemini_keys = KeyManager("GEMINI")
serpapi_keys = KeyManager("SERPAPI")
scrapingbee_keys = KeyManager("SCRAPINGBEE")
firecrawl_keys = KeyManager("FIRECRAWL")


SUPABASE_DATABASE_URL = get_env_variable("SUPABASE_DATABASE_URL", required=False)

if SUPABASE_DATABASE_URL:
    DATABASE_URL = SUPABASE_DATABASE_URL
else:
    DB_PATH = DATA_DIR / "staff_vision.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"
