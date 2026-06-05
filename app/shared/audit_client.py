import requests
import logging

logger = logging.getLogger("AuditClient")

AUDIT_SERVICE_URL = "http://127.0.0.1:8003/log"

def send_audit_log(service: str, event_type: str, severity: str, message: str, user_id: str = None):
    payload = {
        "service": service,
        "event_type": event_type,
        "severity": severity,
        "message": message,
        "user_id": user_id
    }
    try:
        # Timeout court pour ne pas bloquer les services en cas de panne de l'AuditService
        response = requests.post(AUDIT_SERVICE_URL, json=payload, timeout=1.5)
        if response.status_code != 201:
            logger.error(f"Failed to send audit log, status code: {response.status_code}")
    except Exception as e:
        # Silencieusement échouer ou journaliser localement sans planter le flux principal (résilience)
        logger.warning(f"AuditService unreachable: {str(e)}")
