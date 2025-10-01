import os, requests, datetime, json

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
    headers_like_app = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Kickbase/6.0.0 (iPhone; iOS 16.0)",
        "X-App-Version": "6.0.0",
        "X-Platform": "ios"
    }
    r = session.post("https://api.kickbase.com/v4/user/login",
                     json={"email": EMAIL, "password": PASS},
                     headers=headers_like_app,
                     timeout=20)
    if not r.ok:
        raise RuntimeError(f"Login fehlgeschlagen: {r.status_code} {r.text[:200]}")
    j = r.json()
    token = j.get("token") or j.get("accessToken")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    return j

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
