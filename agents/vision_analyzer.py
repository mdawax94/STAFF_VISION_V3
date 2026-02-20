import os
import json
import logging
import sys
from pathlib import Path
from PIL import Image
import google.generativeai as genai

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.config import GEMINI_API_KEY, TEMP_FLYERS_DIR

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

MASTER_PROMPT = (
    "Tu es un expert en arbitrage retail. Analyse l'image du catalogue fournie. "
    "Pour chaque produit visible, extrais les informations suivantes de manière très précise. "
    "Ne rien inventer : si une donnée est absente ou illisible, mets null.\n\n"
    "Chaque objet produit doit suivre ce schéma JSON strict :\n"
    "- brand: Marque du produit\n"
    "- product_name: Nom complet et contenance\n"
    "- base_price: Prix initial affiché (ex: 10.50)\n"
    "- discount_immediate: Remise immédiate en € ou % (ex: '-30%' ou '2.50€')\n"
    "- loyalty_benefit: Avantage fidélité / crédité sur carte (ex: '2.00€ sur la carte')\n"
    "- odr_available: Booléen (True/False) indiquant la présence d'une Offre de Remboursement mentionnée\n"
    "- final_net_price: Calcul du prix de revient final après toutes les remises (Net-Net)\n"
    "- reliability_score: Note de 0 à 100 basée sur la lisibilité des informations et la certitude de l'extraction.\n\n"
    "Réponds UNIQUEMENT au format JSON (une liste d'objets)."
)

def analyze_image(image_path_str: str) -> list:
    """
    Analyzes a flyer image using Gemini 1.5 Flash to extract product data.
    
    Args:
        image_path_str: Path to the image file.
        
    Returns:
        list: A list of dictionaries containing product details.
    """
    try:
        image_path = Path(image_path_str)
        if not image_path.exists():
            logger.error(f"Fichier image introuvable : {image_path}")
            return []

        # Image size check using PIL
        with Image.open(image_path) as img:
            # Check file size in MB
            file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
            if file_size_mb > 20:
                logger.error(f"Image trop lourde ({file_size_mb:.2f}MB). Limite Gemini : 20MB.")
                return []
            
            logger.info(f"Analyse de l'image : {image_path.name} ({file_size_mb:.2f}MB)")
            
            # Prepare the model with JSON output constraint
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Request generation
            # Note: Gemini 1.5 handles image objects directly from PIL or file path
            response = model.generate_content([MASTER_PROMPT, img])
            
            if response.text:
                # Cleanup potential artifacts (though mime_type should handle it)
                raw_json = response.text.strip()
                if raw_json.startswith("```json"):
                    raw_json = raw_json[7:-3].strip()
                
                products = json.loads(raw_json)
                logger.info(f"Extraction réussie : {len(products)} produits trouvés.")
                return products
            else:
                logger.warning("Réponse vide de l'API Gemini.")
                return []

    except Exception as e:
        logger.error(f"Une erreur est survenue lors de l'analyse vision : {e}")
        return []

if __name__ == "__main__":
    # Test with previous Mission's image
    target_image = TEMP_FLYERS_DIR / "test_capture.png"
    
    print("--- TEST UNITAIRE : AGENT VISIONNAIRE ---")
    if target_image.exists():
        results = analyze_image(str(target_image))
        print(json.dumps(results, indent=4, ensure_ascii=False))
    else:
        print(f"Erreur : L'image de test {target_image} n'existe pas. Exécutez flyer_capture.py d'abord.")
