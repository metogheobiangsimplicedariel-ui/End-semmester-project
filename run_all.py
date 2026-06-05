import sys
import os
import subprocess
import time
import threading

# Configuration du chemin d'accès Python de l'environnement virtuel
if sys.platform == "win32":
    python_bin = os.path.join(os.path.dirname(__file__), ".venv", "Scripts", "python.exe")
else:
    python_bin = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python")

if not os.path.exists(python_bin):
    python_bin = sys.executable  # Fallback sur l'interpréteur courant

services = [
    {"name": "AUDIT-SERVICE   ", "script": "app/audit/main.py"},
    {"name": "AUTH-SERVICE    ", "script": "app/auth/main.py"},
    {"name": "ANALYSIS-SERVICE", "script": "app/analysis/main.py"},
    {"name": "API-GATEWAY     ", "script": "app/gateway/main.py"},
]

processes = []

def log_stream(name, stream):
    for line in iter(stream.readline, b''):
        decoded_line = line.decode('utf-8', errors='ignore').strip()
        if decoded_line:
            print(f"[{name}] {decoded_line}")

def main():
    print("=" * 70)
    print("      Lancement de la Plateforme Distribuée PhishShield      ")
    print("=" * 70)
    print(f"Interpréteur Python utilisé : {python_bin}")
    print("Démarrage des services...\n")

    for s in services:
        script_path = os.path.join(os.path.dirname(__file__), s["script"])
        if not os.path.exists(script_path):
            print(f"[-] Erreur : le fichier {script_path} n'existe pas.")
            sys.exit(1)
            
        print(f"[+] Lancement de {s['name']}...")
        p = subprocess.Popen(
            [python_bin, s["script"]],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(__file__)
        )
        processes.append((s["name"], p))
        
        # Lancer des threads de lecture des flux de logs pour la console
        t_out = threading.Thread(target=log_stream, args=(s["name"], p.stdout), daemon=True)
        t_err = threading.Thread(target=log_stream, args=(s["name"], p.stderr), daemon=True)
        t_out.start()
        t_err.start()
        
        time.sleep(0.5)  # Légère pause pour éviter les conflits d'initialisation de port

    print("\n[!] Tous les services sont démarrés.")
    print("[!] Ouvrez http://127.0.0.1:8000 pour accéder au Tableau de bord Web.")
    print("[!] Exécutez 'python client.py' dans une autre console pour utiliser le client CLI.")
    print("[!] Appuyez sur Ctrl+C pour arrêter proprement tous les services.\n")

    try:
        while True:
            time.sleep(1)
            # Vérifier si l'un des processus s'est arrêté de manière inattendue
            for name, p in processes:
                if p.poll() is not None:
                    print(f"[-] Le service {name} s'est arrêté avec le code : {p.returncode}")
                    raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("\n\nArrêt de tous les services en cours...")
        for name, p in processes:
            print(f"[-] Arrêt de {name}...")
            p.terminate()
            p.wait()
        print("[+] Plateforme PhishShield arrêtée.")

if __name__ == "__main__":
    main()
