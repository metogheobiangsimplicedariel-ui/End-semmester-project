import os
import sys
import json
import sqlite3
import logging
import requests
import grpc
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, Depends, status, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Imports internes
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app.shared.audit_client import send_audit_log
from app.gateway.resilience import RateLimiter, CircuitBreaker, CircuitBreakerOpenException
from app.analysis.scoring import analyze_email_heuristics

# Configuration de la journalisation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [GATEWAY] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Gateway")

app = FastAPI(title="SubmissionService / API Gateway", version="1.0.0")

# Autoriser CORS pour simplifier les tests locaux
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.path.join(os.path.dirname(__file__), "submissions.db")
AUTH_SERVICE_URL = "http://127.0.0.1:8001"
AUDIT_SERVICE_URL = "http://127.0.0.1:8003"
ANALYSIS_SERVICE_GRPC = "127.0.0.1:8002"

# Initialisation des disjoncteurs et du rate limiter
auth_cb = CircuitBreaker("AuthService", failure_threshold=3, recovery_timeout=10.0)
analysis_cb = CircuitBreaker("AnalysisService", failure_threshold=3, recovery_timeout=10.0)
rate_limiter = RateLimiter(max_requests=30, window_seconds=60)  # Limite globale

# Modèles Pydantic pour validation stricte
class EmailSubmission(BaseModel):
    sender: str = Field(..., max_length=150, description="Adresse e-mail de l'expéditeur")
    subject: str = Field(..., max_length=200, description="Objet de l'e-mail")
    content: str = Field(..., max_length=10000, description="Contenu textuel (limité à 10 KB)")
    urls: list[str] = Field(default=[], max_items=20, description="Liste d'URLs détectées")
    has_attachment: bool = Field(default=False, description="Présence de pièce jointe")

class UserLogin(BaseModel):
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=100)

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)

class JudgementRequest(BaseModel):
    judgement: str = Field(..., max_length=50, description="Jugement manuel (ex: Phishing Confirmé, Faux Positif)")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            subject TEXT NOT NULL,
            content TEXT NOT NULL,
            urls TEXT NOT NULL,
            has_attachment INTEGER NOT NULL,
            date_submission TEXT NOT NULL,
            user_submitted TEXT NOT NULL,
            score INTEGER NOT NULL,
            risk_level TEXT NOT NULL,
            justifications TEXT NOT NULL,
            manual_judgement TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Extraction et validation de token (Dépendance)
async def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton d'authentification manquant ou invalide"
        )
    
    token = auth_header.split(" ")[1]
    
    # Appel à l'AuthService avec Circuit Breaker
    def call_auth_service():
        response = requests.post(
            f"{AUTH_SERVICE_URL}/validate",
            json={"token": token},
            timeout=2.0
        )
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expirée ou non autorisée"
            )
        else:
            raise Exception("AuthService error response")

    try:
        user_info = auth_cb.call(call_auth_service)
        return user_info
    except CircuitBreakerOpenException:
        logger.error("AuthService Circuit is OPEN. Unable to validate session.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Le service d'authentification est indisponible. Veuillez réessayer ultérieurement."
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error calling AuthService: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Erreur d'authentification ou service injoignable"
        )

# Application du Rate Limiting
@app.middleware("http")
async def apply_rate_limiting(request: Request, call_next):
    client_ip = request.client.host
    if not rate_limiter.is_allowed(client_ip):
        # Envoyer log audit pour tentative d'abus
        send_audit_log("Gateway", "RATE_LIMIT_EXCEEDED", "WARNING", f"Rate limit exceeded by IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de requêtes. Veuillez patienter une minute."
        )
    return await call_next(request)

# --- Routes API ---

@app.post("/api/auth/login")
async def login(credentials: UserLogin):
    try:
        response = requests.post(f"{AUTH_SERVICE_URL}/login", json=credentials.dict(), timeout=2.5)
        if response.status_code == 200:
            return response.json()
        raise HTTPException(status_code=response.status_code, detail=response.json().get("detail", "Échec de connexion"))
    except requests.exceptions.RequestException as e:
        logger.error(f"AuthService unavailable: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Le service d'authentification est actuellement inaccessible."
        )

@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
async def register_user(user: UserRegister):
    """Inscription publique. Le rôle est fixé à 'utilisateur' pour tous les auto-inscriptions."""
    payload = {
        "username": user.username,
        "password": user.password,
        "role": "utilisateur"  # Rôle forcé : impossible d'élever ses privilèges via cet endpoint
    }
    try:
        response = requests.post(f"{AUTH_SERVICE_URL}/register", json=payload, timeout=2.5)
        if response.status_code == 200:
            send_audit_log("Gateway", "USER_REGISTERED", "INFO", f"New user self-registered: {user.username}")
            return {"status": "success", "message": f"Compte créé avec succès. Vous pouvez maintenant vous connecter."}
        raise HTTPException(status_code=response.status_code, detail=response.json().get("detail", "Erreur lors de l'inscription"))
    except requests.exceptions.RequestException as e:
        logger.error(f"AuthService unavailable during register: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Le service d'authentification est actuellement inaccessible."
        )

@app.post("/api/submissions", status_code=status.HTTP_201_CREATED)
async def submit_email(email: EmailSubmission, user: dict = Depends(get_current_user)):
    username = user.get("username", "unknown")
    email_id = f"SUB-{int(datetime.utcnow().timestamp())}"
    
    # Appel de l'AnalysisService via gRPC (avec circuit breaker et timeout)
    def call_analysis_service():
        import app.analysis.analysis_pb2 as pb2
        import app.analysis.analysis_pb2_grpc as pb2_grpc
        
        # gRPC avec timeout
        with grpc.insecure_channel(ANALYSIS_SERVICE_GRPC) as channel:
            stub = pb2_grpc.AnalysisServiceStub(channel)
            req = pb2.EmailAnalysisRequest(
                email_id=email_id,
                sender=email.sender,
                subject=email.subject,
                content=email.content,
                urls=email.urls,
                has_attachment=email.has_attachment
            )
            # Timeout de 2.0 secondes
            response = stub.AnalyzeEmail(req, timeout=2.0)
            return {
                "score": response.score,
                "risk_level": response.risk_level,
                "justifications": list(response.justifications)
            }

    # Résilience : Appel gRPC avec Circuit Breaker et Fallback local
    is_fallback = False
    try:
        analysis_result = analysis_cb.call(call_analysis_service)
    except Exception as e:
        logger.warning(f"AnalysisService (gRPC) failed or circuit open. Using local fallback engine: {str(e)}")
        # Fallback local utilisant directement notre moteur d'analyse python
        score, risk_level, justifications = analyze_email_heuristics(
            sender=email.sender,
            subject=email.subject,
            content=email.content,
            urls=email.urls,
            has_attachment=email.has_attachment
        )
        justifications.append("[FALLBACK] Analyse effectuée par le serveur de secours (mode dégradé)")
        analysis_result = {
            "score": score,
            "risk_level": risk_level,
            "justifications": justifications
        }
        is_fallback = True
        
        # Envoyer une alerte d'audit sur l'utilisation du fallback
        send_audit_log("Gateway", "FALLBACK_ENGINE_USED", "WARNING", f"AnalysisService gRPC failed. Fallback triggered for {email_id}.")

    # Stockage en base locale SQLite de la Gateway
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"
    cursor.execute("""
        INSERT INTO submissions (sender, subject, content, urls, has_attachment, date_submission, user_submitted, score, risk_level, justifications)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        email.sender,
        email.subject,
        email.content,
        json.dumps(email.urls),
        1 if email.has_attachment else 0,
        now_str,
        username,
        analysis_result["score"],
        analysis_result["risk_level"],
        json.dumps(analysis_result["justifications"])
    ))
    conn.commit()
    submission_id = cursor.lastrowid
    conn.close()

    # Log d'audit de soumission réussie
    send_audit_log(
        service="Gateway",
        event_type="EMAIL_SUBMITTED",
        severity="INFO",
        message=f"Email submitted by {username}. Risk qualified: {analysis_result['risk_level']} (Score: {analysis_result['score']})",
        user_id=username
    )

    return {
        "id": submission_id,
        "email_id": email_id,
        "sender": email.sender,
        "subject": email.subject,
        "score": analysis_result["score"],
        "risk_level": analysis_result["risk_level"],
        "justifications": analysis_result["justifications"],
        "fallback_used": is_fallback
    }

@app.get("/api/submissions")
async def list_submissions(
    sender: str = Query(None),
    risk_level: str = Query(None),
    keyword: str = Query(None),
    user: dict = Depends(get_current_user)
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM submissions WHERE 1=1"
    params = []
    
    # Cloisonnement strict des données : les utilisateurs simples ne voient que leurs propres signalements
    if user.get("role") not in ["administrateur", "analyste"]:
        query += " AND user_submitted = ?"
        params.append(user.get("username"))
        
    if sender:
        query += " AND sender LIKE ?"
        params.append(f"%{sender}%")
    if risk_level:
        query += " AND risk_level = ?"
        params.append(risk_level.upper())
    if keyword:
        query += " AND (subject LIKE ? OR content LIKE ?)"
        params.append(f"%{keyword}%")
        params.append(f"%{keyword}%")
        
    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        d = dict(row)
        d["urls"] = json.loads(d["urls"])
        d["justifications"] = json.loads(d["justifications"])
        result.append(d)
        
    return result

@app.get("/api/submissions/{sub_id}")
async def get_submission(sub_id: int, user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM submissions WHERE id = ?", (sub_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Signalement introuvable")
        
    d = dict(row)
    
    # Vérification d'autorisation (RBAC et propriété)
    if user.get("role") not in ["administrateur", "analyste"] and d["user_submitted"] != user.get("username"):
        raise HTTPException(status_code=403, detail="Accès refusé à ce signalement")
        
    d["urls"] = json.loads(d["urls"])
    d["justifications"] = json.loads(d["justifications"])
    return d

@app.post("/api/submissions/{sub_id}/judgement")
async def add_manual_judgement(sub_id: int, req: JudgementRequest, user: dict = Depends(get_current_user)):
    if user.get("role") not in ["administrateur", "analyste"]:
        raise HTTPException(status_code=403, detail="Seul un analyste ou administrateur peut émettre un jugement")
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM submissions WHERE id = ?", (sub_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Signalement introuvable")
        
    cursor.execute("UPDATE submissions SET manual_judgement = ? WHERE id = ?", (req.judgement, sub_id))
    conn.commit()
    conn.close()
    
    send_audit_log("Gateway", "MANUAL_JUDGEMENT_ADDED", "INFO", f"User {user.get('username')} set judgement '{req.judgement}' on sub_id {sub_id}")
    return {"status": "success", "judgement": req.judgement}

@app.get("/api/audit/logs")
async def get_audit_logs(limit: int = 50, user: dict = Depends(get_current_user)):
    # Contrôle de rôle strict (Sécurité by Design)
    if user.get("role") != "administrateur":
        send_audit_log("Gateway", "UNAUTHORIZED_ACCESS", "CRITICAL", f"User {user.get('username')} tried to access audit logs without administrator role", user.get("username"))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé. Rôle administrateur requis."
        )
        
    try:
        response = requests.get(f"{AUDIT_SERVICE_URL}/logs?limit={limit}", timeout=2.0)
        if response.status_code == 200:
            return response.json()
        raise Exception()
    except Exception as e:
        logger.error(f"AuditService unavailable: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Impossible de contacter le service d'audit"
        )

@app.get("/api/health")
async def health_check():
    # Vérification rapide de chaque sous-service (sans planter)
    status_auth = "DOWN"
    status_analysis = "DOWN"
    status_audit = "DOWN"
    
    try:
        if requests.get(f"{AUTH_SERVICE_URL}/docs", timeout=1.0).status_code == 200:
            status_auth = "UP"
    except Exception:
        pass
        
    try:
        # Test de connexion socket simple vers port gRPC
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(("127.0.0.1", 8002))
        s.close()
        status_analysis = "UP"
    except Exception:
        pass
        
    try:
        if requests.get(f"{AUDIT_SERVICE_URL}/logs?limit=1", timeout=1.0).status_code == 200:
            status_audit = "UP"
    except Exception:
        pass
        
    return {
        "gateway": "UP",
        "auth_service": status_auth,
        "analysis_service": status_analysis,
        "audit_service": status_audit
    }

# --- Service des fichiers statiques (Dashboard Web) ---

# Servir le tableau de bord
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Dashboard UI not found</h1>"

# Si on veut monter les fichiers statiques (images, js, css)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Redirection racine vers le dashboard
@app.get("/", response_class=HTMLResponse)
async def root():
    return await dashboard()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
