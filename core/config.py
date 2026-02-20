import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory using pathlib
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMP_FLYERS_DIR = BASE_DIR / "temp_flyers"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
TEMP_FLYERS_DIR.mkdir(exist_ok=True)

# Path to .env file
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    raise FileNotFoundError(f".env file not found at {ENV_PATH}")

def get_env_variable(var_name: str) -> str:
    """Retrieves environment variables or raises an error."""
    value = os.getenv(var_name)
    if value is None:
        raise ValueError(f"Missing mandatory environment variable: {var_name}")
    return value

# API Keys
GEMINI_API_KEY = get_env_variable("GEMINI_API_KEY")
SERPAPI_KEY = get_env_variable("SERPAPI_KEY")
SCRAPINGBEE_API_KEY = get_env_variable("SCRAPINGBEE_API_KEY")

# Configuration ScrapingBee
SCRAPINGBEE_PARAMS = {
    "render_js": "True",
    "premium_proxy": "True",
    "block_ads": "True",
}

# Database configuration
DB_PATH = DATA_DIR / "staff_vision.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"
