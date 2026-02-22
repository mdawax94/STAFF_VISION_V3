"""
COLLISION ENGINE — Le Moteur de Collision (Daily Collider).
Flux: Charger offres -> Croiser avec leviers AST -> Calculer Net-Net -> Match données marché -> Grade certification.
"""
import logging
from datetime import datetime
from itertools import combinations
from core.models import (
    ProduitReference, OffreRetail, LevierActif, RulesMatrix,
    MarketSonde, CollisionResult, SessionLocal
)

logger = logging.getLogger(__name__)

class CollisionEngine:
    def __init__(self, min_roi_percent: float = 15.0):
        self.min_roi_percent = min_roi_percent

    def _get_active_offers(self, db) -> list:
        return db.query(OffreRetail).filter(OffreRetail.is_active == True).all()

    def _get_matching_levers(self, db, ean: str, marque: str, enseigne: str) -> list:
        now = datetime.utcnow()
        levers = db.query(LevierActif).filter(
            LevierActif.is_active == True,
            (LevierActif.date_fin == None) | (LevierActif.date_fin >= now),
        ).all()

        compatible = []
        for lv in levers:
            if lv.ean_cible and lv.ean_cible == ean:
                compatible.append(lv)
                continue
            if lv.marque_cible and marque and lv.marque_cible.lower() == marque.lower():
                if lv.enseigne_cible and lv.enseigne_cible.lower() not in ["toutes", enseigne.lower()]:
                    continue
                compatible.append(lv)
                continue
            if not lv.marque_cible and not lv.ean_cible and lv.enseigne_cible:
                if lv.enseigne_cible.lower() in ["toutes", enseigne.lower()]:
                    compatible.append(lv)
        return compatible

    def _get_rules(self, db, enseigne: str) -> list:
        rules = db.query(RulesMatrix).filter(
            (RulesMatrix.enseigne_concernee == enseigne) |
            (RulesMatrix.enseigne_concernee == "Toutes")
        ).all()
        return rules

    def _check_stacking_allowed(self, lever: LevierActif, rules: list) -> bool:
        if lever.ast_conditions:
            conditions = lever.ast_conditions
            if isinstance(conditions, dict):
                if conditions.get("cumulable") == False:
                    return False
                if conditions.get("exclusif") == True:
                    return False

        for rule in rules:
            ast = rule.ast_rules
            if not isinstance(ast, dict):
                continue
            global_flags = ast.get("global_flags", {})
            if lever.type_levier == "COUPON":
                if global_flags.get("promo_enseigne_cumulable_coupon_marque") == False:
                    return False
            if lever.type_levier == "ODR":
                if global_flags.get("odr_cumulable_promo_enseigne") == False:
                    return False
            if lever.type_levier == "FIDELITE":
                if global_flags.get("carte_fidelite_cumulable_promo") == False:
                    return False
        return True

    def _calculate_lever_discount(self, lever: LevierActif, base_price: float) -> float:
        if lever.valeur_absolue > 0:
            return lever.valeur_absolue
        elif lever.valeur_pourcentage > 0:
            return round(base_price * (lever.valeur_pourcentage / 100), 2)
        return 0.0

    def _generate_scenarios(self, base_price: float, remise_immediate: float,
                            compatible_levers: list, rules: list) -> list:
        prix_apres_remise = base_price - remise_immediate
        scenarios = []
        scenarios.append({
            "levers_used": [], "total_discount": remise_immediate,
            "net_net": prix_apres_remise, "detail": "Remise enseigne seule"
        })

        stackable = []
        exclusive = []
        for lv in compatible_levers:
            if self._check_stacking_allowed(lv, rules):
                stackable.append(lv)
            else:
                exclusive.append(lv)

        for lv in exclusive:
            discount = self._calculate_lever_discount(lv, prix_apres_remise)
            net = round(prix_apres_remise - discount, 2)
            scenarios.append({
                "levers_used": [lv.id],
                "total_discount": round(remise_immediate + discount, 2),
                "net_net": max(0, net),
                "detail": f"Exclusif: {lv.type_levier} ({lv.description or lv.id})"
            })

        if stackable:
            for r in range(1, len(stackable) + 1):
                for combo in combinations(stackable, r):
                    total_combo_discount = 0
                    detail_parts = []
                    current_price = prix_apres_remise
                    for lv in combo:
                        d = self._calculate_lever_discount(lv, current_price)
                        total_combo_discount += d
                        current_price -= d
                        detail_parts.append(f"{lv.type_levier}:{lv.description or lv.id}(-{d}\u20ac)")
                    net = round(prix_apres_remise - total_combo_discount, 2)
                    scenarios.append({
                        "levers_used": [lv.id for lv in combo],
                        "total_discount": round(remise_immediate + total_combo_discount, 2),
                        "net_net": max(0, net),
                        "detail": " + ".join(detail_parts)
                    })

        scenarios.sort(key=lambda s: s["net_net"])
        return scenarios

    def _calculate_certification_grade(self, roi: float, has_market_data: bool,
                                        levers_count: int) -> str:
        if roi >= 40 and has_market_data and levers_count <= 2:
            return "A+"
        elif roi >= 30 and has_market_data:
            return "A"
        elif roi >= 20:
            return "B"
        elif roi >= self.min_roi_percent:
            return "C"
        return "REJECTED"

    def run_collision(self):
        db = SessionLocal()
        try:
            offers = self._get_active_offers(db)
            logger.info(f"[COLLISION] Lancement sur {len(offers)} offres actives.")
            new_pepites = 0
            rejected = 0

            for offre in offers:
                ean = offre.ean
                enseigne = offre.enseigne
                produit = db.query(ProduitReference).filter(ProduitReference.ean == ean).first()
                if not produit:
                    continue
                marque = produit.marque or ""
                levers = self._get_matching_levers(db, ean, marque, enseigne)
                rules = self._get_rules(db, enseigne)
                scenarios = self._generate_scenarios(
                    offre.prix_public, offre.remise_immediate, levers, rules
                )
                best = scenarios[0]
                prix_net = best["net_net"]

                market = db.query(MarketSonde).filter(
                    MarketSonde.ean == ean
                ).order_by(MarketSonde.timestamp.desc()).first()

                if market:
                    buy_box = market.buy_box
                    commission = round(buy_box * (market.commission_percent / 100), 2)
                    frais = market.fba_fees + market.shipping_cost + commission
                    profit = round(buy_box - frais - prix_net, 2)
                    roi = round((profit / prix_net) * 100, 2) if prix_net > 0 else 0
                    prix_revente = buy_box
                else:
                    profit = 0
                    roi = 0
                    frais = 0
                    prix_revente = 0

                grade = self._calculate_certification_grade(
                    roi, market is not None, len(best["levers_used"])
                )

                if grade == "REJECTED" and not best["levers_used"]:
                    rejected += 1
                    continue

                existing = db.query(CollisionResult).filter(
                    CollisionResult.offre_id == offre.id
                ).first()

                if existing:
                    existing.prix_achat_net = prix_net
                    existing.prix_revente_estime = prix_revente
                    existing.frais_plateforme = frais
                    existing.profit_net_absolu = profit
                    existing.roi_percent = roi
                    existing.certification_grade = grade
                    existing.leviers_appliques_json = best["levers_used"]
                    existing.scenario_detail_json = best
                    existing.timestamp = datetime.utcnow()
                else:
                    collision = CollisionResult(
                        ean=ean, offre_id=offre.id,
                        leviers_appliques_json=best["levers_used"],
                        scenario_detail_json=best, prix_achat_net=prix_net,
                        prix_revente_estime=prix_revente, frais_plateforme=frais,
                        profit_net_absolu=profit, roi_percent=roi,
                        certification_grade=grade,
                    )
                    db.add(collision)
                new_pepites += 1

            db.commit()
            logger.info(f"[COLLISION] Termin\u00e9. {new_pepites} p\u00e9pites, {rejected} rejet\u00e9es.")
            return {"pepites": new_pepites, "rejected": rejected}

        except Exception as e:
            logger.error(f"[COLLISION] Erreur: {e}")
            db.rollback()
            return {"pepites": 0, "rejected": 0, "error": str(e)}
        finally:
            db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    engine = CollisionEngine(min_roi_percent=15.0)
    result = engine.run_collision()
    print(f"R\u00e9sultat Collision: {result}")
