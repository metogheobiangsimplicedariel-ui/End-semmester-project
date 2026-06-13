# PhishShield - Plateforme distribuée de détection de phishing

PhishShield est une mini application distribuée et sécurisée développée en Python pour centraliser, analyser et qualifier les signalements d'e-mails suspectés de phishing.

Ce projet met en oeuvre les notions clés des applications réparties et de la cybersécurité (sécurité by design, authentification par jetons, journalisation d'audit sécurisée, mécanismes de résilience tels que les disjoncteurs et les limites de débit, et gestion des rôles utilisateurs).

---

## Architecture du Projet

Le système est découpé en 4 services communicants et un client :

```
/
├── app/
│   ├── gateway/                  # SubmissionService / API Gateway (Port 8000)
│   │   ├── main.py               # Serveur FastAPI principal + Routes API + Inscription publique
│   │   ├── resilience.py         # CircuitBreaker & RateLimiter
│   │   └── static/               # Interface Web (HTML, CSS, JS) avec formulaire d'inscription
│   ├── auth/                     # AuthService (Port 8001 - FastAPI)
│   │   ├── main.py               # Gestion des tokens signés, utilisateurs et rôles
│   │   └── auth.db               # Base SQLite locale des identifiants (hachés)
│   ├── analysis/                 # AnalysisService (Port 8002 - gRPC)
│   │   ├── main.py               # Serveur gRPC
│   │   ├── scoring.py            # Moteur heuristique d'analyse de phishing
│   │   ├── analysis_pb2.py       # Code de stub généré par protobuf
│   │   └── analysis_pb2_grpc.py  # Code gRPC généré
│   ├── audit/                    # AuditService (Port 8003 - FastAPI)
│   │   ├── main.py               # Enregistrement des logs de sécurité
│   │   └── audit.db              # Base SQLite locale des événements de sécurité
│   └── shared/
│       └── audit_client.py       # Client d'audit partagé importé par tous les services
├── client.py                     # Client interactif en ligne de commande (CLI) avec inscription
├── demo_submissions.py           # Script pour injecter des e-mails d'exemples
├── run_all.py                    # Script d'orchestration pour lancer tous les services
└── README.md                     # Cette documentation
```

---

## Gestion des Rôles Utilisateurs

La plateforme supporte trois niveaux de rôles :

| Rôle | Comment l'obtenir | Accès |
| :--- | :--- | :--- |
| `utilisateur` | Auto-inscription (Web UI ou CLI) | Soumission et consultation de ses propres signalements |
| `analyste` | Créé par un administrateur | Historique complet et émission de **jugements manuels** (2nde vérification) |
| `administrateur` | Pré-configuré au démarrage | Accès complet + Journaux d'audit sécurité |

Comptes pré-remplis au démarrage : `admin` / `admin123` et `analyst` / `analyst123`.

---

## Fonctionnalités de Sécurité & Résilience (Security by Design)

1. **Aucun mot de passe en clair** : Les identifiants sont salés et hachés via `PBKDF2-HMAC-SHA256` dans `AuthService`.
2. **Tokens signés cryptographiquement** : Les sessions sont gérées par des jetons HMAC-SHA256 auto-suffisants et limités dans le temps.
3. **Journalisation d'audit sécurisée** : Les événements critiques (échecs de connexion, inscriptions, scores élevés, alertes) sont centralisés par l'**AuditService**. Les tokens et mots de passe ne figurent jamais dans les journaux.
4. **Rate Limiting** : Protection contre l'abus de soumissions et brute-force (mécanisme de fenêtre glissante implémenté dans l'API Gateway).
5. **Circuit Breaker (Disjoncteur)** : Si le service gRPC d'analyse ou d'authentification tombe en panne, l'API Gateway coupe temporairement les requêtes pour éviter d'attendre les timeouts réseau.
6. **Moteur local de secours (Fallback)** : En cas d'indisponibilité de l'**AnalysisService** (gRPC), la Gateway bascule de manière transparente sur son moteur heuristique local intégré pour continuer à rendre service (mode dégradé).
7. **Rôle forcé à l'inscription** : L'endpoint public `/api/auth/register` attribue systématiquement le rôle `utilisateur`. Il est impossible de s'auto-inscrire avec un rôle privilégié.
8. **Seconde vérification (Humain dans la boucle)** : Les analystes peuvent examiner les signalements et émettre un jugement manuel (Phishing Confirmé / Faux Positif) pour compléter la détection automatique.

---

## Installation & Exécution

### 1. Prérequis
Assurez-vous d'avoir Python 3.11+ installé.

### 2. Configuration de l'environnement virtuel
Le projet s'appuie sur un environnement virtuel local (`.venv`) pour isoler ses dépendances.

**Créer l'environnement virtuel :**
```bash
python -m venv .venv
```

**Activer l'environnement virtuel :**
- Sur Windows :
  ```bash
  .\.venv\Scripts\activate
  ```
- Sur macOS/Linux :
  ```bash
  source .venv/bin/activate
  ```

**Installer les dépendances :**
```bash
pip install fastapi uvicorn requests grpcio grpcio-tools
```

### 3. Lancer la plateforme
Pour démarrer tous les services simultanément sur leurs ports respectifs, exécutez le script d'orchestration :
```bash
python run_all.py
```
*Le script démarrera les 4 services en parallèle et fusionnera leurs logs d'audit sur la console avec des préfixes identifiables.*

### 4. Injecter les données de test (Démonstration)
Dans une autre console, vous pouvez injecter un jeu d'e-mails de démonstration (faible, moyen et haut risque) pour peupler la plateforme :
```bash
.venv\Scripts\python demo_submissions.py
```

### 5. Utiliser le Tableau de bord Web
Une interface utilisateur web premium et réactive est disponible.
- Ouvrez votre navigateur sur : **[http://127.0.0.1:8000](http://127.0.0.1:8000)**
- Pour créer un nouveau compte : cliquez sur **"Créer un compte"** sur la page de connexion, remplissez le formulaire et validez.
- Connectez-vous avec l'un des comptes :
  - **Nouveau compte** : via le formulaire d'inscription (rôle `utilisateur`)
  - **Analyste** : `analyst` / `analyst123` (Accès à la soumission et à l'historique)
  - **Administrateur** : `admin` / `admin123` (Accès complet, y compris les **Journaux d'audit**)

### 6. Utiliser le client CLI
Vous pouvez également interagir avec la plateforme via le client interactif en console :
```bash
.venv\Scripts\python client.py
```
Au démarrage, un menu vous propose de **vous connecter** ou de **créer un compte**.
