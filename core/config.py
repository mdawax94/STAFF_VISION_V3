import os
from pathlib import Path
from dotenv import load_dotenv

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

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    raise FileNotFoundError(f".env file not found at {ENV_PATH}")

def get_env_variable(var_name: str, required: bool = True) -> str:
    """Retrieves environment variables. Raises only if required=True."""
    value = os.getenv(var_name)
    if value is None and required:
        raise ValueError(f"Missing mandatory environment variable: {var_name}")
    return value or ""

# --- Clé obligatoire (utilisée partout) ---
GEMINI_API_KEY = get_env_variable("GEMINI_API_KEY", required=True)

# --- Clés optionnelles (gérées par le CredentialManager en DB) ---
SERPAPI_KEY = get_env_variable("SERPAPI_KEY", required=False)
SCRAPINGBEE_API_KEY = get_env_variable("SCRAPINGBEE_API_KEY", required=False)

# Database configuration
DB_PATH = DATA_DIR / "staff_vision.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"
