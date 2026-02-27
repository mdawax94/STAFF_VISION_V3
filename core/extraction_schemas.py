"""
MODULE 6 — Extraction Schemas (Pydantic v3)
Schemas stricts que l'IA (Gemini) doit remplir selon le template_type.
- "catalogue" → CatalogueItem : fiche produit avec EAN/SEO + prix barré + promo type
- "regles"   → RegleItem : condition/levier pour rules_matrix

NOUVEAU V3 :
  - EAN optionnel (le EAN Hunter complète après)
  - prix_initial_barre & promo_directe_type
  - Instructions SEO : chercher GTIN dans application/ld+json

Usage:
    from core.extraction_schemas import CatalogueItem, RegleItem, get_schema_for_template
    schema_class = get_schema_for_template("catalogue")
    item = schema_class.model_validate(raw_dict)
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime


class CatalogueItem(BaseModel):
    """
    Schema strict pour l'extraction de fiches produits en catalogue.

    INSTRUCTIONS GEMINI :
    1. Chercher le GTIN/EAN en PRIORITÉ dans les balises <script type="application/ld+json">
       (champs "gtin13", "gtin", "ean", "productID", "sku").
    2. Si absent du JSON-LD, chercher dans le texte visible (code-barres, fiche technique).
    3. Si introuvable, mettre ean = null (le EAN Hunter le résoudra).
    """
    ean: Optional[str] = Field(
        None,
        description=(
            "Code EAN/GTIN-13 du produit. "
            "PRIORITÉ : extraire depuis <script type='application/ld+json'> "
            "(champs gtin13, gtin, productID). Si introuvable, mettre null."
        ),
    )
    nom_produit: str = Field(..., min_length=3, description="Nom complet du produit")
    marque: Optional[str] = Field(None, description="Marque du produit")
    categorie: Optional[str] = Field(None, description="Catégorie (ex: Hygiène, Alimentaire)")

    prix_public: float = Field(..., gt=0, description="Prix public TTC affiché (prix final en rayon)")
    prix_initial_barre: Optional[float] = Field(
        None, ge=0,
        description="Prix initial barré (l'ancien prix avant promo). Si pas de prix barré, null.",
    )
    prix_brut: Optional[float] = Field(None, ge=0, description="Prix brut avant remise immédiate magasin")
    promo_directe_type: Optional[str] = Field(
        None,
        description=(
            "Type de promotion directe affichée : "
            "REMISE_IMMEDIATE, LOT, 2EME_GRATUIT, X_POUR_Y, POURCENTAGE, null si aucune"
        ),
    )
    remise_immediate: float = Field(default=0.0, ge=0, description="Remise immédiate en EUR")
    valeur_coupon: float = Field(default=0.0, ge=0, description="Valeur du coupon en EUR")
    valeur_odr: float = Field(default=0.0, ge=0, description="Valeur ODR en EUR")
    remise_fidelite: float = Field(default=0.0, ge=0, description="Remise fidélité en EUR")

    enseigne: str = Field(..., description="Enseigne source (Carrefour, Leclerc, etc.)")
    source_url: Optional[str] = Field(None, description="URL de la page source")
    image_url: Optional[str] = Field(None, description="URL de l'image produit")
    date_fin_promo: Optional[str] = Field(None, description="Date fin promo (format YYYY-MM-DD)")

    @field_validator("ean")
    @classmethod
    def validate_ean(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        cleaned = v.strip().replace(" ", "").replace("-", "")
        if not cleaned.isdigit():
            return None
        if len(cleaned) not in (8, 13):
            return None
        return cleaned

    @field_validator("prix_public")
    @classmethod
    def validate_prix(cls, v: float) -> float:
        if v > 50000:
            raise ValueError(f"Prix suspect (>50000\u20ac): {v}")
        return round(v, 2)

    @field_validator("promo_directe_type")
    @classmethod
    def validate_promo_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        allowed = {
            "REMISE_IMMEDIATE", "LOT", "2EME_GRATUIT",
            "X_POUR_Y", "POURCENTAGE", "CASHBACK",
        }
        upper = v.upper().strip()
        return upper if upper in allowed else None

    @property
    def needs_ean_hunting(self) -> bool:
        """True si l'EAN est manquant et doit \u00eatre r\u00e9solu."""
        return self.ean is None


class RegleCondition(BaseModel):
    """Sous-schema pour une condition d'application d'un levier."""
    champ: str = Field(..., description="Champ cible (ex: marque, categorie, montant_min)")
    operateur: str = Field(..., description="Op\u00e9rateur (==, !=, >=, <=, in, not_in)")
    valeur: str = Field(..., description="Valeur de comparaison")


class RegleItem(BaseModel):
    """Schema strict pour l'extraction de r\u00e8gles/conditions promotionnelles."""
    type_levier: str = Field(
        ...,
        description="Type du levier (COUPON, ODR, FIDELITE, REMISE_IMMEDIATE, MULTI_ACHAT)"
    )
    description: str = Field(..., min_length=5, description="Description lisible de la r\u00e8gle")

    valeur_absolue: float = Field(default=0.0, ge=0, description="Montant en EUR")
    valeur_pourcentage: float = Field(default=0.0, ge=0, le=100, description="Pourcentage de remise")

    enseigne_cible: str = Field(..., description="Enseigne concern\u00e9e")
    marque_cible: Optional[str] = Field(None, description="Marque cibl\u00e9e (si applicable)")
    ean_cible: Optional[str] = Field(None, description="EAN sp\u00e9cifique (si applicable)")

    conditions: List[RegleCondition] = Field(
        default_factory=list,
        description="Liste des conditions d'application du levier"
    )

    source_url: Optional[str] = Field(None, description="URL source de la r\u00e8gle")
    date_fin: Optional[str] = Field(None, description="Date d'expiration (YYYY-MM-DD)")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Score de confiance 0-1")

    @field_validator("type_levier")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"COUPON", "ODR", "FIDELITE", "REMISE_IMMEDIATE", "MULTI_ACHAT", "CASHBACK"}
        upper = v.upper().strip()
        if upper not in allowed:
            raise ValueError(f"type_levier '{v}' invalide. Valide: {allowed}")
        return upper


SCHEMA_REGISTRY = {
    "catalogue": CatalogueItem,
    "regles": RegleItem,
}


def get_schema_for_template(template_type: str) -> type[BaseModel]:
    """Retourne la classe Pydantic correspondant au template_type."""
    schema = SCHEMA_REGISTRY.get(template_type)
    if not schema:
        raise ValueError(
            f"Template '{template_type}' inconnu. Disponibles: {list(SCHEMA_REGISTRY.keys())}"
        )
    return schema


def get_json_schema_for_prompt(template_type: str) -> str:
    """
    G\u00e9n\u00e8re le JSON Schema \u00e0 injecter dans le prompt Gemini
    pour forcer un output structur\u00e9.
    """
    schema_class = get_schema_for_template(template_type)
    return schema_class.model_json_schema()


def validate_extraction(template_type: str, raw_data: dict) -> BaseModel:
    """
    Valide un dict brut extrait par l'IA contre le schema du template.
    Raises ValidationError si non conforme.
    """
    schema_class = get_schema_for_template(template_type)
    return schema_class.model_validate(raw_data)


def validate_batch(template_type: str, raw_list: list[dict]) -> tuple[list[BaseModel], list[dict]]:
    """
    Valide un batch de dicts. Retourne (valides, erreurs).
    Les erreurs contiennent l'index et le message d'erreur.
    """
    schema_class = get_schema_for_template(template_type)
    valid = []
    errors = []
    for i, item in enumerate(raw_list):
        try:
            valid.append(schema_class.model_validate(item))
        except Exception as e:
            errors.append({"index": i, "data": item, "error": str(e)[:300]})
    return valid, errors
