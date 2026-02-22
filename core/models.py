from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, Boolean, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from core.config import DATABASE_URL

Base = declarative_base()

# ==========================================
# 1. GESTION DE LA FLOTTE & CONFIGURATION
# ==========================================

class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, autoincrement=True)
    service = Column(String, nullable=False)
    key_value = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    error_count = Column(Integer, default=0)
    last_error_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

class AgentConfig(Base):
    __tablename__ = "agent_configs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nom = Column(String, nullable=False)
    type_agent = Column(String, nullable=False)
    target_url = Column(String, nullable=False)
    frequence_cron = Column(String, nullable=False, default="manual")
    is_active = Column(Boolean, default=True)
    last_run = Column(DateTime, nullable=True)
    last_run_duration_s = Column(Float, nullable=True)
    status = Column(String, default="IDLE")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

class GlobalSettings(Base):
    __tablename__ = "global_settings"
    key = Column(String, primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

# ==========================================
# 2. LE HUB DE DONNÉES & PIVOT D'IDENTITÉ
# ==========================================

class ProduitReference(Base):
    __tablename__ = "produits_reference"
    ean = Column(String, primary_key=True)
    nom_genere = Column(String, nullable=False)
    marque = Column(String)
    categorie = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

class OffreRetail(Base):
    __tablename__ = "offres_retail"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_config_id = Column(Integer, ForeignKey("agent_configs.id"), nullable=True)
    ean = Column(String, ForeignKey("produits_reference.ean"), nullable=False)
    enseigne = Column(String, nullable=False)
    prix_public = Column(Float, nullable=False)
    remise_immediate = Column(Float, default=0.0)
    image_preuve_path = Column(String, nullable=False)
    source_url = Column(String, nullable=True)
    date_fin_promo = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=lambda: datetime.utcnow())
    produit = relationship("ProduitReference", backref="offres")
    agent = relationship("AgentConfig")

# ==========================================
# 3. LA MATRICE DE RÈGLES & LEVIERS (AST)
# ==========================================

class RulesMatrix(Base):
    __tablename__ = "rules_matrix"
    id = Column(Integer, primary_key=True, autoincrement=True)
    enseigne_concernee = Column(String, nullable=False)
    type_regle = Column(String, nullable=False)
    source_url = Column(String, nullable=True)
    ast_rules = Column(JSON, nullable=False)
    raw_text_extract = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

class LevierActif(Base):
    __tablename__ = "leviers_actifs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_config_id = Column(Integer, ForeignKey("agent_configs.id"), nullable=True)
    type_levier = Column(String, nullable=False)
    description = Column(String, nullable=True)
    valeur_absolue = Column(Float, default=0.0)
    valeur_pourcentage = Column(Float, default=0.0)
    marque_cible = Column(String, nullable=True)
    ean_cible = Column(String, ForeignKey("produits_reference.ean"), nullable=True)
    enseigne_cible = Column(String, nullable=True)
    ast_conditions = Column(JSON, nullable=True)
    source_url = Column(String, nullable=True)
    image_preuve_path = Column(String, nullable=True)
    date_fin = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    produit_cible = relationship("ProduitReference")
    agent = relationship("AgentConfig")

# ==========================================
# 4. LE RÉSULTAT (SONDE & COLLISION)
# ==========================================

class MarketSonde(Base):
    __tablename__ = "market_sonde"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ean = Column(String, ForeignKey("produits_reference.ean"), nullable=False)
    marketplace = Column(String, nullable=False, default="amazon_fr")
    asin = Column(String, nullable=True)
    buy_box = Column(Float, nullable=False)
    fba_fees = Column(Float, default=0.0)
    commission_percent = Column(Float, default=15.0)
    shipping_cost = Column(Float, default=0.0)
    bsr = Column(Integer, nullable=True)
    seller_count = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.utcnow())
    produit = relationship("ProduitReference", backref="market_data")

class CollisionResult(Base):
    __tablename__ = "collision_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ean = Column(String, ForeignKey("produits_reference.ean"), nullable=False)
    offre_id = Column(Integer, ForeignKey("offres_retail.id"), nullable=False)
    leviers_appliques_json = Column(JSON, nullable=True)
    scenario_detail_json = Column(JSON, nullable=True)
    prix_achat_net = Column(Float, nullable=False)
    prix_revente_estime = Column(Float, nullable=False)
    frais_plateforme = Column(Float, default=0.0)
    profit_net_absolu = Column(Float, nullable=False)
    roi_percent = Column(Float, nullable=False)
    certification_grade = Column(String)
    status_qa = Column(String, default="PENDING_QA")
    rejected_reason = Column(String, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.utcnow())
    produit = relationship("ProduitReference")
    offre = relationship("OffreRetail")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
