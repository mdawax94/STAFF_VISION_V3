# STAFF v5 — Scraping & Training for Arbitrage Fast Finder

**STAFF v5** est un moteur SaaS B2B ultra-modulaire conçu pour l'Arbitrage Retail à haute performance. Son objectif est d'extraire, traiter et certifier des données de prix provenant de la grande distribution pour calculer le Net-Net (après remises, coupons, ODR et fidélité) et identifier les véritables opportunités d'arbitrage (ROI positif) destinées à la revente B2B.

---

## 🎯 Vision Globale (SaaS Retail Arbitrage B2B)
L'outil s'articule autour de deux principes :
1. **Pousser la logique au maximum** : Automatiser toute la chaîne de valeur, de la capture de la donnée brute sur le web (Catalogues, ODR, Promos) jusqu'à la détermination algorithmique du prix le plus bas du marché (Market Fetcher).
2. **L'Humain dans la Boucle (Human-In-The-Loop)** : Rien n'est expédié aux clients (B2B) sans passer par l'Arène (QA Lab et Market Export), où une validation finale garantit que les erreurs d'IA ou les faux-positifs sont écartés.

---

## 🏗️ Architecture des Moteurs

Le cœur d'extraction repose sur trois Workers asynchrones pilotés par une `MissionConfig` dynamique :

*   🥷 **API_FURTIF (`BaseWorker`)** : Effectue des requêtes HTTP directes (sans rendu JS) pour cibler les APIs publiques, JSON et pages légères. Utilise nativement la rotation ScrapingBee. Rapide et économique.
*   🦎 **HEADLESS_CAMELEON (`PlaywrightWorker`)** : Embarque un faux navigateur Chromium indétectable pour percer les défenses Cloudflare, Datadome, rouler le JavaScript lourd, et gérer le scroll infini / la pagination.
*   📸 **VISION_SNIPER (`VisionSniperWorker`)** : Prends des "screenshots plein écran" de la page web visitée et utilise Gemini 1.5 Pro Vision pour identifier et parser visuellement les éléments produits sans se soucier du code source (idéal pour les sites extrêmement obfusqués).

### 🧠 Smart Batching (One-Context-Browser)
Optimisation majeure de l'Usine V5 pour les moteurs abstraits (Caméléon & Vision). Le système regroupe intelligemment les URLs par domaine et réutilise le contexte du navigateur. Résultat : une seule bannière cookie acceptée, moins de blocages, et une navigation multi-pages ultra-rapide sur un même onglet.

### 🔑 Rotation des Clés API (KeyManager)
L'architecture intègre un gestionnaire d'API Keys stockées en base de données (`ApiKeys`). Si l'un des moteurs ou des LLMs (Gemini, SerpAPI, ScrapingBee) rencontre un quota dépassé (HTTP 429), le `KeyManager` assigne le statut `EXHAUSTED` à la clé et retente instantanément la requête avec la clé `ACTIVE` suivante. Si le pool est vide, le crash est contrôlé et signalé au Dashboard.

---

## 🔄 Le Pipeline de Données

1.  **Extraction** : Le `scheduler_worker.py` déclenche un Minion (Agent ou Mission) qui invoque le `ScraperEngine` via l'un des 3 Moteurs pour ramasser du HTML ou des Images.
2.  **Semantic Parsing** : Le `AiParser` instancie Gemini 1.5 pour transformer le texte/image en Pydantic Objects propres (ex: `OffreRetailSchema`).
3.  **EAN Hunting** : Le `EanHunter` prend le relai si l'EAN est manquant. Il utilise SerpAPI et des algorithmes de NLP pour associer le produit trouvé à son Code Barre universel.
4.  **Stacking Engine** : L'offre brute est passée à la calculette de marge : (Prix Brut - Remise - Coupon - Fidélité - ODR) = `Prix Net-Net`.
5.  **Quality Assurance (QA Lab & Kanban Split-Screen)** : Le Centre de Triage affiche un Split-Screen Kanban. La file d'attente à gauche permet des validations en masse (Bulk Actions), et le Mode Inspecteur à droite permet de corriger le tir granulairement. Un mécanisme de calcul du **Reliability Score** évalue l'assurance de l'extraction, de l'EAN et du Net-Net (Score de Fiabilité global de l'AI).
6.  **Market Fetcher & PriceHistory** : Un bot silencieux parcourt les offres validées. À chaque prix marché trouvé via SerpAPI, il alimente une table **PriceHistory**. L'historisation du BSR devient la grande force de la V5 garantissant la valeur des deals B2B dans le temps.
7.  **Market Export (L'Arène)** : Interface finale. Les commerciaux visualisent les pépites, appuyées par un graphique interactif natif retraçant l'historique du prix de revente. Validation finale (GO B2B) et export CSV.

---

## 🚀 Démarrer le Projet

Pour lancer l'application en conditions réelles, deux processus distincts doivent tourner en parallèle :

**1. Activer l'environnement virtuel (Optionnel mais recommandé)**
```bash
# Windows
.venv\Scripts\Activate.ps1
```

**2. Lancer le Worker d'Arrière-Plan (Bots, Scheduler & Market Fetcher)**
```bash
python core/scheduler_worker.py
```

**3. Lancer l'Interface Graphique (Streamlit SaaS)**
```bash
python -m streamlit run 01_🏠_Dashboard.py
```
*(Naviguez ensuite sur le port 8501 de votre `localhost` pour accéder à la tour de contrôle de l'application)*.
