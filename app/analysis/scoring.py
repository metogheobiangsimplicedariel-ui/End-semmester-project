import re
from urllib.parse import urlparse

# Mots manipulateurs ou urgents
URGENT_WORDS = [
    r"urgent", r"immédiat", r"action requise", r"suspendu", r"cliquez ici",
    r"gagner", r"lot", r"facture impayée", r"vérifier votre compte",
    r"sécurité de votre compte", r"connexion suspecte", r"mise à jour requise",
    r"impôt", r"remboursement", r"cadeau", r"gratuit", r"gagnant"
]

SUSPICIOUS_DOMAINS = [
    "paypal-security", "bank-login", "secure-update", "verification-portal",
    "win-free-gift", "support-alert", "signin-verification", "webmail-update"
]

def analyze_email_heuristics(sender: str, subject: str, content: str, urls: list[str], has_attachment: bool) -> tuple[int, str, list[str]]:
    score = 0
    justifications = []
    
    # 1. Analyse du contenu textuel (Mots-clés)
    combined_text = (subject + " " + content).lower()
    matched_words = []
    for word in URGENT_WORDS:
        if re.search(word, combined_text):
            matched_words.append(word)
            
    if matched_words:
        # 10 points par mot-clé suspect, max 30
        kw_score = min(len(matched_words) * 10, 30)
        score += kw_score
        justifications.append(f"Mots-clés urgents/suspects détectés ({kw_score} pts) : {', '.join(matched_words[:3])}")
        
    # 2. Analyse de l'expéditeur
    sender_lower = sender.lower()
    sender_domain = ""
    if "@" in sender_lower:
        sender_domain = sender_lower.split("@")[-1]
    
    # Domaines gratuits suspectés s'ils usurpent une identité d'entreprise dans le nom
    # Ex: "support-paypal@gmail.com"
    brand_keywords = ["paypal", "netflix", "apple", "google", "microsoft", "amazon", "banque"]
    is_free_domain = any(domain in sender_domain for domain in ["gmail.com", "outlook.com", "yahoo.", "hotmail."])
    if is_free_domain:
        matched_brands = [b for b in brand_keywords if b in sender_lower.split("@")[0]]
        if matched_brands:
            score += 25
            justifications.append(f"Usurpation d'identité suspectée : expéditeur utilise un domaine gratuit mais contient des mots clés de marque ({matched_brands[0]}) (25 pts)")

    # 3. Analyse des URLs
    if urls:
        score += 10  # Avoir des URLs augmente légèrement le risque
        justifications.append("Le message contient des liens externes (10 pts)")
        
        ip_url_detected = False
        susp_domain_detected = False
        mismatch_detected = False
        
        for url in urls:
            try:
                parsed = urlparse(url)
                netloc = parsed.netloc.lower()
                
                # Détection adresse IP brute dans l'URL
                if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?$", netloc):
                    ip_url_detected = True
                
                # Détection domaines suspects
                if any(susp in netloc for susp in SUSPICIOUS_DOMAINS):
                    susp_domain_detected = True
                    
                # Détection de l'écart expéditeur/domaine (si expéditeur a un domaine valide)
                if sender_domain and not is_free_domain:
                    # Si le domaine de l'URL n'est pas le domaine de l'expéditeur ou un sous-domaine
                    if netloc and not netloc.endswith(sender_domain):
                        # Pour éviter de pénaliser les CDN/domaines connus, on pénalise si les mots de l'expéditeur diffèrent complètement
                        mismatch_detected = True
            except Exception:
                pass
                
        if ip_url_detected:
            score += 20
            justifications.append("Lien avec adresse IP brute détecté (20 pts)")
        if susp_domain_detected:
            score += 20
            justifications.append("Lien pointant vers un domaine suspect/usurpé détecté (20 pts)")
        if mismatch_detected:
            score += 15
            justifications.append("Écart détecté entre le domaine de l'expéditeur et les liens du message (15 pts)")
            
    # 4. Pièces jointes suspectes
    if has_attachment:
        # Dans un vrai cas, on regarderait l'extension. Ici on attribue un score si l'utilisateur indique qu'il y en a une.
        # Si de plus le sujet contient des termes d'urgence : double risque
        score += 15
        justifications.append("Présence d'une pièce jointe suspecte (15 pts)")
        
        # Détection d'extensions suspectes annoncées dans le sujet ou métadonnées
        suspicious_exts = [".exe", ".scr", ".zip", ".rar", ".pdf.exe", ".vbs"]
        found_ext = [ext for ext in suspicious_exts if ext in combined_text]
        if found_ext:
            score += 15
            justifications.append(f"Extension de fichier suspecte détectée dans les métadonnées ({found_ext[0]}) (15 pts)")

    # Plafonner le score à 100
    score = min(score, 100)
    
    # Qualification du risque
    if score >= 60:
        risk_level = "ÉLEVÉ"
    elif score >= 30:
        risk_level = "MOYEN"
    else:
        risk_level = "FAIBLE"
        if not justifications:
            justifications.append("Aucun indicateur de phishing détecté.")
            
    return score, risk_level, justifications
