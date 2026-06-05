import sys
import os
import logging
from concurrent import futures
import grpc

# Configuration du dossier courant et parent pour les imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import analysis_pb2
import analysis_pb2_grpc
from scoring import analyze_email_heuristics
from app.shared.audit_client import send_audit_log

# Configuration de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [ANALYSIS-SERVICE] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AnalysisService")

class AnalysisServiceServicer(analysis_pb2_grpc.AnalysisServiceServicer):
    def AnalyzeEmail(self, request, context):
        try:
            logger.info(f"Received analysis request for Email ID: {request.email_id} from sender: {request.sender}")
            
            # Analyse heuristique
            score, risk_level, justifications = analyze_email_heuristics(
                sender=request.sender,
                subject=request.subject,
                content=request.content,
                urls=list(request.urls),
                has_attachment=request.has_attachment
            )
            
            logger.info(f"Analysis complete for {request.email_id}: Score={score}, Risk={risk_level}")
            
            # Si le risque est ÉLEVÉ, envoyer un log d'audit
            if risk_level == "ÉLEVÉ":
                send_audit_log(
                    service="AnalysisService",
                    event_type="HIGH_RISK_DETECTED",
                    severity="WARNING",
                    message=f"High risk phishing email detected! Sender: {request.sender}, Score: {score}",
                    user_id="SYSTEM"
                )
                
            return analysis_pb2.EmailAnalysisResponse(
                score=score,
                risk_level=risk_level,
                justifications=justifications
            )
        except Exception as e:
            logger.error(f"Error during AnalyzeEmail: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Internal server error during analysis")
            return analysis_pb2.EmailAnalysisResponse()

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    analysis_pb2_grpc.add_AnalysisServiceServicer_to_server(AnalysisServiceServicer(), server)
    server.add_insecure_port('[::]:8002')
    logger.info("Starting AnalysisService gRPC server on port 8002...")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
