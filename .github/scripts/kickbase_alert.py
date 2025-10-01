import os, sys, json, datetime, requests

# ---- Secrets / Env
EMAIL         = os.environ["KICK_USER"]
PASS          = os.environ["KICK_PASS"]
WEBHOOK       = os.environ["DISCORD_WEBHOOK"]
LEAGUE_ID     = os.environ.get("KICK_LEAGUE_ID","").strip()  # z.B. 5654776
EVENT         = os.environ.get("GITHUB_EVENT_NAME","")

# ---- damit wir aus dem Repo importieren können (dein funktionierender Login!)
sys.path.insert(0, os.getcwd())
from kickbase_api.user import login as kb_login

session = requests.Session()
# App-ähnliche Default-Header (wie iOS-App)
session.headers.update({
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Kickbase/6.0.0 (iPhone; iOS 16.0)",
    "X-App-Version": "6.0.0",
    "X-Platform": "ios"
})


def discord_post(text: str):
    while text:
        chunk = text[:1900]
        try:
            requests.post(
                WEBHOOK,
                json={"content": chunk, "username":"Kickbase Alarm","allowed_mentions":{"parse":[]}},
                timeout=20
            ).raise_for_status()
        except Exception as e:
            print("Discord-Post Fehler:", e)
        text = text[1900:]

def kb_auth():
    """Loggt sich mit deiner Repo-Funktion ein und setzt den Bearer."""
    token = kb_login(EMAIL, PASS)   # wirft bei Fehler Exception (die fangen wir im main)
    session.headers.update({"Authorization": f"Bearer {token}"})

def league_name_from_id(lid: str) -> str:
    """Nur für Anzeige – versucht Namen per ID aus /v4/leagues ('lins') zu holen."""
    try:
        r = session.get("https://api.kickbase.com/v4/leagues", timeout=15)
        if r.ok:
            data = r.json()
            if isinstance(data, dict) and "lins" in data:
                for L in data["lins"]:
                    if str(L.get("i")) == str(lid):
                        return L.get("n") or "(per ID)"
    except Exception:
        pass
    return "(per ID)"

# ---------- Hilfsfunktionen für Beträge/Zeiten/JSON ----------
def first_ok_json(urls):
    for u in urls:
        try:
            r = session.get(u, timeout=20)
            if r.ok:
                return r.json(), u
        except Exception:
            continue
    return None, None

def get(d, *names, default=None):
    for n in names:
        if isinstance(d, dict) and n in d and d[n] is not None:
            return d[n]
    return default

def eur(x):
    if x is None: return "?"
    try:
        v = float(x)
        if v.is_integer(): v = int(v)
        # Heuristik: < 1 Mio -> vermutlich in Cent geliefert
        if isinstance(v, int) and v < 1_000_000:
            return f"{v/100:,.0f} €".replace(",", ".")
        return f"{v:,.0f} €".replace(",", ".")
    except:
        return str(x)

def ts(val):
    if not val: return "?"
    try:
        if isinstance(val,(int,float)):
            t = int(val)
            if t > 10_000_000_000: t//=1000  # ms -> s
            return datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M UTC")
        s = str(val)
        return s.replace("T"," ").replace("Z"," UTC")
    except:
        return str(val)

# ---------------------- Hauptlogik --------------------------
def main():
    # 1) Login
    try:
        kb_auth()
    except Exception as e:
        discord_post(f"❌ Login fehlgeschlagen: {e}")
        return

    # 2) Liga-ID vorhanden?
    if not LEAGUE_ID:
        discord_post("ℹ️ Bitte Secret **KICK_LEAGUE_ID** setzen (z. B. 5654776).")
        return

    lname = league_name_from_id(LEAGUE_ID)

    # 3) Aktivmeldung beim manuellen Start
    if EVENT == "workflow_dispatch":
        ts_now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        discord_post(f"✅ Kickbase-Alarm aktiv – Liga: {lname} (ID: {LEAGUE_ID}) • {ts_now}")

           # 4) Debug-Scan mehrerer plausibler Endpoints (mit Liga-ID im Header)
    #    -> wir loggen ALLES ins Discord, was antwortet
    endpoints = [
        f"https://api.kickbase.com/v4/leagues/{LEAGUE_ID}/transfermarket/bids",
        f"https://api.kickbase.com/v4/transfermarket/leagues/{LEAGUE_ID}/bids",
        f"https://api.kickbase.com/v4/leagues/{LEAGUE_ID}/transfermarket",
        f"https://api.kickbase.com/v4/leagues/{LEAGUE_ID}/transfermarket/auctions",
        f"https://api.kickbase.com/v4/leagues/{LEAGUE_ID}/transfermarket/items",
        f"https://api.kickbase.com/v4/leagues/{LEAGUE_ID}/auctions",
        f"https://api.kickbase.com/v4/leagues/{LEAGUE_ID}/bids",
        "https://api.kickbase.com/v4/user/bids",
        "https://api.kickbase.com/v4/me/bids",
        f"https://api.kickbase.com/v3/leagues/{LEAGUE_ID}/transfermarket/bids",
        f"https://api.kickbase.com/v3/leagues/{LEAGUE_ID}/transfermarket",
        "https://api.kickbase.com/v3/user/bids",
    ]

    found_any = False
    for u in endpoints:
        try:
            r = session.get(u, headers={"x-league-id": str(LEAGUE_ID)}, timeout=20)
            if r.ok:
                try:
                    data = r.json()
                    preview = json.dumps(data, indent=2)[:1700]
                    discord_post(f"✅ {u} lieferte {len(preview)} Zeichen JSON:\n{preview}")
                    found_any = True
                except Exception as e:
                    discord_post(f"⚠️ {u} -> JSON-Fehler: {e}\nText: {r.text[:500]}")
            else:
                discord_post(f"❌ {u} -> {r.status_code}: {r.text[:120]}")
        except Exception as e:
            discord_post(f"❌ {u} -> Exception: {type(e).__name__}: {e}")

    if not found_any:
        discord_post("⚠️ Keiner der getesteten Endpoints hat JSON geliefert. (Wir sind trotzdem eingeloggt; die API-Pfade/Headers variieren.)")
        return

    # Wenn einer was geliefert hat, versuche aus dem ersten brauchbaren Objekt 'meine Nicht-Höchstgebote' zu ziehen
    # (wir nehmen heuristisch die letzte erfolgreiche Antwort aus der Schleife oben)
    # Tipp: wir könnten hier den 'besten' Treffer merken; fürs Erste beenden wir nach dem Scan, sag mir welcher Endpoint Daten hatte.


    found = False
    for u in endpoints:
        try:
            r = session.get(u, timeout=20)
            if r.ok:
                data = r.json()
                preview = json.dumps(data, indent=2)[:1800]
                discord_post(f"✅ Endpoint {u} lieferte:\n{preview}")
                found = True
            else:
                discord_post(f"{u} → {r.status_code}")
        except Exception as e:
            discord_post(f"{u} → Fehler: {e}")

    if not found:
        discord_post("⚠️ Keiner der getesteten Endpoints lieferte Daten.")

        return

    # 5) Items extrahieren
    if isinstance(data, dict):
        items = data.get("bids") or data.get("items") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []

    # 6) Auswertung: meine Gebote, aber nicht Höchstbietender (oder explizit überboten)
    alerts = []
    not_highest = 0
    for it in items:
        mine    = (it.get("isMine") or it.get("mine")) is True
        highest = (it.get("isHighestBidder") or it.get("highest")) is True
        over    = (it.get("overbid") or it.get("isOverbid")) is True
        if not mine:
            continue
        if highest and not over:
            continue

        not_highest += 1
        p = get(it, "player", default={}) or {}
        pname = get(p, "lastName", "name", default="Unbekannter Spieler")
        my_bid = get(it, "amount","bidAmount","myBid","amountCents")
        top    = get(it, "highestBidAmount","topBid","maxBid","topBidCents")
        end_at = get(it, "endTime","deadline","expiresAt","endTs")

        alerts.append(f"• {pname}: Dein Gebot {eur(my_bid)} | Höchstgebot {eur(top)} | Ende: {ts(end_at)}")

    # 7) Benachrichtigung
    if alerts:
        discord_post("⚠️ Du wurdest überboten:\n\n" + "\n".join(alerts))
    else:
        # Beim manuellen Start kleine Statistik
        if EVENT == "workflow_dispatch":
            discord_post(f"ℹ️ Alles gut – du bist aktuell überall Höchstbietender. ({not_highest} offene Nicht-Höchstgebote)")

if __name__ == "__main__":
    main()
