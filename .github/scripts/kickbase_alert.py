import os, requests, datetime, json
import sys
sys.path.insert(0, os.getcwd())  # erlaubt Import aus Repo
from kickbase_api.user import login as kb_login

EMAIL   = os.environ["KICK_USER"]
PASS    = os.environ["KICK_PASS"]
WEBHOOK = os.environ["DISCORD_WEBHOOK"]
LEAGUE_WANTED = os.environ.get("KICK_LEAGUE_NAME", "").strip()
EVENT = os.environ.get("GITHUB_EVENT_NAME","")  # "workflow_dispatch" beim manuellen Start

session = requests.Session()
session.headers.update({"Accept":"application/json","User-Agent":"Mozilla/5.0"})

def discord_post(text: str):
    # Stückeln, falls zu lang
    while text:
        chunk = text[:1900]
        r = requests.post(WEBHOOK, json={"content": chunk, "username": "Kickbase Alarm", "allowed_mentions":{"parse":[]}}, timeout=20)
        r.raise_for_status()
        text = text[1900:]

def login():
    # nutzt die bewährte Login-Funktion aus deinem Repo
    token = kb_login(EMAIL, PASS)  # wirft Exception bei Fehler
    session.headers.update({"Authorization": f"Bearer {token}"})
    # hol dir gleich die Ligen, damit choose_league wie gehabt arbeiten kann
    r = session.get("https://api.kickbase.com/v4/user/leagues", timeout=20)
    leagues = r.json() if r.ok else []
    return {"leagues": leagues}


def choose_league(login_json):
    leagues = login_json.get("leagues") or []
    if LEAGUE_WANTED:
        for L in leagues:
            if (L.get("name") or "").strip() == LEAGUE_WANTED:
                return L["id"], L.get("name","?")
    if leagues:
        L = leagues[0]
        return L["id"], L.get("name","?")
    # Fallback: extra call
    r = session.get("https://api.kickbase.com/v4/user/leagues", timeout=20)
    if r.ok and isinstance(r.json(), list) and r.json():
        L = r.json()[0]
        return L["id"], L.get("name","?")
    raise RuntimeError("Keine Liga gefunden. Bist du in einer Liga?")

def first_ok_json(urls):
    last = ""
    for url in urls:
        try:
            r = session.get(url, timeout=20)
            if r.ok:
                return r.json(), url
            last = f"{r.status_code} {r.text[:120]}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    return None, last

def get(d, *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default

def eur(x):
    if x is None: return "?"
    try:
        v = float(x)
        if v.is_integer(): v = int(v)
        # Heuristik: Beträge < 1 Mio könnten Cent sein
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
            if t > 10_000_000_000: t//=1000
            return datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M UTC")
        s = str(val)
        return s.replace("T"," ").replace("Z"," UTC")
    except:
        return str(val)

def main():
    try:
        lj = login()
        lid, lname = choose_league(lj)
    except Exception as e:
        discord_post(f"❌ Login/Liga fehlgeschlagen: {e}")
        return

    candidates = [
        f"https://api.kickbase.com/v4/leagues/{lid}/transfermarket/bids",
        "https://api.kickbase.com/v4/user/bids",
        f"https://api.kickbase.com/v3/leagues/{lid}/transfermarket/bids",
        "https://api.kickbase.com/v3/user/bids",
    ]
    data, used = first_ok_json(candidates)
    if data is None:
        discord_post("⚠️ Konnte Bids nicht laden (API evtl. geändert). Sag mir Bescheid, dann passe ich es an.")
        return

    if isinstance(data, dict):
        items = data.get("bids") or data.get("items") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []

    alerts = []
    for it in items:
        mine    = get(it, "isMine","mine", default=False) is True
        highest = get(it, "isHighestBidder","highest", default=False) is True
        over    = get(it, "overbid","isOverbid", default=False) is True
        if not mine:
            continue
        if highest and not over:
            continue
        p = get(it,"player", default={}) or {}
        player = get(p, "lastName","name", default="Unbekannter Spieler")
        my_bid = get(it, "amount","bidAmount","myBid","amountCents")
        top    = get(it, "highestBidAmount","topBid","maxBid","topBidCents")
        end_at = get(it, "endTime","deadline","expiresAt","endTs")
        alerts.append(f"• {player}: Dein Gebot {eur(my_bid)} | Höchstgebot {eur(top)} | Ende: {ts(end_at)}")

    if alerts:
        discord_post(f"⚠️ Du wurdest überboten (Liga: {lname})\n\n" + "\n".join(alerts))
    else:
        if EVENT == "workflow_dispatch":
            discord_post(f"✅ Kickbase-Alarm aktiv (Liga: {lname}). Aktuell keine Überbietungen.")

if __name__ == "__main__":
    main()
