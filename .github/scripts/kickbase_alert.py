import os, requests, datetime, json
import sys, os, requests, datetime, json
sys.path.insert(0, os.getcwd())  # erlaubt Import aus deinem Repo
from kickbase_api.user import login as kb_login

EMAIL   = os.environ["KICK_USER"]
PASS    = os.environ["KICK_PASS"]
WEBHOOK = os.environ["DISCORD_WEBHOOK"]
LEAGUE_WANTED = os.environ.get("KICK_LEAGUE_NAME", "").strip()
LEAGUE_ID = os.environ.get("KICK_LEAGUE_ID", "").strip()
EVENT = os.environ.get("GITHUB_EVENT_NAME","")

session = requests.Session()
session.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0"})

def discord_post(text: str):
    while text:
        chunk = text[:1900]
        r = requests.post(WEBHOOK, json={"content": chunk, "username": "Kickbase Alarm"}, timeout=20)
        try:
            r.raise_for_status()
        except Exception as e:
            print("Discord Fehler:", e, r.text)
        text = text[1900:]

def login():
    token = kb_login(EMAIL, PASS)   # nutzt die getestete Funktion aus deinem Repo
    session.headers.update({"Authorization": f"Bearer {token}"})
    # direkt alle Ligen abholen
    r = session.get("https://api.kickbase.com/leagues", timeout=20)
    if r.ok:
        return {"leagues": r.json()}
    return {"leagues": []}


def main():
    try:
        lj = login()

        # Debug-Ausgabe: Login JSON dumpen
        try:
            discord_post("Login JSON:\n" + json.dumps(lj, indent=2)[:1800])
        except Exception as e:
            discord_post(f"Login JSON nicht dumpbar: {e}")

        # Verschiedene Endpoints für Ligen testen
        for u in [
            "https://api.kickbase.com/v4/user/leagues",
            "https://api.kickbase.com/v4/leagues",
            "https://api.kickbase.com/v3/leagues",
            "https://api.kickbase.com/leagues",
        ]:
            try:
                r = session.get(u, timeout=15)
                if r.ok:
                    data = r.json()
                    preview = json.dumps(data, indent=2)[:1800]
                    discord_post(f"Ligen von {u}:\n{preview}")
                else:
                    discord_post(f"{u} → {r.status_code} {r.text[:100]}")
            except Exception as e:
                discord_post(f"{u} → Fehler: {e}")

        discord_post("✅ Debug fertig – such dir im JSON deine Liga-ID/Name raus.")

    except Exception as e:
        discord_post(f"❌ Login/Liga fehlgeschlagen: {e}")
        return

if __name__ == "__main__":
    main()
