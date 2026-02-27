from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, Boolean, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.hybrid import hybrid_property
from core.config import DATABASE_URL

Base = declarative_base()

# ==========================================
# 0. GESTION MULTI-TENANT (SUPABASE)
# ==========================================

class DbTenant(Base):
    """Stocke plusieurs chaînes de connexion Supabase pour basculer facilement."""
    __tablename__ = "db_tenants"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    connection_string = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

# ==========================================
# 0b. MONITORING — SANTÉ DES API EXTERNES
# ==========================================

class ApiHealthCheck(Base):
    """Stocke le statut Online/Offline de chaque service externe pour le Dashboard."""
    __tablename__ = "api_health_checks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    service_name = Column(String, nullable=False, unique=True)
    status = Column(String, default="UNKNOWN")
    last_check_at = Column(DateTime, nullable=True)
    last_response_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    consecutive_failures = Column(Integer, default=0)

# ==========================================
# 1. GESTION DE LA FLOTTE & CONFIGURATION
# ==========================================

class AgentConfig(Base):
    """Instanciation dynamique des Minions depuis l'interface."""
    __tablename__ = "agent_configs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nom = Column(String, nullable=False)
    type_agent = Column(String, nullable=False)
    template_type = Column(String, default="catalogue")
    target_url = Column(String, nullable=False)
    target_api = Column(String, default="playwright")
    pagination_selector = Column(String, nullable=True)
    max_pages = Column(Integer, default=1)
    requires_scroll = Column(Boolean, default=False)
    worker_type = Column(String, default="HEADLESS_CAMELEON")
    frequence_cron = Column(String, nullable=False, default="manual")
    is_active = Column(Boolean, default=True)
    last_run = Column(DateTime, nullable=True)
    last_run_duration_s = Column(Float, nullable=True)
    status = Column(String, default="IDLE")
    error_message = Column(Text, nullable=True)
    tenant_id = Column(Integer, ForeignKey("db_tenants.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    tenant = relationship("DbTenant")

class GlobalSettings(Base):
    """Paramètres globaux de l'usine."""
    __tablename__ = "global_settings"
    key = Column(String, primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

# ==========================================
# 2. LE HUB DE DONNÉES & PIVOT D'IDENTITÉ
# ==========================================

class ProduitReference(Base):
    """Le Pivot Universel. Un produit unique = Une ligne, identifié par son EAN."""
    __tablename__ = "produits_reference"
    ean = Column(String, primary_key=True)
    nom_genere = Column(String, nullable=False)
    marque = Column(String)
    categorie = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

class OffreRetail(Base):
    """L'offre instantanée capturée par un Agent Scout dans une enseigne."""
    __tablename__ = "offres_retail"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_config_id = Column(Integer, ForeignKey("agent_configs.id"), nullable=True)
    ean = Column(String, ForeignKey("produits_reference.ean"), nullable=False)
    enseigne = Column(String, nullable=False)
    prix_public = Column(Float, nullable=False)
    prix_brut = Column(Float, nullable=True)
    prix_initial_barre = Column(Float, nullable=True)
    promo_directe_type = Column(String, nullable=True)
    remise_immediate = Column(Float, default=0.0)
    valeur_coupon = Column(Float, default=0.0)
    valeur_odr = Column(Float, default=0.0)
    remise_fidelite = Column(Float, default=0.0)
    prix_net_net_calcule = Column(Float, nullable=True)
    prix_revente_marche = Column(Float, nullable=True)
    validation_humaine_phase_1 = Column(String, default="PENDING")
    reliability_score = Column(Float, default=0.0)
    qa_status = Column(String, default="PENDING")
    flag_reason = Column(Text, nullable=True)
    image_preuve_path = Column(String, nullable=True)
    image_present = Column(Boolean, default=False)
    margin_rate = Column(Float, nullable=True)
    source_url = Column(String, nullable=True)
    date_fin_promo = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=lambda: datetime.utcnow())

    produit = relationship("ProduitReference", backref="offres")
    agent = relationship("AgentConfig")

    @hybrid_property
    def calcul_net_net(self):
        """Calcul dynamique du prix Net-Net: prix_brut - coupon - odr - fidelite."""
        base = self.prix_brut if self.prix_brut is not None else (self.prix_public or 0)
        coupon = self.valeur_coupon or 0
        odr = self.valeur_odr or 0
        fidelite = self.remise_fidelite or 0
        remise = self.remise_immediate or 0
        return round(base - remise - coupon - odr - fidelite, 2)

    def recalculate_and_persist(self):
        """Recalcule et persiste le prix_net_net_calcule."""
        self.prix_net_net_calcule = self.calcul_net_net
        return self.prix_net_net_calcule

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

# ==========================================
# 4. API KEYS (Manager dynamique)
# ==========================================

class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, autoincrement=True)
    service_name = Column(String, nullable=False)
    api_key = Column(String, unique=True, nullable=False)
    status = Column(String, default="ACTIVE")
    last_used = Column(DateTime, nullable=True)
    raw_text_extract = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())


class RuleMatrix(Base):
    __tablename__ = "rule_matrix"
    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_name = Column(String, nullable=False)
    rule_type = Column(String, nullable=False)
    target_enseigne = Column(String, nullable=True)
    target_brand = Column(String, nullable=True)
    target_category = Column(String, nullable=True)
    target_ean = Column(String, nullable=True)
    discount_value = Column(Float, nullable=False, default=0.0)
    is_percentage = Column(Boolean, default=False)
    min_purchase_amount = Column(Float, nullable=True)
    max_uses = Column(Integer, nullable=True)
    source_url = Column(String, nullable=True)
    date_debut = Column(DateTime, nullable=True)
    date_expiration = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

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
    prix_amazon = Column(Float, nullable=True)
    prix_rakuten = Column(Float, nullable=True)
    volume_ventes_estime = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.utcnow())

    produit = relationship("ProduitReference", backref="market_data")

class PriceHistory(Base):
    """Historique des prix relevés sur le marché pour tracer la tendance (Phase 5)."""
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ean = Column(String, ForeignKey("produits_reference.ean"), nullable=False)
    prix_revente = Column(Float, nullable=False)
    fetch_date = Column(DateTime, default=lambda: datetime.utcnow())

    produit = relationship("ProduitReference", backref="historique_prix")

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
    certification_finale = Column(String, default="PENDING_PHASE2")
    reliability_score = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=lambda: datetime.utcnow())

    produit = relationship("ProduitReference")
    offre = relationship("OffreRetail")

# ==========================================
# 4b. MISSIONS D'EXTRACTION (V3 WORKER POOL)
# ==========================================

class MissionConfig(Base):
    __tablename__ = "mission_configs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nom = Column(String, nullable=False)
    mission_type = Column(String, nullable=False, default="PRICE_CHECK")
    worker_type = Column(String, nullable=False, default="HEADLESS_CAMELEON")
    target_urls = Column(JSON, nullable=False, default=[])
    extraction_params = Column(JSON, default={})
    ai_prompt_override = Column(Text, nullable=True)
    output_schema = Column(String, default="catalogue")
    frequence_cron = Column(String, default="manual")
    is_active = Column(Boolean, default=True)
    status = Column(String, default="IDLE")
    last_run = Column(DateTime, nullable=True)
    last_run_duration_s = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    tenant_id = Column(Integer, ForeignKey("db_tenants.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    tenant = relationship("DbTenant")

class MissionLog(Base):
    __tablename__ = "mission_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    mission_id = Column(Integer, ForeignKey("mission_configs.id"), nullable=False)
    url_cible = Column(String, nullable=False)
    statut = Column(String, default="PROCESSING")
    message_erreur = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    mission = relationship("MissionConfig", backref="logs")

# ==========================================
# 5. ORCHESTRATION & AUDIT LOGS
# ==========================================

class JobQueue(Base):
    __tablename__ = "job_queue"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_type = Column(String, nullable=False)
    target_id = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)
    status = Column(String, default="PENDING")
    priority = Column(Integer, default=10)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    next_retry_at = Column(DateTime, default=lambda: datetime.utcnow())
    worker_id = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

class SystemEventLog(Base):
    __tablename__ = "system_event_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String, nullable=False)
    severity = Column(String, default="INFO")
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.utcnow())

# Database engine and session factory
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Crée toutes les tables dans la base de données."""
    Base.metadata.create_all(bind=engine)
