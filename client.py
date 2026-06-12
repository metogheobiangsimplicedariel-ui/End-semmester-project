import sys
import json
import requests

API_URL = "http://127.0.0.1:8000/api"
session_token = None
current_user = None
current_role = None

def print_banner():
    print("=" * 60)
    print("   PhishShield CLI - Détection distribuée de Phishing   ")
    print("=" * 60)

def register():
    print("\n--- Créer un nouveau compte ---")
    username = input("Choisissez un nom d'utilisateur (min. 3 caractères) : ").strip()
    password = input("Choisissez un mot de passe (min. 6 caractères) : ")
    password_confirm = input("Confirmez le mot de passe : ")

    if password != password_confirm:
        print("[-] Les mots de passe ne correspondent pas.")
        return False

    try:
        response = requests.post(f"{API_URL}/auth/register", json={
            "username": username,
            "password": password
        })
        if response.status_code == 201:
            print(f"\n[+] {response.json().get('message', 'Compte créé avec succès !')}")
            return True
        else:
            print(f"[-] Erreur : {response.json().get('detail', 'Inscription impossible')}")
    except Exception as e:
        print(f"[-] Erreur de connexion au serveur : {str(e)}")
    return False

def login():
    global session_token, current_user, current_role
    print("\n--- Connexion à la plateforme ---")
    username = input("Nom d'utilisateur : ").strip()
    password = input("Mot de passe : ")
    
    try:
        response = requests.post(f"{API_URL}/auth/login", json={
            "username": username,
            "password": password
        })
        if response.status_code == 200:
            data = response.json()
            session_token = data["token"]
            current_user = data["username"]
            current_role = data["role"]
            print(f"\n[+] Connexion réussie ! Bienvenue {current_user} ({current_role}).")
            return True
        else:
            print(f"[-] Échec de connexion : {response.json().get('detail', 'Identifiants incorrects')}")
    except Exception as e:
        print(f"[-] Erreur de connexion au serveur : {str(e)}")
    return False

def submit_email():
    if not session_token:
        print("[-] Vous devez être connecté pour effectuer cette action.")
        return

    print("\n--- Soumission d'un e-mail suspect ---")
    sender = input("Expéditeur (ex: security@paypal.com) : ").strip()
    subject = input("Objet de l'e-mail : ").strip()
    
    urls = []
    print("Entrez les URLs détectées (laisser vide et valider pour terminer) :")
    while True:
        url = input(" -> URL : ").strip()
        if not url:
            break
        urls.append(url)
        
    has_attachment_input = input("Présence d'une pièce jointe suspecte (o/N) : ").strip().lower()
    has_attachment = has_attachment_input == 'o'
    
    print("Entrez le contenu ou l'extrait de l'e-mail (Tapez 'FIN' sur une ligne seule pour terminer) :")
    lines = []
    while True:
        line = input()
        if line.strip() == "FIN":
            break
        lines.append(line)
    content = "\n".join(lines)

    headers = {"Authorization": f"Bearer {session_token}"}
    payload = {
        "sender": sender,
        "subject": subject,
        "content": content,
        "urls": urls,
        "has_attachment": has_attachment
    }

    try:
        response = requests.post(f"{API_URL}/submissions", json=payload, headers=headers)
        if response.status_code == 201:
            res = response.json()
            print("\n" + "=" * 50)
            print("         RÉSULTAT DE L'ANALYSE DE PHISHING          ")
            print("=" * 50)
            print(f"ID Signalement : {res['email_id']}")
            print(f"Expéditeur     : {res['sender']}")
            print(f"Objet          : {res['subject']}")
            print(f"Score de risque: {res['score']}/100")
            print(f"Qualification  : {res['risk_level']}")
            print("\nIndicateurs détectés :")
            for j in res['justifications']:
                print(f" - {j}")
            if res.get('fallback_used'):
                print("\n[NOTE] Analyse effectuée par le moteur local de secours.")
            print("=" * 50)
        else:
            print(f"[-] Erreur de soumission : {response.json().get('detail', 'Erreur inconnue')}")
    except Exception as e:
        print(f"[-] Erreur de communication avec le serveur : {str(e)}")

def list_submissions():
    if not session_token:
        print("[-] Vous devez être connecté.")
        return

    print("\n--- Liste des signalements suspectés ---")
    headers = {"Authorization": f"Bearer {session_token}"}
    
    # Options de filtrage optionnelles
    risk = input("Filtrer par risque (FAIBLE/MOYEN/ELEVE ou Entrée pour tout) : ").strip().upper()
    if risk == "ELEVE":
        risk = "ÉLEVÉ"
        
    params = {}
    if risk:
        params["risk_level"] = risk

    try:
        response = requests.get(f"{API_URL}/submissions", headers=headers, params=params)
        if response.status_code == 200:
            submissions = response.json()
            if not submissions:
                print("[*] Aucun signalement enregistré.")
                return
            
            print(f"\n{'ID':<5} | {'Expéditeur':<25} | {'Objet':<25} | {'Risque':<8} | {'Score':<5} | {'Soumis par':<10}")
            print("-" * 85)
            for s in submissions:
                subj = s['subject'][:22] + "..." if len(s['subject']) > 25 else s['subject']
                send = s['sender'][:22] + "..." if len(s['sender']) > 25 else s['sender']
                print(f"{s['id']:<5} | {send:<25} | {subj:<25} | {s['risk_level']:<8} | {s['score']:<5}/100 | {s['user_submitted']:<10}")
        else:
            print(f"[-] Erreur : {response.json().get('detail')}")
    except Exception as e:
        print(f"[-] Erreur lors de la récupération : {str(e)}")

def inspect_submission():
    if not session_token:
        print("[-] Vous devez être connecté.")
        return

    sub_id = input("\nEntrez l'ID du signalement à inspecter : ").strip()
    if not sub_id.isdigit():
        print("[-] ID invalide.")
        return

    headers = {"Authorization": f"Bearer {session_token}"}
    try:
        response = requests.get(f"{API_URL}/submissions/{sub_id}", headers=headers)
        if response.status_code == 200:
            s = response.json()
            print("\n" + "=" * 50)
            print(f"          INSPECTION DU SIGNALEMENT N°{s['id']}          ")
            print("=" * 50)
            print(f"Date de soumission : {s['date_submission']}")
            print(f"Soumis par         : {s['user_submitted']}")
            print(f"Expéditeur         : {s['sender']}")
            print(f"Objet              : {s['subject']}")
            print(f"Pièce jointe       : {'Oui' if s['has_attachment'] else 'Non'}")
            print(f"URLs extraites     : {', '.join(s['urls']) if s['urls'] else 'Aucune'}")
            print(f"Score de risque    : {s['score']}/100 ({s['risk_level']})")
            print("\nIndicateurs retenus :")
            for j in s['justifications']:
                print(f" - {j}")
            print("\nContenu de l'e-mail :")
            print("-" * 50)
            print(s['content'])
            print("-" * 50)
        else:
            print(f"[-] Signalement non trouvé : {response.json().get('detail')}")
    except Exception as e:
        print(f"[-] Erreur : {str(e)}")

def view_audit_logs():
    if not session_token:
        print("[-] Connectez-vous d'abord.")
        return

    if current_role != "administrateur":
        print("[-] Action interdite : rôle administrateur requis.")
        return

    print("\n--- Journaux d'audit de sécurité ---")
    headers = {"Authorization": f"Bearer {session_token}"}
    try:
        response = requests.get(f"{API_URL}/audit/logs", headers=headers)
        if response.status_code == 200:
            logs = response.json()
            print(f"\n{'Date':<20} | {'Service':<15} | {'Événement':<20} | {'Niveau':<8} | {'Message'}")
            print("-" * 100)
            for l in logs:
                date = l['timestamp'][:19]
                print(f"{date:<20} | {l['service']:<15} | {l['event_type']:<20} | {l['severity']:<8} | {l['message']}")
        else:
            print(f"[-] Erreur : {response.json().get('detail')}")
    except Exception as e:
        print(f"[-] Erreur de connexion à l'audit : {str(e)}")

def main():
    print_banner()

    # Menu d'accueil : connexion ou inscription
    while True:
        print("\n=== Bienvenue sur PhishShield ===")
        print("1. Se connecter")
        print("2. Créer un compte")
        print("0. Quitter")
        choice = input("Votre choix : ").strip()

        if choice == "1":
            if login():
                break
        elif choice == "2":
            if register():
                print("[*] Vous pouvez maintenant vous connecter.")
        elif choice == "0":
            print("\nAu revoir !")
            return
        else:
            print("[-] Choix invalide.")

    # Menu principal après connexion
    while True:
        print("\n=== Menu Principal ===")
        print("1. Soumettre un e-mail suspect pour analyse")
        print("2. Consulter la liste des signalements")
        print("3. Inspecter les détails d'un signalement")

        if current_role == "administrateur":
            print("4. Consulter les journaux d'audit (Admin)")

        print("0. Quitter")

        choice = input("Votre choix : ").strip()

        if choice == "1":
            submit_email()
        elif choice == "2":
            list_submissions()
        elif choice == "3":
            inspect_submission()
        elif choice == "4" and current_role == "administrateur":
            view_audit_logs()
        elif choice == "0":
            print("\nAu revoir !")
            break
        else:
            print("[-] Choix invalide.")

if __name__ == "__main__":
    main()
