import sys
from pathlib import Path

# Add the project root to sys.path to allow absolute imports
sys.path.append(str(Path(__file__).resolve().parent))

try:
    from core.models import engine, Base
    from core.config import DB_PATH
    
    print(f"Initialisation de la base de données : {DB_PATH}")
    
    # Create all tables defined in models.py
    Base.metadata.create_all(bind=engine)
    
    print("Succès : Les tables ont été créées avec succès.")

except ImportError as e:
    print(f"Erreur d'importation : {e}")
    print("Assurez-vous que le dossier 'core' contient '__init__.py'.")
except Exception as e:
    print(f"Une erreur est survenue lors de l'initialisation : {e}")
