import requests
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.config import SCRAPINGBEE_API_KEY, SCRAPINGBEE_PARAMS, TEMP_FLYERS_DIR

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def capture_page(url: str, output_name: str) -> bool:
    """
    Captures a screenshot of a web page using ScrapingBee.
    
    Args:
        url: The URL of the page to capture.
        output_name: The name of the resulting file (e.g., 'catalogue_leclerc.png').
        
    Returns:
        bool: True if success, False otherwise.
    """
    try:
        logger.info(f"Démarrage de la capture pour : {url}")
        
        # Output path handling with pathlib
        output_path = TEMP_FLYERS_DIR / output_name
        
        # API Parameters
        api_url = "https://app.scrapingbee.com/api/v1/"
        params = {
            "api_key": SCRAPINGBEE_API_KEY,
            "url": url,
            "screenshot": "True",
            "screenshot_full_page": "True",
            "block_ads": "True",
        }
        
        # Merge default params from config (render_js, premium_proxy, etc.)
        params.update(SCRAPINGBEE_PARAMS)
        
        # Execute request
        response = requests.get(api_url, params=params, timeout=60)
        
        # Error handling based on status code
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            logger.info(f"Succès : Capture sauvegardée dans {output_path}")
            return True
        else:
            logger.error(f"Erreur ScrapingBee ({response.status_code}) : {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de connexion lors de la capture : {e}")
        return False
    except Exception as e:
        logger.error(f"Une erreur inattendue est survenue : {e}")
        return False

if __name__ == "__main__":
    # Test capture with Google
    test_url = "https://www.google.com"
    test_filename = "test_capture.png"
    
    print("--- TEST UNITAIRE : AGENT SCOUT ---")
    success = capture_page(test_url, test_filename)
    
    if success:
        print(f"Test réussi. Vérifiez le dossier : {TEMP_FLYERS_DIR}")
    else:
        print("Test échoué. Consultez les logs ci-dessus.")
