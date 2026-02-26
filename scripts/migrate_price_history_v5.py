import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Text, DateTime, Float, ForeignKey
from core.config import DATABASE_URL
from datetime import datetime

def migrate():
    engine = create_engine(DATABASE_URL)
    meta = MetaData()
    meta.reflect(bind=engine)

    # Création table price_history
    if "price_history" not in meta.tables:
        print("Phase 5: Création table 'price_history'...")
        PriceHistory = Table(
            "price_history", meta,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("ean", String, ForeignKey("produits_reference.ean"), nullable=False),
            Column("prix_revente", Float, nullable=False),
            Column("fetch_date", DateTime, default=lambda: datetime.utcnow())
        )
        meta.create_all(engine)
        print("Table 'price_history' créée avec succès.")
    else:
         print("La table 'price_history' existe déjà.")

if __name__ == "__main__":
    migrate()