import os, requests, datetime, json
import sys
sys.path.insert(0, os.getcwd())  # erlaubt Import aus Repo
from kickbase_api.user import login as kb_login

EMAIL   = os.environ["KICK_USER"]
PASS    = os.environ["KICK_PASS"]
WEBHOOK = os.environ["DISCORD_WEBHOOK"]
LEAGUE_WANTED = os.environ.get("KICK_LEAGUE_NAME", "").strip()
LEAGUE_ID = os.environ.get("KICK_LEAGUE_ID", "").strip()
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
    # 1) Wenn eine Liga-ID als Secret gesetzt ist → sofort diese nehmen
    if LEAGUE_ID:
        # Versuche optional den Namen zu ermitteln (nur für die Anzeige)
        try:
            for url in [
                "https://api.kickbase.com/v4/leagues",
                "https://api.kickbase.com/v3/leagues",
                "https://api.kickbase.com/leagues",
            ]:
                r = session.get(url, timeout=15)
                if r.ok:
                    for L in (r.json() if isinstance(r.json(), list) else []):
                        if str(L.get("id")) == LEAGUE_ID:
                            return LEAGUE_ID, L.get("name", "(per ID)")
        except Exception:
            pass
        return LEAGUE_ID, "(per ID)"

    # 2) Wenn ein Name vorgegeben ist → exakt matchen (erst aus Login, dann Fallback)
    leagues = login_json.get("leagues") or []
    wanted = LEAGUE_WANTED
    if wanted:
        for L in leagues:
            if (L.get("name") or "").strip() == wanted:
                return L["id"], L.get("name", "?")
        # Fallback: alternative Endpoints probieren
        for url in [
            "https://api.kickbase.com/v4/leagues",
            "https://api.kickbase.com/v3/leagues",
            "https://api.kickbase.com/leagues",
        ]:
            r = session.get(url, timeout=15)
            if r.ok and isinstance(r.json(), list):
                for L in r.json():
                    if (L.get("name") or "").strip() == wanted:
                        return L["id"], L.get("name", "?")
        raise RuntimeError(f"Liga '{wanted}' nicht gefunden.")

    # 3) Fallback: erste Liga aus Login nehmen, wenn vorhanden
    if leagues:
        L = leagues[0]
        return L["id"], L.get("name", "?")

    # 4) Letzter Fallback: irgendeinen League-Endpoint probieren
    for url in [
        "https://api.kickbase.com/v4/leagues",
        "https://api.kickbase.com/v3/leagues",
        "https://api.kickbase.com/leagues",
    ]:
        r = session.get(url, timeout=15)
        if r.ok and isinstance(r.json(), list) and r.json():
            L = r.json()[0]
            return L["id"], L.get("name", "?")

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
        def main():
    try:
        lj = login()

        # Debug-Ausgabe: Login-Daten und mögliche Liga-Listen
        discord_post("Login JSON:\n" + json.dumps(lj, indent=2)[:1800])

        for u in [
            "https://api.kickbase.com/v4/user/leagues",
            "https://api.kickbase.com/v4/leagues",
            "https://api.kickbase.com/v3/leagues",
            "https://api.kickbase.com/leagues",
        ]:
            r = session.get(u, timeout=15)
            if r.ok:
                try:
                    data = r.json()
                    preview = json.dumps(data, indent=2)[:1800]
                    discord_post(f"Ligen von {u}:\n{preview}")
                except Exception as e:
                    discord_post(f"{u} → Fehler beim JSON: {e}")
            else:
                discord_post(f"{u} → {r.status_code} {r.text[:100]}")

        lid, lname = choose_league(lj)

                # Debug: versuche verschiedene Endpoints, um Ligen zu listen
        for u in [
            "https://api.kickbase.com/v4/leagues",
            "https://api.kickbase.com/v3/leagues",
            "https://api.kickbase.com/leagues",
        ]:
            r = session.get(u, timeout=15)
            if r.ok:
                leagues = r.json()
                if isinstance(leagues, list) and leagues:
                    preview = "\n".join([f"- {L.get('name')} (ID: {L.get('id')})" for L in leagues])[:1800]
                    discord_post(f"Ligen von {u}:\n{preview}")
                    break
        # Extra Debug: hole alle Ligen ab und poste sie
        r = session.get("https://api.kickbase.com/v4/user/leagues", timeout=20)
        if r.ok:
            leagues = r.json()
            txt = "Gefundene Ligen:\n" + "\n".join([f"- {L.get('name')} (ID: {L.get('id')})" for L in leagues])
            discord_post(txt)
        else:
            discord_post(f"⚠️ Konnte Ligen nicht holen: {r.status_code} {r.text[:100]}")
        lid, lname = choose_league(lj)
    except Exception as e:
        discord_post(f"❌ Login/Liga fehlgeschlagen: {e}")
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
