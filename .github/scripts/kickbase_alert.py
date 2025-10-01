import os
import json
import datetime
import requests

# --- Secrets / Env ---
EMAIL        = os.environ["KICK_USER"]
PASS         = os.environ["KICK_PASS"]
WEBHOOK      = os.environ["DISCORD_WEBHOOK"]
LEAGUE_ID    = os.environ.get("KICK_LEAGUE_ID", "").strip()   # z.B. 5654776
LEAGUE_NAME  = os.environ.get("KICK_LEAGUE_NAME", "").strip()
EVENT        = os.environ.get("GITHUB_EVENT_NAME", "")

# --- HTTP Session ---
session = requests.Session()
session.headers.update({
    "Accept": "application/json",
    "User-Agent": "Kickbase/6.0.0 (iPhone; iOS 16.0)"
})

def discord_post(text: str):
    """Postet Text nach Discord (in 1900er Blöcken)."""
    try:
        while text:
            chunk = text[:1900]
            r = requests.post(
                WEBHOOK,
                json={"content": chunk, "username": "Kickbase Alarm", "allowed_mentions":{"parse":[]}},
                timeout=20,
            )
            # Kein harter Abbruch bei Discord-Fehlern
            try:
                r.raise_for_status()
            except Exception:
                print("Discord-Fehler:", r.status_code, r.text[:200])
            text = text[1900:]
    except Exception as e:
        print("Discord-Exception:", e)

def kb_login() -> bool:
    """Login bei Kickbase (inoffizielle API), setzt Bearer-Token. Gibt True/False zurück."""
    headers_like_app = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Kickbase/6.0.0 (iPhone; iOS 16.0)",
        "X-App-Version": "6.0.0",
        "X-Platform": "ios"
    }
    try:
        r = session.post(
            "https://api.kickbase.com/v4/user/login",
            json={"email": EMAIL, "password": PASS},
            headers=headers_like_app,
            timeout=20
        )
        if not r.ok:
            discord_post(f"❌ Login fehlgeschlagen: {r.status_code} {r.text[:120]}")
            return False
        j = r.json()
        token = j.get("token") or j.get("accessToken")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
            return True
        discord_post("❌ Login fehlgeschlagen: kein Token erhalten.")
        return False
    except Exception as e:
        discord_post(f"❌ Login-Exception: {type(e).__name__}: {e}")
        return False

def get_league_name_from_api(lid: str) -> str:
    """Versucht, den Anzeigenamen der Liga anhand der ID zu finden."""
    try:
        # Der funktionierende Endpoint laut deinem Debug: /v4/leagues liefert ein Dict mit 'lins'
        r = session.get("https://api.kickbase.com/v4/leagues", timeout=15)
        if r.ok:
            data = r.json()
            if isinstance(data, dict) and "lins" in data:
                for L in data["lins"]:
                    if str(L.get("i")) == str(lid):
                        return L.get("n") or "(per ID)"
        # Fallbacks ignorieren wir still; geben "(per ID)" zurück
    except Exception:
        pass
    return "(per ID)"

def main():
    # 1) Login
    if not kb_login():
        # Fehler wurde bereits an Discord gepostet; NICHT crashen
        return

    # 2) Liga bestimmen (ID first)
    lid = LEAGUE_ID if LEAGUE_ID else ""
    lname = LEAGUE_NAME if LEAGUE_NAME else ""
    if lid and not lname:
        lname = get_league_name_from_api(lid)

    if not lid:
        # Kein Secret gesetzt: Nutzerfreundliche Meldung
        discord_post("ℹ️ Bitte setze das Secret **KICK_LEAGUE_ID** (z. B. 5654776). Dann weiß ich, welche Liga ich überwachen soll.")
        return

    # 3) Aktiv-Meldung (beim manuellen Start immer; bei Cron nur, wenn du willst)
    if EVENT == "workflow_dispatch":
        ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        discord_post(f"✅ Kickbase-Alarm aktiv – Liga: {lname} (ID: {lid}) • {ts}")

    # 4) HIER kommt später die Überbietungs-Logik rein (derzeit nur Platzhalter)
    #    Wir fangen alle Fehler intern ab, damit der Job nie rot wird.
    try:
        # Beispiel-Endpoints (je nach API-Version variabel):
        candidates = [
            f"https://api.kickbase.com/v4/leagues/{lid}/transfermarket/bids",
            "https://api.kickbase.com/v4/user/bids",
            f"https://api.kickbase.com/v3/leagues/{lid}/transfermarket/bids",
            "https://api.kickbase.com/v3/user/bids",
        ]
        # Versuch, irgendeinen Bids-Endpoint zu erwischen
        got = None
        used = ""
        for u in candidates:
            try:
                r = session.get(u, timeout=20)
                if r.ok:
                    got = r.json()
                    used = u
                    break
            except Exception:
                continue

        if got is None:
            # leise bleiben – oder hier debuggen:
            # discord_post("⚠️ Konnte aktuell keine Bids laden (API kann variieren).")
            return

        # Items extrahieren (API unterscheidet sich je nach Version)
        if isinstance(got, dict):
            items = got.get("bids") or got.get("items") or []
        elif isinstance(got, list):
            items = got
        else:
            items = []

        # Minimal-Scan: nur zählen, nichts crashen
        mine_not_highest = 0
        for it in items:
            mine    = (it.get("isMine") or it.get("mine")) is True
            highest = (it.get("isHighestBidder") or it.get("highest")) is True
            over    = (it.get("overbid") or it.get("isOverbid")) is True
            if mine and (over or not highest):
                mine_not_highest += 1

        # Optional: Bei manuellem Start kurz Statistik posten
        if EVENT == "workflow_dispatch":
            discord_post(f"ℹ️ Schneller Check: {mine_not_highest} deiner Gebote sind aktuell nicht Höchstgebot.")

    except Exception as e:
        # Niemals crashen – wir posten den Fehler und gehen raus
        discord_post(f"⚠️ Scan-Fehler: {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()
