import time
import requests

API_URL = "http://127.0.0.1:8000/api"

DEMO_EMAILS = [
    {
        "sender": "professeur.dupont@universite.fr",
        "subject": "Notes du projet final de Cloud Computing",
        "content": "Bonjour à tous,\n\nVous trouverez vos notes du projet de Cloud Computing sur l'ENT. Le cours est terminé, merci pour votre implication.\n\nCordialement,\nProf. Dupont",
        "urls": ["https://ent.universite.fr/notes"],
        "has_attachment": False
    },
    {
        "sender": "security-update@paypal-security.com",
        "subject": "Urgent : Suspension immédiate de votre compte PayPal",
        "content": "Cher client,\n\nNous avons détecté une connexion suspecte sur votre compte. Veuillez cliquer ici pour vérifier votre compte immédiatement et éviter une suspension permanente.\n\nL'équipe de sécurité PayPal.",
        "urls": ["http://verification-portal-paypal.com/login"],
        "has_attachment": False
    },
    {
        "sender": "impots-remboursement-en-ligne@gmail.com",
        "subject": "Remboursement d'impôt 2026 - Action requise sous 48h",
        "content": "Madame, Monsieur,\n\nAprès calculs, vous êtes éligible à un remboursement d'impôt de 450,00 €. Veuillez télécharger la pièce jointe justificative et vous connecter sur l'IP du portail sécurisé pour recevoir vos fonds.\n\nCordialement,\nLe Trésor Public.",
        "urls": ["http://192.168.1.105/remboursement"],
        "has_attachment": True
    }
]

def seed_demo_data():
    print("Connexion en tant qu'analyste pour injecter les données de test...")
    try:
        # 1. Login
        login_res = requests.post(f"{API_URL}/auth/login", json={
            "username": "analyst",
            "password": "analyst123"
        })
        if login_res.status_code != 200:
            print("[-] Erreur d'authentification. Les services sont-ils démarrés ?")
            return
            
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("[+] Connecté avec succès.")

        # 2. Submit emails
        for i, email in enumerate(DEMO_EMAILS, 1):
            print(f"[+] Soumission de l'e-mail de test n°{i} : '{email['subject']}'")
            res = requests.post(f"{API_URL}/submissions", json=email, headers=headers)
            if res.status_code == 201:
                data = res.json()
                print(f"    -> Risque qualifié : {data['risk_level']} (Score : {data['score']}/100)")
            else:
                print(f"    [-] Erreur lors de la soumission : {res.text}")
                
        print("\n[!] Données de démonstration injectées avec succès.")
    except Exception as e:
        print(f"[-] Erreur de communication : {str(e)}")

if __name__ == "__main__":
    seed_demo_data()
