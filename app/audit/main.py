import os
import sqlite3
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

# Configuration de la journalisation locale de l'AuditService
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [AUDIT-SERVICE] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AuditService")

app = FastAPI(title="AuditService", version="1.0.0")
DB_PATH = os.path.join(os.path.dirname(__file__), "audit.db")

# Modèle de log d'audit reçu
class AuditLogEntry(BaseModel):
    service: str = Field(..., max_length=50)
    event_type: str = Field(..., max_length=50)
    severity: str = Field(..., max_length=10)  # INFO, WARNING, CRITICAL
    message: str = Field(..., max_length=500)
    user_id: str = Field(None, max_length=100)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            service TEXT NOT NULL,
            event_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            user_id TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.post("/log", status_code=status.HTTP_201_CREATED)
async def create_audit_log(entry: AuditLogEntry):
    try:
        timestamp = datetime.utcnow().isoformat() + "Z"
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (timestamp, service, event_type, severity, message, user_id) VALUES (?, ?, ?, ?, ?, ?)",
            (timestamp, entry.service, entry.event_type, entry.severity, entry.message, entry.user_id)
        )
        conn.commit()
        conn.close()
        
        # Log structuré sur la console
        logger.info(f"[{entry.severity}] {entry.service} - {entry.event_type} - {entry.message} (User: {entry.user_id})")
        return {"status": "success", "message": "Log recorded"}
    except Exception as e:
        logger.error(f"Failed to write log: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record log on audit service"
        )

@app.get("/logs")
async def get_audit_logs(limit: int = 100):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to fetch logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve logs"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8003)
