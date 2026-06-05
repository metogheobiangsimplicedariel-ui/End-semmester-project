import time
import logging
from collections import defaultdict

logger = logging.getLogger("GatewayResilience")

class RateLimiter:
    """Limiteur de débit de type fenêtre glissante par utilisateur/IP."""
    def __init__(self, max_requests: int = 15, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        # Supprimer les requêtes expirées de la fenêtre
        self.requests[key] = [t for t in self.requests[key] if now - t < self.window_seconds]
        
        if len(self.requests[key]) >= self.max_requests:
            return False
            
        self.requests[key].append(now)
        return True

class CircuitBreakerOpenException(Exception):
    pass

class CircuitBreaker:
    """Disjoncteur (Circuit Breaker) pour protéger les appels aux microservices."""
    def __init__(self, name: str, failure_threshold: int = 3, recovery_timeout: float = 10.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.failure_count = 0
        self.last_failure_time = 0

    def call(self, func, *args, **kwargs):
        now = time.time()
        
        # Si le circuit est ouvert, vérifier si le délai de récupération est expiré
        if self.state == "OPEN":
            if now - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF-OPEN"
                logger.info(f"Circuit Breaker '{self.name}' transitioned to HALF-OPEN. Testing service...")
            else:
                logger.warning(f"Circuit Breaker '{self.name}' is OPEN. Fast-failing call.")
                raise CircuitBreakerOpenException(f"Service '{self.name}' temporairement indisponible (Circuit ouvert)")

        try:
            result = func(*args, **kwargs)
            # Si on était en HALF-OPEN et que l'appel réussit, fermer le circuit
            if self.state == "HALF-OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info(f"Circuit Breaker '{self.name}' successfully reset to CLOSED.")
            elif self.state == "CLOSED":
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = now
            logger.error(f"Failure {self.failure_count}/{self.failure_threshold} on service '{self.name}': {str(e)}")
            
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.error(f"Circuit Breaker '{self.name}' transitioned to OPEN due to consecutive failures.")
            
            raise e
