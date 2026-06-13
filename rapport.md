# Rapport de Projet : Plateforme Distribuée PhishShield

**Module : Applications réparties et cybersécurité**  
**Projet de fin de semestre**

---

## 1. Introduction & Objectifs

Le projet **PhishShield** est une plateforme distribuée de qualification et de détection d'e-mails de phishing. Son but est d'offrir une infrastructure robuste, modulaire et hautement sécurisée pour recevoir, inspecter et classifier des signalements suspects.

### Objectifs atteints :
- Conception d'une architecture orientée microservices (communication distribuée).
- Intégration de mécanismes de sécurité avancés (hachage, signature de tokens, contrôle d'accès basé sur les rôles).
- Conception de mécanismes de résilience (disjoncteurs, limites de débit, repli local en mode dégradé).
- Création d'une interface web interactive (UI Premium) avec des modales scrollables et d'un client en ligne de commande (CLI).
- Gestion autonome des comptes utilisateurs avec auto-inscription sécurisée depuis la Web UI et le CLI.
- **Seconde vérification** : Fonctionnalité permettant aux analystes d'émettre un jugement manuel (Phishing Confirmé / Faux Positif) sur les signalements automatisés.

---

## 2. Architecture Technique et Flux d'Information

Le système est composé de 4 microservices et de clients (CLI/Web). Chaque composant s'exécute dans son propre espace de processus.

### Diagramme d'Architecture (Composants)

```mermaid
graph TD
    subgraph Clients
        Web[Interface Web]
        CLI[Client CLI Python]
    end

    subgraph API Gateway
        GW[Gateway Service - Port 8000<br/>FastAPI]
        DB_Sub[(submissions.db)]
    end

    subgraph Services Distribués
        Auth[Auth Service - Port 8001<br/>FastAPI]
        DB_Auth[(auth.db)]
        
        Analysis[Analysis Service - Port 8002<br/>gRPC]
        
        Audit[Audit Service - Port 8003<br/>FastAPI]
        DB_Audit[(audit.db)]
    end

    Web -->|HTTP / REST| GW
    CLI -->|HTTP / REST| GW
    
    GW -->|REST| Auth
    GW -->|gRPC| Analysis
    GW -->|REST| Audit
    
    Auth -->|REST| Audit
    Analysis -->|REST| Audit
    
    GW --- DB_Sub
    Auth --- DB_Auth
    Audit --- DB_Audit
```

### Flux d'information typique (Séquence)


```mermaid
sequenceDiagram
    autonumber
    actor Client as Client (Web / CLI)
    participant GW as API Gateway (8000)
    participant Auth as AuthService (8001)
    participant Analysis as AnalysisService (8002)
    participant Audit as AuditService (8003)

    Client->>GW: POST /api/auth/register (Inscription publique)
    GW->>Auth: POST /register (rôle forcé : utilisateur)
    Auth-->>GW: Compte créé
    GW->>Audit: POST /log (USER_REGISTERED)

    Client->>GW: POST /api/submissions (avec Token Bearer)
    GW->>Auth: POST /validate (Vérifier le Token)
    Auth-->>GW: OK (rôle, username)
    GW->>Analysis: AnalyzeEmail (gRPC call)
    Note over Analysis: Scoring heuristique
    Analysis-->>GW: Réponse (Score, Justifications)
    GW->>Audit: POST /log (Événement de soumission)
    Audit-->>GW: OK
    Note over GW: Sauvegarde locale SQLite
    GW-->>Client: Retour du score et de la qualification
```

### Détail des Protocoles et Ports :
- **API Gateway (Port 8000)** : Point d'accès REST principal gérant le routage, le stockage local des signalements (SQLite `submissions.db`) et servant l'interface utilisateur web.
- **AuthService (Port 8001)** : Gère les accès via HTTP REST. Il isole les identifiants utilisateurs dans `auth.db`.
- **AnalysisService (Port 8002)** : Utilise **gRPC** pour l'échange de messages rapides et typés. Il analyse l'e-mail selon des règles d'ingénierie sociale et d'heuristiques réseaux.
- **AuditService (Port 8003)** : Centralise les logs de sécurité au format JSON via des requêtes HTTP.

---

## 3. Gestion des Rôles, Auto-inscription et Seconde Vérification

La plateforme implémente un système RBAC (Role-Based Access Control) à **trois niveaux** :

| Rôle | Création | Capacités |
| :--- | :--- | :--- |
| `utilisateur` | Auto-inscription (Web UI ou CLI) | Soumettre et consulter les signalements |
| `analyste` | Créé par un administrateur | Mêmes droits que `utilisateur` |
| `administrateur` | Pré-configuré au démarrage (`admin`) | Accès complet + Journaux d'audit |

### Endpoint d'auto-inscription
- **Route** : `POST /api/auth/register` (public, sans authentification)
- **Validation** : Pydantic enforce un nom d'utilisateur de 3+ caractères et un mot de passe de 6+ caractères.
- **Rôle forcé** : Le rôle est systématiquement fixé à `utilisateur` dans le code de la Gateway. Il est impossible pour un utilisateur d'auto-s'inscrire avec un rôle élevé.
- **Accès** : Disponible depuis la **Web UI** (lien "Créer un compte" sur la page de connexion) et depuis le **CLI** (menu d'accueil, option 2).

### Processus de Seconde Vérification (Jugement Manuel)
Afin d'ajouter une couche humaine à la détection automatisée, les utilisateurs ayant le rôle `analyste` ou `administrateur` disposent d'une fonctionnalité exclusive :
- Lors de l'inspection d'un signalement, l'analyste peut émettre un **jugement manuel** (*Phishing Confirmé* ou *Faux Positif*).
- Ce jugement est stocké de manière persistante (colonne `manual_judgement` dans `submissions.db`) et remplace visuellement le statut "En attente de vérification" pour l'utilisateur normal ayant soumis l'e-mail.
- L'émission d'un jugement est strictement contrôlée côté backend et trace un log d'audit spécifique (`MANUAL_JUDGEMENT_ADDED`).

---

## 4. Modélisation des Menaces et Contre-mesures (STRIDE)

Pour répondre aux exigences de cybersécurité par design, nous avons rédigé la matrice des menaces suivantes selon le modèle STRIDE :

| Catégorie | Menace Identifiée | Impact | Contre-mesures appliquées |
| :--- | :--- | :--- | :--- |
| **Spoofing** (Usurpation) | Un attaquant tente d'usurper l'identité d'un analyste ou d'un administrateur. | Accès non autorisé aux signalements et aux logs de sécurité. | Authentification par jeton HMAC-SHA256 signé cryptographiquement avec clé secrète serveur. |
| **Tampering** (Altération) | Modification des requêtes de soumission ou injection de payloads malveillants. | Corruption de la base de données ou contournement de l'analyse. | Validation stricte des types et longueurs via **Pydantic** côté serveur. Limitation de la taille des e-mails à 10 Ko. |
| **Repudiation** (Répudiation) | Un utilisateur effectue des actions sensibles (ex. consultation de logs d'audit) et le nie. | Perte de traçabilité lors d'un incident de sécurité. | **AuditService** dédié et indépendant qui logue systématiquement toutes les actions sensibles avec horodatage et ID utilisateur. |
| **Information Disclosure** (Fuite d'info) | Fuite d'informations d'erreur internes (stack traces) au client ou interception de mots de passe. | Un attaquant peut comprendre l'architecture interne ou intercepter des mots de passe. | Hachage sécurisé `PBKDF2-HMAC-SHA256` avec sel unique. Messages d'erreur génériques renvoyés par l'API Gateway. Mots de passe et tokens complets masqués des logs. |
| **Denial of Service** (Déni de Service) | Brute-force ou inondation du serveur de soumission par des requêtes en boucle. | Épuisement des ressources système et indisponibilité. | Middleware de **Rate Limiting** par adresse IP (fenêtre glissante in-memory). |
| **Elevation of Privilege** (Élévation de privilèges) | Un utilisateur tente de s'auto-inscrire avec le rôle `administrateur` ou `analyste`, ou d'appeler l'API d'audit. | Accès non autorisé aux journaux d'audit ou aux fonctions d'administration. | Le rôle est **forcé à `utilisateur`** dans l'endpoint public `/api/auth/register`. Contrôle de rôle strict (RBAC) sur les routes sensibles : rejet immédiat et log d'alerte critique. |

### 4.2. Conformité stricte aux exigences de cybersécurité du projet

Pour répondre de manière exhaustive à la grille d'évaluation, voici comment chaque point a été adressé techniquement :

1. **Ne jamais stocker ni afficher les mots de passe en clair** : 
   - *Stockage* : Les mots de passe sont salés (`os.urandom`) et hachés via `hashlib.pbkdf2_hmac` avec SHA-256 dans `AuthService`.
   - *Affichage* : Les formulaires web utilisent `type="password"` et le CLI masque la saisie (librairie `getpass` native ou substitution de caractères).
2. **Ne pas journaliser les tokens complets** : 
   - L'AuditService et les fonctions de logging ne tracent **jamais** la chaîne JWT complète. Seul le nom d'utilisateur (extrait après validation) et l'action sont journalisés (ex: `User admin connected`).
3. **Valider toutes les entrées côté serveur** : 
   - L'API Gateway utilise **Pydantic** (`BaseModel`, `Field`) pour imposer un typage fort, des longueurs minimales et maximales avant que la requête n'atteigne la logique métier.
4. **Contrôler les rôles et les permissions** : 
   - Implémentation complète du RBAC. Les routes sensibles (comme l'audit ou l'émission de jugement) vérifient explicitement `user.get("role") in ["administrateur", "analyste"]`. En cas d'échec, une erreur HTTP 403 est renvoyée et l'incident est journalisé.
5. **Prévoir des messages d'erreur génériques côté client** : 
   - Pour éviter la fuite d'informations (*Information Disclosure*), les erreurs d'authentification renvoient toujours un générique *"Identifiants incorrects"* (et non "Utilisateur inconnu" ou "Mot de passe faux"). Les *stack traces* ne sont jamais exposées.
6. **Prévoir une réflexion sur les risques de sérialisation et de désérialisation** : 
   - Le projet n'utilise **jamais** de bibliothèques vulnérables comme `pickle` en Python (qui permet l'exécution de code arbitraire). Toute la sérialisation est faite en **JSON** pur (validé par Pydantic) pour les requêtes REST, et en **Protocol Buffers** pour gRPC, ce qui garantit que seules des données typées et prévisibles sont désérialisées.
7. **Limiter la taille des entrées** : 
   - Les modèles Pydantic définissent des `max_length` stricts (ex: 50 pour le pseudo, 100 pour le mot de passe, et 10 000 caractères maximum pour le contenu du message) pour prévenir les attaques de type Buffer Overflow ou l'épuisement mémoire.
8. **Prévoir un minimum de protection contre l'abus d'appels** : 
   - Un middleware de **Rate Limiting** (algorithme de fenêtre glissante en mémoire, développé dans `resilience.py`) bloque les adresses IP dépassant un quota défini (ex: prévenir le brute-force ou le spam de l'API d'analyse).
9. **Documenter les menaces principales et les contre-mesures** : 
   - Adressé par la modélisation **STRIDE** détaillée dans la section 4.1 ci-dessus.

---

## 5. Création et Exposition des APIs

La conception, la création et l'exposition des différents services reposent sur des standards modernes et performants :

### 5.1. Choix du Framework : FastAPI
Toutes les APIs REST du projet (Gateway, AuthService, AuditService) ont été développées en utilisant **FastAPI**.
- **Performance et Asynchronisme** : FastAPI est basé sur l'asynchronisme natif de Python (`async`/`await`), ce qui permet à la Gateway de gérer de multiples requêtes de soumission sans bloquer le serveur.
- **Validation intégrée** : Couplé à **Pydantic**, FastAPI s'assure que les charges utiles JSON respectent strictement les schémas définis (types, tailles) avant même d'exécuter la fonction, limitant drastiquement la surface d'attaque.
- **Documentation automatique** : FastAPI génère automatiquement une documentation interactive (Swagger UI/OpenAPI) accessible sur la route `/docs` de chaque service.

### 5.2. Exposition des Services
L'application est découpée en microservices, chacun exposé sur un port dédié de la boucle locale (`127.0.0.1`) pour simuler des serveurs distincts :
- **Serveur ASGI (Uvicorn)** : L'API Gateway, l'AuthService et l'AuditService sont exposés via **Uvicorn**, un serveur web ultra-rapide capable de traiter des requêtes HTTP concurrentes.
- **Serveur gRPC** : L'AnalysisService n'utilise pas HTTP/REST mais est exposé en tant que serveur **gRPC** via la librairie `grpcio`. Il écoute sur le port `8002` et attend des appels RPC binaires, offrant des performances supérieures pour le transfert du contenu des e-mails.

### 5.3. Sécurisation de l'Exposition (CORS)
L'API Gateway sert de point d'entrée unique. Afin de permettre à l'interface Web (qui pourrait techniquement être hébergée sur un autre domaine) de dialoguer avec l'API, nous avons configuré un **Middleware CORS** (`CORSMiddleware`). Bien qu'autorisant `["*"]` pour la facilité de la démonstration locale, cette configuration garantit que les navigateurs modernes acceptent les requêtes asynchrones (`fetch`) issues du frontend JavaScript.

---

## 6. Résilience et Tolérance aux Pannes

### 1. Circuit Breaker (Disjoncteur)
Les communications avec `AuthService` et `AnalysisService` sont enveloppées dans des objets `CircuitBreaker`. Si un nombre de pannes consécutives (3 par défaut) est atteint, le disjoncteur passe à l'état **OPEN**. Les requêtes futures échouent instantanément pour éviter de monopoliser les threads réseau (fail-fast). Après 10 secondes, il tente une reconnexion (HALF-OPEN).

### 2. Moteur de Secours (Fallback)
Si l'**AnalysisService** gRPC est inaccessible, la Gateway ne renvoie pas d'erreur au client. Elle bascule automatiquement sur un **moteur heuristique local** (Fallback). L'utilisateur reçoit son score de risque avec la mention `[FALLBACK]`, assurant la continuité d'activité de la plateforme.

---

## 7. Guide de Démonstration

Pour valider le fonctionnement de la plateforme en soutenance :
1. **Démarrage global** : `python run_all.py` (vérifier que les 4 services s'initialisent correctement).
2. **Peuplement de test** : Lancer `python demo_submissions.py` pour simuler des signalements variés.
3. **Accès Web** :
   - Naviguer sur `http://127.0.0.1:8000`.
   - Créer un nouveau compte via le lien **"Créer un compte"** sur la page de connexion.
   - Se connecter avec le nouveau compte et soumettre un e-mail suspect.
   - Constater le statut "En attente de vérification manuelle...".
   - Se déconnecter, puis se connecter en tant que `analyst` (`analyst123`).
   - Inspecter le signalement, scroller vers le bas (UI améliorée) et cliquer sur **Phishing Confirmé** ou **Faux Positif**.
   - Se déconnecter puis se connecter en tant que `admin` (`admin123`) pour accéder à l'onglet **Journaux d'audit** et vérifier que l'inscription et le jugement manuel ont bien été tracés.
4. **Test de Résilience** :
   - Stopper le script `app/analysis/main.py` (gRPC).
   - Soumettre un e-mail suspect depuis le navigateur.
   - Observer que l'analyse réussit toujours grâce au message `[FALLBACK]` et que le disjoncteur a détecté la coupure.
