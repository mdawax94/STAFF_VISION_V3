"""
MODULE 3 — Scheduler Worker V3 (Dynamic Polling)
Ce script tourne en arrière-plan (daemon).
Il scrute les AgentConfig et MissionConfig dont is_active=True,
et lance ScraperEngine selon les fréquences définies.
NEW V4: Logging granulaire URL par URL avec la table MissionLog pour éviter les crashs globaux d'une mission en cas d'échec sur une seule URL.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
import asyncio
import logging
from datetime import datetime

from core.models import SessionLocal, AgentConfig, MissionConfig, MissionLog
from core.scraper_engine import ScraperEngine

logger = logging.getLogger("scheduler_worker")
logging.basicConfig(level=logging.INFO)

async def process_agent(agent_id: int):
    logger.info(f"Démarrage AgentConfig ID {agent_id}")
    engine = ScraperEngine(agent_config_id=agent_id)
    try:
        await engine.run()
    except Exception as e:
        logger.error(f"  -> Agent {agent_id} a crashé: {e}")

async def process_mission(mission_id: int):
    """
    Exécute une Mission complète.
    NOUVEAUTÉ V4 : ScraperEngine gère désormais la table MissionLog via callback.
    Nous veillons ici simplement à ce que la mission soit lancée proprement
    sans que le scheduler lui-même ne crashe.
    """
    logger.info(f"Démarrage MissionConfig ID {mission_id}")
    db = SessionLocal()
    try:
        mission = db.query(MissionConfig).filter_by(id=mission_id).first()
        if not mission or not mission.target_urls:
            logger.warning(f"  -> Mission {mission_id} vide ou introuvable.")
            return

        # Pre-populate pending logs if they don't exist
        for url in mission.target_urls:
            log = db.query(MissionLog).filter_by(mission_id=mission.id, url_cible=url).first()
            if not log:
                db.add(MissionLog(mission_id=mission.id, url_cible=url, statut="PENDING"))
        db.commit()

        # Run Engine
        engine = ScraperEngine(mission_config_id=mission_id)
        # L'engine mettra lui-même à jour la table via son _log_url_status
        await engine.run()

    except Exception as e:
        logger.error(f"  -> Mission {mission_id} a rencontré une erreur fatale: {e}")
        try:
            mission = db.query(MissionConfig).filter_by(id=mission_id).first()
            if mission:
                mission.status = "ERROR"
                mission.error_message = str(e)[:2000]
                db.commit()
        except:
            pass
    finally:
        db.close()


async def main_loop():
    """Boucle infinie du Scheduler"""
    logger.info("Scheduler démarré. En attente de jobs...")
    
    while True:
        db = SessionLocal()
        tasks = []
        try:
            # 1. Scrutage des Agents (Legacy Blueprint V2)
            agents = db.query(AgentConfig).filter(AgentConfig.is_active == True, AgentConfig.frequence_cron != "manual").all()
            for agent in agents:
                # Logique simplifiée de cron (run all every loop for testing)
                # En vrai, parser le frequence_cron et check last_run
                if agent.status != "RUNNING":
                    tasks.append(process_agent(agent.id))
            
            # 2. Scrutage des Missions (Nouvelle Stratégie multi-URLs V3)
            missions = db.query(MissionConfig).filter(MissionConfig.is_active == True, MissionConfig.frequence_cron != "manual").all()
            for mission in missions:
                if mission.status != "RUNNING":
                    tasks.append(process_mission(mission.id))

            if tasks:
                logger.info(f"Lancement batch de {len(tasks)} tâches d'extraction...")
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Erreur globale dans la boucle Scheduler : {e}")
        finally:
            db.close()

        # Pause pour éviter de spammer la BDD
        await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Scheduler arrêté manuellement.")
