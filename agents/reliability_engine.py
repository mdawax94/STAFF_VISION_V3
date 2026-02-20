import logging
import sys
import difflib
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from serpapi import GoogleSearch
from core.config import SERPAPI_KEY

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
FEES_ESTIMATE = 0.15  # 15% estimated selling/shipping fees

def get_market_price(product_name: str) -> dict:
    """
    Searches for market prices using SerpApi (Google Shopping).
    Filters out accessories results (abnormally low prices).
    """
    try:
        logger.info(f"Recherche de prix pour : {product_name}")
        
        params = {
            "engine": "google_shopping",
            "q": product_name,
            "api_key": SERPAPI_KEY,
            "hl": "fr",
            "gl": "fr"
        }
        
        search = GoogleSearch(params)
        results = search.get_dict()
        shopping_results = results.get("shopping_results", [])
        
        if not shopping_results:
            logger.warning(f"Aucun résultat Shopping pour : {product_name}")
            return {}

        # Intelligent Filtering: Get prices to determine a threshold
        prices = []
        for res in shopping_results:
            price_str = res.get("extracted_price")
            if price_str:
                prices.append(float(price_str))
        
        if not prices:
            return {}

        # Simple threshold logic: ignore results < 30% of the median price
        # (Assuming the median is likely the real product and others are accessories)
        prices.sort()
        median_price = prices[len(prices) // 2]
        threshold = median_price * 0.3
        
        valid_results = []
        for res in shopping_results:
            price = res.get("extracted_price")
            if price and float(price) > threshold:
                valid_results.append({
                    "title": res.get("title"),
                    "price": float(price),
                    "source": res.get("source")
                })

        if not valid_results:
            return {}

        # Extract stats from valid results
        valid_prices = [r["price"] for r in valid_results]
        lowest_price = min(valid_prices)
        average_price = sum(valid_prices) / len(valid_prices)
        top_result_title = valid_results[0]["title"]

        return {
            "lowest_price": lowest_price,
            "average_price": round(average_price, 2),
            "top_result_title": top_result_title,
            "total_results": len(valid_results)
        }

    except Exception as e:
        logger.error(f"Erreur lors de la recherche SerpApi : {e}")
        return {}

def calculate_arbitrage(purchase_price: float, market_data: dict, vision_score: int, original_name: str) -> dict:
    """
    Calculates arbitrage metrics and cross-references data for a final judgment.
    """
    if not market_data:
        return {"is_deal": False, "error": "No market data"}

    market_price = market_data["lowest_price"]
    
    # Net Margin Calculation: Market - Purchase - (Market * Fees)
    # Note: Using market price for fees as it's the selling price basis
    net_fees = market_price * FEES_ESTIMATE
    potential_profit = market_price - purchase_price - net_fees
    margin_percentage = (potential_profit / market_price) * 100 if market_price > 0 else 0
    
    # Text comparison (difflib)
    matcher = difflib.SequenceMatcher(None, original_name.lower(), market_data["top_result_title"].lower())
    similarity = matcher.ratio()
    
    # Confidence Index Logic
    if similarity >= 0.85 and vision_score >= 80:
        confidence = "HIGH"
    elif similarity >= 0.60:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
        
    is_deal = margin_percentage > 15

    return {
        "market_price": market_price,
        "potential_profit": round(potential_profit, 2),
        "margin_percentage": round(margin_percentage, 2),
        "is_deal": is_deal,
        "confidence_index": confidence,
        "similarity_score": round(similarity * 100, 1),
        "market_title_match": market_data["top_result_title"]
    }

if __name__ == "__main__":
    # Test Unitary
    test_product = "Nintendo Switch OLED"
    test_purchase_price = 220.0  # Simulated discount price
    
    print(f"--- TEST UNITAIRE : AGENT JUGE ({test_product}) ---")
    
    market_info = get_market_price(test_product)
    if market_info:
        print(f"Marché : Bas={market_info['lowest_price']}€, Moy={market_info['average_price']}€")
        print(f"Top Resultat : {market_info['top_result_title']}")
        
        decision = calculate_arbitrage(
            purchase_price=test_purchase_price,
            market_data=market_info,
            vision_score=95,
            original_name=test_product
        )
        
        print("\n--- RÉSULTAT DU JUGE ---")
        import json
        print(json.dumps(decision, indent=4, ensure_ascii=False))
    else:
        print("Erreur : Impossible de récupérer les prix du marché.")
