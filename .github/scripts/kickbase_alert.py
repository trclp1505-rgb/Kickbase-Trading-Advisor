import os, sys, json, datetime, requests

# ---- Secrets / Env
EMAIL  = os.environ["KICK_USER"]
PASS   = os.environ["KICK_PASS"]
WEBHOOK = os.environ["DISCORD_WEBHOOK"]
LEAGUE_ID = os.environ.get("KICK_LEAGUE_ID","").strip()  # z.B. 5654776
EVENT  = os.environ.get("GITHUB_EVENT_NAME","")

# ---- damit wir aus dem Repo importieren können
sys.path.insert(0, os.getcwd())
from kickbase_api.user import login as kb_login  # <- deine bewährte Login-Funktion!

session = requests.Session()
session.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0"})

def discord_post(text: str):
    while text:
        chunk = text[:1900]
        try:
            requests.post(WEBHOOK, json={"content": chunk, "username":"Kickbase Alarm",
                                         "allowed_mentions":{"parse":[]}}, timeout=20).raise_for_status()
        except Exception: pass
        text = text[1900:]

def kb_auth():
    """Loggt sich mit der Repo-Funktion ein und setzt den Bearer-Token."""
    token = kb_login(EMAIL, PASS)               # wirft bei Fehler eine Exception
    session.headers.update({"Authorization": f"Bearer {token}"})

def league_name_from_id(lid: str) -> str:
    try:
        r = session.get("https://api.kickbase.com/v4/leagues", timeout=15)
        if r.ok and isinstance(r.json(), dict) and "lins" in r.json():
            for L in r.json()["lins"]:
                if str(L.get("i")) == str(lid):
                    return L.get("n") or "(per ID)"
    except Exception:
        pass
    return "(per ID)"

def main():
    # 1) Login (funktionierende Variante)
    try:
        kb_auth()
    except Exception as e:
        discord_post(f"❌ Login fehlgeschlagen: {e}")
        return

    # 2) Liga-ID muss gesetzt sein
    if not LEAGUE_ID:
        discord_post("ℹ️ Bitte Secret **KICK_LEAGUE_ID** setzen (z. B. 5654776).")
        return

    lname = league_name_from_id(LEAGUE_ID)

    # 3) Aktivmeldung beim manuellen Start
    if EVENT == "workflow_dispatch":
        ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        discord_post(f"✅ Kickbase-Alarm aktiv – Liga: {lname} (ID: {LEAGUE_ID}) • {ts}")

    # 4) (Platzhalter) Bids-Check – nicht crashen
    try:
        candidates = [
            f"https://api.kickbase.com/v4/leagues/{LEAGUE_ID}/transfermarket/bids",
            "https://api.kickbase.com/v4/user/bids",
            f"https://api.kickbase.com/v3/leagues/{LEAGUE_ID}/transfermarket/bids",
            "https://api.kickbase.com/v3/user/bids",
        ]
        got = None
        for u in candidates:
            try:
                r = session.get(u, timeout=20)
                if r.ok:
                    got = r.json(); break
            except Exception:
                continue
        if not got:
            return

        items = got.get("bids") or got.get("items") if isinstance(got, dict) else (got if isinstance(got, list) else [])
        not_highest = 0
        for it in items:
            mine  = (it.get("isMine") or it.get("mine")) is True
            high  = (it.get("isHighestBidder") or it.get("highest")) is True
            over  = (it.get("overbid") or it.get("isOverbid")) is True
            if mine and (over or not high):
                not_highest += 1

        if EVENT == "workflow_dispatch":
            discord_post(f"ℹ️ Schnellcheck: {not_highest} deiner Gebote sind aktuell NICHT Höchstgebot.")
    except Exception as e:
        discord_post(f"⚠️ Scan-Fehler: {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()
