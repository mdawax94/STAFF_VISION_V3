from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from core.config import DATABASE_URL

Base = declarative_base()

class Source(Base):
    __tablename__ = "sources"
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, nullable=False)
    levier = Column(String)  # Catalogues, Coupons, ODR
    frequence = Column(Integer)  # 1, 2, 5, 7 jours
    last_scan = Column(DateTime)
    status = Column(String, default="IDLE") # IDLE, SCRAPING..., ANALYZING...

class ProduitBrut(Base):
    __tablename__ = "produits_bruts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("sources.id"))
    image_path = Column(String)
    marque = Column(String)
    produit = Column(String)
    prix_catalogue = Column(Float)
    remise = Column(Float)
    prix_net_net = Column(Float)
    levier_type = Column(String) # Catalogues, Coupons, ODR
    status = Column(String, default="PENDING")
    
    source = relationship("Source")

class Arbitrage(Base):
    __tablename__ = "arbitrage"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    produit = Column(String, nullable=False)
    prix_achat_net = Column(Float, nullable=False)
    prix_revente = Column(Float, nullable=False)
    marge = Column(Float, nullable=False)
    fiabilite = Column(Integer, nullable=False)
    image_preuve = Column(String)
    details_promo = Column(JSON)

class PepiteFinale(Base):
    __tablename__ = "pepites_finales"
    id = Column(Integer, primary_key=True, autoincrement=True)
    produit_brut_id = Column(Integer, ForeignKey("produits_bruts.id"))
    produit_name = Column(String)
    marge_nette = Column(Float)
    reliability_score = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Database engine and session factory
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
