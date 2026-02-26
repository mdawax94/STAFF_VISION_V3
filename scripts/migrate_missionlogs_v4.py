import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Text, DateTime, ForeignKey
from config import DATABASE_URL

def migrate():
    engine = create_engine(DATABASE_URL)
    meta = MetaData()
    meta.reflect(bind=engine)

    # Vérifier l'existence
    if "mission_logs" not in meta.tables:
        print("Création de la table 'mission_logs'...")
        MissionLog = Table(
            "mission_logs", meta,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("mission_id", Integer, ForeignKey("mission_configs.id"), nullable=False),
            Column("url_cible", String, nullable=False),
            Column("statut", String, default="PROCESSING"),
            Column("message_erreur", Text, nullable=True),
            Column("timestamp", DateTime)
        )
        meta.create_all(engine)
        print("Table 'mission_logs' créée avec succès.")
    else:
        print("La table 'mission_logs' existe déjà.")

if __name__ == "__main__":
    migrate()