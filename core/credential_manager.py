from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
from core.models import ApiKey, SessionLocal

logger = logging.getLogger(__name__)


class CredentialManager:
    """
    Dynamic Credential Rotator.
    Manages a pool of API keys per service (gemini, scrapingbee, keepa, etc.).
    Detects quota errors (HTTP 429) and automatically rotates to the next healthy key.
    Keys are re-activated after a configurable cooldown period.
    """

    def __init__(self, service_name: str, error_threshold: int = 3, cooldown_minutes: int = 60):
        self.service_name = service_name
        self.error_threshold = error_threshold
        self.cooldown_minutes = cooldown_minutes

    def _get_session(self) -> Session:
        """Creates a new database session."""
        return SessionLocal()

    def get_api_key(self, db: Session = None) -> str | None:
        """
        Retrieves the first active and healthy API key for the service.
        Automatically re-activates keys that have passed their cooldown.
        Returns None if no key is available (all burnt or pool empty).
        """
        own_session = db is None
        if own_session:
            db = self._get_session()

        try:
            cooldown_time = datetime.utcnow() - timedelta(minutes=self.cooldown_minutes)
            cooled_keys = db.query(ApiKey).filter(
                ApiKey.service == self.service_name,
                ApiKey.is_active == False,
                ApiKey.last_error_at != None,
                ApiKey.last_error_at <= cooldown_time
            ).all()

            for key in cooled_keys:
                key.is_active = True
                key.error_count = 0
                logger.info(f"[CredentialManager] Réactivation clé {self.service_name} (ID={key.id}) après cooldown.")

            if cooled_keys:
                db.commit()

            api_key = db.query(ApiKey).filter(
                ApiKey.service == self.service_name,
                ApiKey.is_active == True,
                ApiKey.error_count < self.error_threshold
            ).order_by(ApiKey.error_count.asc()).first()

            if not api_key:
                logger.error(f"[CredentialManager] Aucune clé API disponible pour: {self.service_name}. Pool vide ou toutes en cooldown.")
                return None

            return api_key.key_value

        except Exception as e:
            logger.error(f"[CredentialManager] Erreur DB lors de la récupération de clé: {e}")
            return None
        finally:
            if own_session:
                db.close()

    def report_error(self, key_value: str, status_code: int = 429, db: Session = None):
        own_session = db is None
        if own_session:
            db = self._get_session()

        try:
            api_key = db.query(ApiKey).filter(
                ApiKey.service == self.service_name,
                ApiKey.key_value == key_value
            ).first()

            if not api_key:
                logger.warning(f"[CredentialManager] Clé inconnue signalée en erreur: {key_value[:8]}...")
                return

            api_key.last_error_at = datetime.utcnow()
            api_key.error_count += 1

            if status_code == 429 or api_key.error_count >= self.error_threshold:
                api_key.is_active = False
                logger.warning(
                    f"[CredentialManager] Clé {self.service_name} (ID={api_key.id}) DÉSACTIVÉE. "
                    f"Raison: {'Quota 429' if status_code == 429 else f'Seuil erreurs ({api_key.error_count}/{self.error_threshold})'}"
                )

            db.commit()

        except Exception as e:
            logger.error(f"[CredentialManager] Erreur DB lors du report d'erreur: {e}")
            db.rollback()
        finally:
            if own_session:
                db.close()

    def add_key(self, key_value: str, db: Session = None) -> bool:
        own_session = db is None
        if own_session:
            db = self._get_session()

        try:
            existing = db.query(ApiKey).filter(
                ApiKey.service == self.service_name,
                ApiKey.key_value == key_value
            ).first()

            if existing:
                logger.info(f"[CredentialManager] Clé déjà présente pour {self.service_name}, ignorée.")
                return False

            new_key = ApiKey(service=self.service_name, key_value=key_value)
            db.add(new_key)
            db.commit()
            logger.info(f"[CredentialManager] Nouvelle clé ajoutée pour {self.service_name}.")
            return True

        except Exception as e:
            logger.error(f"[CredentialManager] Erreur DB lors de l'ajout de clé: {e}")
            db.rollback()
            return False
        finally:
            if own_session:
                db.close()

    def get_pool_status(self, db: Session = None) -> dict:
        own_session = db is None
        if own_session:
            db = self._get_session()

        try:
            all_keys = db.query(ApiKey).filter(ApiKey.service == self.service_name).all()
            active = [k for k in all_keys if k.is_active]
            disabled = [k for k in all_keys if not k.is_active]

            return {
                "service": self.service_name,
                "total_keys": len(all_keys),
                "active_keys": len(active),
                "disabled_keys": len(disabled),
                "keys_detail": [
                    {
                        "id": k.id,
                        "active": k.is_active,
                        "errors": k.error_count,
                        "last_error": str(k.last_error_at) if k.last_error_at else None,
                        "key_preview": f"{k.key_value[:8]}..."
                    }
                    for k in all_keys
                ]
            }
        finally:
            if own_session:
                db.close()
