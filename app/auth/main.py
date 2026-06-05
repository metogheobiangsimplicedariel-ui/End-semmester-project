import os
import sys
import sqlite3
import hashlib
import hmac
import json
import base64
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

# Ajout du dossier parent au path pour importer app.shared
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app.shared.audit_client import send_audit_log

app = FastAPI(title="AuthService", version="1.0.0")
DB_PATH = os.path.join(os.path.dirname(__file__), "auth.db")
SECRET_KEY = b"phishing-platform-very-secret-key-12345"

# Modèles Pydantic
class LoginRequest(BaseModel):
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=100)

class TokenValidationRequest(BaseModel):
    token: str

class UserCreate(BaseModel):
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=100)
    role: str = Field(..., max_length=20) # administrateur, analyste

# Helper functions pour la sécurité
def hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return pwd_hash.hex(), salt.hex()

def verify_password(password: str, hashed: str, salt_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    new_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(new_hash, hashed)

def create_signed_token(username: str, role: str) -> str:
    exp = (datetime.utcnow() + timedelta(hours=4)).timestamp()
    payload = {"username": username, "role": role, "exp": exp}
    payload_json = json.dumps(payload).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode().rstrip("=")
    
    # Signature HMAC-SHA256
    sig = hmac.new(SECRET_KEY, payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"

def verify_signed_token(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        
        # Vérifier la signature
        expected_sig = hmac.new(SECRET_KEY, payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        
        # Décoder le payload
        padding = "=" * (4 - len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64 + padding).decode()
        payload = json.loads(payload_json)
        
        # Vérifier l'expiration
        if datetime.utcnow().timestamp() > payload.get("exp", 0):
            return None
            
        return payload
    except Exception:
        return None

# Initialisation DB
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)
    conn.commit()
    
    # Ajouter des utilisateurs par défaut si vide
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        # Création admin
        h1, s1 = hash_password("admin123")
        cursor.execute("INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
                       ("admin", h1, s1, "administrateur"))
        # Création analyste
        h2, s2 = hash_password("analyst123")
        cursor.execute("INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
                       ("analyst", h2, s2, "analyste"))
        conn.commit()
        
    conn.close()

init_db()

@app.post("/login")
async def login(req: LoginRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, salt, role FROM users WHERE username = ?", (req.username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row or not verify_password(req.password, row[0], row[1]):
        # Audit log échec de connexion (sans logger le mot de passe!)
        send_audit_log("AuthService", "LOGIN_FAILED", "WARNING", f"Failed login attempt for user: {req.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects"
        )
        
    role = row[2]
    token = create_signed_token(req.username, role)
    
    # Audit log succès
    send_audit_log("AuthService", "LOGIN_SUCCESS", "INFO", f"User {req.username} logged in successfully", req.username)
    return {"token": token, "username": req.username, "role": role}

@app.post("/validate")
async def validate_token(req: TokenValidationRequest):
    payload = verify_signed_token(req.token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré"
        )
    return payload

@app.post("/register")
async def register(user: UserCreate):
    # Endpoint restreint par l'API Gateway aux administrateurs
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        h, s = hash_password(user.password)
        cursor.execute("INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
                       (user.username, h, s, user.role))
        conn.commit()
        send_audit_log("AuthService", "USER_CREATED", "INFO", f"New user created: {user.username} with role {user.role}")
        return {"status": "success", "message": f"User {user.username} registered"}
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom d'utilisateur déjà pris"
        )
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
