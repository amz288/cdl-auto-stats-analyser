"""
CDL One-Click Analyst v14
=========================

Drop-in replacement for v13. Same Streamlit Cloud setup, same secrets:
  CITO_API_KEY   = "..."
  OPENAI_API_KEY = "..."

Fixes vs v13:
  1. LA Guerrillas M8 added (was missing — that's why nothing about them ever loaded).
  2. Verified CDL 2026 rosters BAKED IN as ground truth.
     Cito/BP rosters now augment rather than replace, so the player list is never blank.
  3. BO7 map pool baked in. The maps editor uses dropdowns from the real pool
     instead of free-text — the AI can no longer return stale BO6 maps.
  4. Full PRIORS table for every verified 2026 player so the model never blanks out.
  5. Map veto fetch retries more endpoint shapes AND has a manual override
     so when neither Cito nor the AI find vetoes, you can pick them yourself
     from the BO7 pool in 5 clicks.
  6. New EV Calculator tab — paste BetMGM line + odds, get fair price / edge / EV%.
  7. Roster correction pass on AI output — if the AI claims aBeZy is on FaZe,
     the app silently moves him to LA Thieves before rendering.
  8. AI prompt now includes the baked-in rosters as ground truth so it stops
     hallucinating moved players.

Workflow (unchanged):
  1. Refresh match list   →  Cito + BP + AI
  2. Select a match
  3. Refresh maps/vetoes  →  or pick manually from the BO7 pool
  4. Analyse this match   →  full 8-player ranking, props, leans, best bets
  5. EV tab               →  paste line + odds, get the maths
"""

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# ============================================================
# PAGE / STYLE
# ============================================================

st.set_page_config(page_title="CDL One-Click Analyst v14", layout="wide")

st.markdown("""
<style>
.stApp {
    background: radial-gradient(circle at top left, #121827 0, #080B12 42%, #03050A 100%);
    color: #F8FAFC;
}
h1,h2,h3 { letter-spacing:-.02em; }
.hero {
    padding: 26px;
    border-radius: 28px;
    border: 1px solid rgba(255,91,4,.38);
    background: linear-gradient(135deg, rgba(255,91,4,.16), rgba(15,23,42,.92));
    box-shadow: 0 24px 80px rgba(0,0,0,.42);
    margin-bottom: 18px;
}
.hero-title { font-size:44px; font-weight:950; line-height:1; margin-bottom:10px; }
.hero-sub { color:#CBD5E1; font-size:16px; line-height:1.55; }
.accent { color:#FF5B04; }
.card {
    border: 1px solid rgba(148,163,184,.18);
    border-radius: 20px;
    padding: 18px;
    background: rgba(15,23,42,.76);
    margin-bottom: 14px;
}
.match-card {
    border: 1px solid rgba(255,91,4,.30);
    border-radius: 24px;
    padding: 20px;
    background: linear-gradient(135deg, rgba(255,91,4,.12), rgba(15,23,42,.82));
    margin-bottom: 16px;
}
.bet-card {
    border: 1px solid rgba(34,197,94,.34);
    border-radius: 20px;
    padding: 16px;
    background: linear-gradient(135deg, rgba(34,197,94,.12), rgba(15,23,42,.84));
    min-height: 190px;
}
.warn-card {
    border: 1px solid rgba(245,158,11,.35);
    border-radius: 20px;
    padding: 16px;
    background: linear-gradient(135deg, rgba(245,158,11,.10), rgba(15,23,42,.82));
    margin-bottom: 14px;
}
.risk-card {
    border: 1px solid rgba(239,68,68,.32);
    border-radius: 20px;
    padding: 16px;
    background: linear-gradient(135deg, rgba(239,68,68,.10), rgba(15,23,42,.82));
    margin-bottom: 12px;
}
.pill {
    display:inline-block;
    border: 1px solid rgba(148,163,184,.25);
    background: rgba(2,6,23,.74);
    border-radius: 999px;
    padding: 4px 9px;
    color:#CBD5E1;
    font-size:12px;
    margin-right:6px;
    margin-bottom:6px;
}
.good { color:#22C55E; }
.mid  { color:#F59E0B; }
.bad  { color:#EF4444; }
.muted { color:#94A3B8; }
.big { font-size:32px; font-weight:900; }
div[data-testid="stMetric"] {
    background: rgba(15,23,42,.72);
    border: 1px solid rgba(148,163,184,.16);
    padding: 16px;
    border-radius: 18px;
}
.stButton > button { border-radius: 14px; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="hero-title">CDL <span class="accent">One‑Click Analyst v14</span></div>
  <div class="hero-sub">
    Match-day workflow. Verified 2026 rosters baked in, BO7 map pool, EV calculator,
    fail-safe map manual picker, full 8-player ranking, auto-save.
    <b>Analysis only — no bets placed, no profit guarantee. 18+.</b>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# CONFIG / GROUND TRUTH
# ============================================================

CACHE_FILE       = Path("v14_saved_analyses.json")
MATCH_CACHE_FILE = Path("v14_match_cache.json")
ROSTER_OVR_FILE  = Path("v14_roster_overrides.json")

BP_MATCHES_URL = "https://breakingpoint.gg/matches"
BP_TEAMS_URL   = "https://breakingpoint.gg/cdl/teams-and-players"
CITO_ROOTS     = ["https://api.citoapi.com/api/v1/cod", "https://api.citoapi.com/v1/cod"]

# FIX #1: LA Guerrillas M8 added (was missing in v13)
TEAMS = [
    "Boston Breach", "Carolina Royal Ravens", "Cloud9 New York", "FaZe Vegas",
    "G2 Minnesota", "Los Angeles Guerrillas M8", "Los Angeles Thieves",
    "Miami Heretics", "OpTic Texas", "Paris Gentle Mates",
    "Riyadh Falcons", "Toronto KOI", "Vancouver Surge",
]

MODES = ["Hardpoint", "Search & Destroy", "Overload", "Hardpoint", "Search & Destroy"]

# FIX #3: BO7 map pool baked in.
BO7_MAP_POOL = {
    "Hardpoint":        ["Protocol", "Cortex", "Skyline", "Toshin", "Exposure"],
    "Search & Destroy": ["Protocol", "Cortex", "Skyline", "Toshin", "Exposure", "Imprint"],
    "Overload":         ["Protocol", "Cortex", "Skyline", "Toshin"],
}

# FIX #2: Verified CDL 2026 rosters as ground truth.
# Sources: 100thieves.com, esportsinsider, esportsbets, prismnews, liquipedia (Nov–Dec 2025).
VERIFIED_ROSTERS = {
    "Boston Breach":             ["Snoopy", "Purj", "Cammy", "Nastie"],
    "Carolina Royal Ravens":     ["Craze", "Lurqxx", "Nero", "SlasheR"],
    "Cloud9 New York":           ["Encourage", "Hide", "Nejra", "Okis"],
    "FaZe Vegas":                ["Simp", "Drazah", "04", "Abuzah"],
    "G2 Minnesota":              ["Estreal", "Kremp", "Mamba", "Skyz"],
    "Los Angeles Guerrillas M8": ["Lucky", "ReeaL", "Standy", "Fire"],
    "Los Angeles Thieves":       ["aBeZy", "Kenny", "HyDra", "Scrap"],
    "Miami Heretics":            ["MettalZ", "RenKoR", "SupeR", "Traixx"],
    "OpTic Texas":               ["Dashy", "Shotzzy", "Huke", "Mercules"],
    "Paris Gentle Mates":        ["Envoy", "Ghosty", "Neptune", "Sib"],
    "Riyadh Falcons":            ["Cellium", "Exnid", "KiSMET", "Pred"],
    "Toronto KOI":               ["CleanX", "Insight", "JoeDeceives", "Kips"],
    "Vancouver Surge":           ["Atura", "Lunarz", "Nero2", "Wevy"],
}

# Player → correct team lookup for the AI roster-correction pass
PLAYER_TO_TEAM = {}
for _t, _ps in VERIFIED_ROSTERS.items():
    for _p in _ps:
        PLAYER_TO_TEAM[_p.lower()] = _t

TEAM_SLUGS = {t: re.sub(r"[^a-z0-9-]", "", t.lower().replace("&","and").replace(" ","-")) for t in TEAMS}
TEAM_SLUGS["FaZe Vegas"]    = "faze-vegas"
TEAM_SLUGS["OpTic Texas"]   = "optic-texas"
TEAM_SLUGS["Los Angeles Guerrillas M8"] = "la-guerrillas"
SLUG_TO_TEAM = {v:k for k,v in TEAM_SLUGS.items()}

# FIX #4: Full PRIORS for every verified 2026 player. [HP, SnD, Overload], 70–98 scale.
PRIORS = {
    # OpTic Texas
    "Dashy":[92,95,91], "Shotzzy":[95,93,94], "Huke":[89,87,88], "Mercules":[88,86,87],
    # LA Thieves
    "aBeZy":[95,94,93], "Kenny":[92,93,91], "HyDra":[96,93,95], "Scrap":[96,92,95],
    # FaZe Vegas
    "Simp":[96,97,94], "Drazah":[91,92,90], "04":[84,82,83], "Abuzah":[90,92,90],
    # Riyadh Falcons
    "Cellium":[94,98,93], "Exnid":[86,86,86], "KiSMET":[90,88,90], "Pred":[93,91,92],
    # G2 Minnesota
    "Estreal":[91,89,90], "Kremp":[94,91,93], "Mamba":[86,83,85], "Skyz":[89,92,88],
    # Paris Gentle Mates
    "Envoy":[91,89,90], "Ghosty":[90,90,90], "Neptune":[89,86,88], "Sib":[91,88,91],
    # Toronto KOI
    "CleanX":[91,89,90], "Insight":[88,93,87], "JoeDeceives":[92,94,92], "Kips":[85,85,85],
    # Boston Breach
    "Snoopy":[86,85,85], "Purj":[86,84,85], "Cammy":[89,88,88], "Nastie":[89,87,88],
    # Carolina Royal Ravens
    "Craze":[85,83,84], "Lurqxx":[89,86,88], "Nero":[90,87,89], "SlasheR":[86,88,86],
    # Cloud9 NY
    "Encourage":[85,82,84], "Hide":[83,85,83], "Nejra":[83,83,83], "Okis":[83,83,83],
    # Miami Heretics
    "MettalZ":[86,85,85], "RenKoR":[85,84,84], "SupeR":[87,86,86], "Traixx":[83,83,83],
    # LA Guerrillas M8
    "Lucky":[86,88,86], "ReeaL":[88,86,87], "Standy":[88,86,87], "Fire":[83,83,83],
    # Vancouver Surge
    "Atura":[84,86,84], "Lunarz":[85,85,85], "Nero2":[82,82,82], "Wevy":[84,84,84],
}

ROSTER_COLS = ["Team", "Player", "Source"]
STAT_COLS   = ["Team", "Player", "Mode", "Score", "KD", "KP10", "KPR", "ProjectedKills", "Source"]

# ============================================================
# HELPERS
# ============================================================

def safe(x): return "" if x is None else str(x).strip()
def now():  return datetime.now().strftime("%d %b %Y %H:%M")
def slug(x): return re.sub(r"[^a-z0-9-]", "", safe(x).lower().replace("&","and").replace(" ","-"))

def norm_team(x):
    s = safe(x)
    if not s: return ""
    sl = slug(s)
    if sl in SLUG_TO_TEAM: return SLUG_TO_TEAM[sl]
    for t in TEAMS:
        if s.lower() == t.lower() or t.lower() in s.lower() or s.lower() in t.lower():
            return t
    return s

def mode_name(x):
    m = safe(x).lower()
    if "search" in m or "snd" in m or "s&d" in m: return "Search & Destroy"
    if "overload" in m or "ovl" in m or "control" in m: return "Overload"
    return "Hardpoint"

def to_num(x, default=0.0):
    try:
        s = re.sub(r"[^0-9.\-]", "", safe(x))
        return float(s) if s not in ["", ".", "-"] else default
    except Exception:
        return default

def get_secret(name):
    try: return st.secrets.get(name, "")
    except Exception: return ""

def load_json(path):
    if not path.exists(): return {}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}

def save_json(path, data):
    try: path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception: pass

def short_hash(text): return hashlib.sha256(text.encode("utf-8")).hexdigest()[:18]

def empty_roster(): return pd.DataFrame(columns=ROSTER_COLS)
def empty_stats(): return pd.DataFrame(columns=STAT_COLS)

def default_maps():
    return pd.DataFrame({
        "Map": [1,2,3,4,5],
        "Mode": MODES,
        "Map Name": ["","","","",""],
        "Picked By": ["","","","",""],
    })

def maps_to_text(df):
    lines = []
    for _, r in df.iterrows():
        lines.append(f"Map {int(r['Map'])}: {safe(r['Mode'])} | map: {safe(r['Map Name']) or 'unknown'} | picked by: {safe(r['Picked By']) or 'unknown'}")
    return "\n".join(lines)

def match_label(m, i):
    s = safe(m.get("status")).lower()
    icon = "🔴 LIVE" if s in ["live","in-play","in play"] else ("🟢" if s == "upcoming" else "⚪")
    return f"{i}: {icon} {safe(m.get('start_time'))} — {safe(m.get('team_a'))} vs {safe(m.get('team_b'))} — {safe(m.get('event'))} [{safe(m.get('source'))}]"

def analysis_key(match, maps_df, model):
    return short_hash(f"{match.get('team_a')}|{match.get('team_b')}|{match.get('start_time')}|{maps_to_text(maps_df)}|{model}")

def nested(d, paths):
    for path in paths:
        cur, ok = d, True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False; break
        if ok and safe(cur): return cur
    return ""

def as_list(payload):
    d = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(d, list): return d
    if isinstance(d, dict):
        for k in ["players","matches","items","results","data","maps","schedule","fixtures","games"]:
            if isinstance(d.get(k), list): return d[k]
    return []

def extract_json(text):
    """Tolerant JSON extractor — strips fences, finds outermost {...}, repairs truncation."""
    if not text: return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try: return json.loads(cleaned)
    except Exception: pass
    # Find outermost object
    first = cleaned.find("{")
    if first < 0: return None
    candidate = cleaned[first:]
    try: return json.loads(candidate)
    except Exception: pass
    # Strip trailing commas
    fixed = re.sub(r",(\s*[}\]])", r"\1", candidate)
    try: return json.loads(fixed)
    except Exception: pass
    # Iteratively trim back to last clean array/object boundary
    working = fixed
    for _ in range(40):
        try: return json.loads(working)
        except Exception:
            i1 = working.rfind("},")
            i2 = working.rfind("],")
            boundary = max(i1, i2)
            if boundary < 0: break
            working = working[:boundary+1]
            # Close any unbalanced brackets
            opens_o = working.count("{") - working.count("}")
            opens_a = working.count("[") - working.count("]")
            tail = working.rstrip(", \n\t")
            for _ in range(max(0, opens_a)): tail += "]"
            for _ in range(max(0, opens_o)): tail += "}"
            try: return json.loads(tail)
            except Exception: continue
    return None

# ============================================================
# ROSTER OVERRIDES (verified rosters + user edits)
# ============================================================

def get_roster_for(team):
    overrides = load_json(ROSTER_OVR_FILE)
    if isinstance(overrides, dict) and overrides.get(team):
        return list(overrides[team]), "User override"
    if team in VERIFIED_ROSTERS:
        return list(VERIFIED_ROSTERS[team]), "Verified 2026"
    return [], "Unknown"

def save_roster_override(team, players):
    overrides = load_json(ROSTER_OVR_FILE)
    if not isinstance(overrides, dict): overrides = {}
    overrides[team] = [p for p in players if safe(p)]
    save_json(ROSTER_OVR_FILE, overrides)

def reset_roster(team):
    overrides = load_json(ROSTER_OVR_FILE)
    if isinstance(overrides, dict):
        overrides.pop(team, None)
        save_json(ROSTER_OVR_FILE, overrides)

def correct_player_team(player_name, claimed_team):
    """Fixes AI hallucinations like 'aBeZy on FaZe' → moves him to LA Thieves."""
    if not player_name: return claimed_team, False
    correct = PLAYER_TO_TEAM.get(player_name.lower().strip())
    if correct and correct != claimed_team:
        return correct, True
    return claimed_team or correct or "", False

# ============================================================
# CITO API
# ============================================================

def cito_headers():
    key = get_secret("CITO_API_KEY")
    h = {"accept": "application/json", "user-agent": "CDL-v14"}
    if key:
        h["Authorization"] = f"Bearer {key}"
        h["x-api-key"] = key
    return h

@st.cache_data(ttl=120, show_spinner=False)
def cito_get(path, params_tuple=()):
    params = dict(params_tuple)
    attempts = []
    for root in CITO_ROOTS:
        try:
            r = requests.get(root + path, headers=cito_headers(), params=params, timeout=25)
            try: payload = r.json()
            except Exception: payload = {"raw_text": r.text[:1200]}
            res = {"ok": r.ok, "status": r.status_code, "url": r.url, "payload": payload}
            attempts.append(res)
            if r.ok: return res
        except Exception as e:
            attempts.append({"ok": False, "status": "ERR", "url": root + path, "payload": {"error": str(e)}})
    res = attempts[-1] if attempts else {"ok": False, "status": "ERR", "url": path, "payload": {"error": "No attempts"}}
    res["attempts"] = attempts
    return res

@st.cache_data(ttl=120, show_spinner=True)
def cito_match_list(season, limit):
    endpoints = [
        ("/matches/upcoming", {"season": season, "limit": limit}),
        ("/matches/live",     {"season": season, "limit": limit}),
        ("/matches",          {"season": season, "limit": limit, "status": "live"}),
        ("/matches",          {"season": season, "limit": limit, "status": "upcoming"}),
        ("/cdl/schedule",     {"season": season, "limit": limit}),
    ]
    calls, rows = [], []
    for path, params in endpoints:
        call = cito_get(path, tuple(params.items()))
        calls.append(call)
        if not call["ok"]: continue
        for m in as_list(call["payload"]):
            if not isinstance(m, dict): continue
            blob = str(m)
            a = norm_team(nested(m, ["team1.name","teams.team1.name","homeTeam.name","teamA.name","team1.slug","team1"]))
            b = norm_team(nested(m, ["team2.name","teams.team2.name","awayTeam.name","teamB.name","team2.slug","team2"]))
            found = [t for t in TEAMS if t.lower() in blob.lower()]
            if not a and len(found) >= 1: a = found[0]
            if not b and len(found) >= 2: b = found[1]
            if a and b and a != b:
                status = safe(nested(m, ["status","state","matchStatus"])) or ("live" if "live" in path else "upcoming")
                rows.append({
                    "start_time": safe(nested(m, ["startsAt","startTime","scheduledAt","matchDate","date"])) or "",
                    "event":      safe(nested(m, ["event.name","tournament.name","event","round","stage.name"])) or "CDL",
                    "team_a": a, "team_b": b, "status": status, "source": "Cito",
                    "match_id": safe(nested(m, ["id","matchId","bpMatchId","_id"])),
                })
    return rows, calls

@st.cache_data(ttl=120, show_spinner=True)
def cito_maps_for_match(match_id):
    """FIX #5: Retries more endpoint shapes."""
    if not match_id: return None, []
    endpoints = [
        f"/matches/{match_id}/maps",
        f"/matches/{match_id}/vetoes",
        f"/matches/{match_id}/veto",
        f"/matches/{match_id}/games",
        f"/matches/{match_id}",
    ]
    calls = []
    for ep in endpoints:
        call = cito_get(ep, ())
        calls.append(call)
        if not call["ok"]: continue
        payload = call["payload"]
        items = as_list(payload)
        if not items and isinstance(payload, dict):
            for key in ["maps","vetoes","games","veto","mapVetoes"]:
                if isinstance(payload.get(key), list):
                    items = payload[key]; break
        rows = []
        for i, mp in enumerate(items[:5], start=1):
            if not isinstance(mp, dict): continue
            map_name = safe(nested(mp, ["mapName","map.name","name","map","mapTitle"]))
            mode = mode_name(nested(mp, ["mode","gameMode","game.mode","type","modeName"]))
            # Verify against BO7 pool — drop nonsense
            if map_name and map_name not in BO7_MAP_POOL.get(mode, []):
                # try case-insensitive match
                pool = BO7_MAP_POOL.get(mode, [])
                matched = next((p for p in pool if p.lower() == map_name.lower()), "")
                map_name = matched
            rows.append({
                "Map": i,
                "Mode": mode,
                "Map Name": map_name,
                "Picked By": norm_team(nested(mp, ["pickedBy.name","pickedBy","pickTeam.name","team.name","team"])) or "",
            })
        if rows:
            while len(rows) < 5:
                i = len(rows) + 1
                rows.append({"Map": i, "Mode": MODES[i-1], "Map Name": "", "Picked By": ""})
            return pd.DataFrame(rows), calls
    return None, calls

@st.cache_data(ttl=21600, show_spinner=True)
def cito_roster(team):
    rows, calls = [], []
    for val in [TEAM_SLUGS.get(team, slug(team)), team]:
        call = cito_get("/players", tuple({"team": val, "activeOnly": "true", "limit": 12}.items()))
        calls.append(call)
        if not call["ok"]: continue
        for p in as_list(call["payload"]):
            if not isinstance(p, dict): continue
            name = safe(nested(p, ["ign","playerName","gamertag","handle","name"]))
            pteam = norm_team(nested(p, ["currentTeam.name","team.name","teamName","team","currentTeam.slug","team.slug"])) or team
            if name and pteam == team:
                rows.append({"Team": team, "Player": name, "Source": "Cito roster"})
        if rows: break
    return (pd.DataFrame(rows, columns=ROSTER_COLS).drop_duplicates() if rows else empty_roster()), calls

@st.cache_data(ttl=21600, show_spinner=True)
def cito_player_stats(player, season):
    calls = []
    for candidate in dict.fromkeys([player, slug(player), player.lower()]):
        if not candidate: continue
        call = cito_get(f"/players/{candidate}/stats", tuple({"season": season}.items()))
        calls.append(call)
        if call["ok"]: return call["payload"], calls
    return {}, calls

# ============================================================
# BREAKING POINT (best-effort, often bot-blocked)
# ============================================================

@st.cache_data(ttl=120, show_spinner=False)
def page_text(url):
    r = requests.get(url, headers={"user-agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script","style","noscript"]): tag.decompose()
    return "\n".join(x.strip() for x in soup.get_text("\n").splitlines() if x.strip())

@st.cache_data(ttl=120, show_spinner=True)
def bp_match_list():
    try:
        text = " ".join(page_text(BP_MATCHES_URL).splitlines())
    except Exception as e:
        return [], [{"ok": False, "status": "ERR", "url": BP_MATCHES_URL, "payload": {"error": str(e)}}]
    alt = "|".join(map(re.escape, TEAMS))
    rows = []
    pat = rf"(LIVE|~\d+\s+(?:minutes?|hours?|days?))?\s*(CDL\s+(?:Major|Minor|Champs)[^~]*?)\s+({alt}|TBD)\s+0\s+({alt}|TBD)\s+0"
    for m in re.finditer(pat, text, flags=re.I):
        start = safe(m.group(1)) or ""
        event = safe(m.group(2)) or "CDL"
        a, b = safe(m.group(3)), safe(m.group(4))
        if a != "TBD" and b != "TBD" and a and b and a != b:
            rows.append({"start_time": start, "event": event, "team_a": a, "team_b": b,
                         "status": "live" if start.lower() == "live" else "upcoming",
                         "source": "Breaking Point", "match_id": ""})
    pat2 = rf"({alt})\s+(?:vs|v|VS)\s+({alt})"
    for m in re.finditer(pat2, text):
        a, b = safe(m.group(1)), safe(m.group(2))
        if a and b and a != b:
            rows.append({"start_time": "", "event": "CDL", "team_a": a, "team_b": b,
                         "status": "unknown", "source": "Breaking Point", "match_id": ""})
    return dedupe_matches(rows), [{"ok": True, "status": 200, "url": BP_MATCHES_URL, "payload": {"matches": len(rows)}}]

# ============================================================
# STATS MODEL
# ============================================================

def fallback_rows(team, player):
    hp, snd, ovl = PRIORS.get(player, [74, 74, 74])
    return [
        {"Team":team, "Player":player, "Mode":"Hardpoint",        "Score":hp,  "KD":None, "KP10":None, "KPR":None, "ProjectedKills": round(18 + (hp  - 70) * 0.18, 1), "Source": "Fallback profile"},
        {"Team":team, "Player":player, "Mode":"Search & Destroy", "Score":snd, "KD":None, "KP10":None, "KPR":None, "ProjectedKills": round(5  + (snd - 70) * 0.06, 1), "Source": "Fallback profile"},
        {"Team":team, "Player":player, "Mode":"Overload",         "Score":ovl, "KD":None, "KP10":None, "KPR":None, "ProjectedKills": round(18 + (ovl - 70) * 0.16, 1), "Source": "Fallback profile"},
    ]

def parse_stats(player, team, payload):
    d = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(d, dict): return []
    info = d.get("player", {}) if isinstance(d.get("player"), dict) else {}
    name = safe(info.get("ign") or info.get("name") or player)
    by = d.get("byMode", {}) if isinstance(d.get("byMode"), dict) else {}
    overall = d.get("overall", {}) if isinstance(d.get("overall"), dict) else {}
    modes = {
        "hardpoint":"Hardpoint", "hp":"Hardpoint",
        "searchAndDestroy":"Search & Destroy", "search_and_destroy":"Search & Destroy", "snd":"Search & Destroy",
        "overload":"Overload", "ovl":"Overload", "control":"Overload",
    }
    rows = []
    for key, mode in modes.items():
        m = by.get(key)
        if not isinstance(m, dict): continue
        kd   = to_num(m.get("kd"), to_num(overall.get("kd"), 1))
        kp10 = to_num(m.get("killsPer10"), 0)
        dmg10= to_num(m.get("damagePer10"), 0)
        kpr  = to_num(m.get("killsPerRound"), 0)
        if mode == "Search & Destroy":
            score = 55 + kpr * 45 + (kd - 1) * 18
            proj  = max(3, round(kpr * 11 if kpr else 5 + (score - 70) * 0.06, 1))
        else:
            score = 50 + kp10 * 1.75 + dmg10 / 180 + (kd - 1) * 16
            proj  = max(10, round(kp10 * 2.5 if kp10 else 18 + (score - 70) * 0.18, 1))
        rows.append({"Team":team, "Player":name, "Mode":mode, "Score":round(score,2),
                     "KD":kd, "KP10":kp10, "KPR":kpr, "ProjectedKills":proj, "Source":"Cito player stats"})
    return rows

def build_stats(team_a, team_b, season):
    """FIX #2: Verified rosters guarantee a full player list; Cito augments stats."""
    calls = []
    roster_frames, stat_rows = [], []
    for team in [team_a, team_b]:
        # Start with verified ground truth
        verified_players, source_label = get_roster_for(team)
        # Try Cito enrichment, but never let it shrink the list
        cito_roster_df, rcalls = cito_roster(team)
        calls += rcalls
        cito_players = list(cito_roster_df["Player"]) if not cito_roster_df.empty else []
        # Union — verified first, then anyone Cito adds we didn't have
        merged = list(verified_players)
        for p in cito_players:
            if p not in merged and p.lower() not in {x.lower() for x in merged}:
                merged.append(p)
        # Build roster frame
        roster_frames.append(pd.DataFrame([
            {"Team": team, "Player": p,
             "Source": source_label if p in verified_players else "Cito (extra)"}
            for p in merged
        ], columns=ROSTER_COLS))
        # Stats per player
        for p in merged:
            payload, pcalls = cito_player_stats(p, season)
            calls += pcalls
            parsed = parse_stats(p, team, payload)
            stat_rows += parsed if parsed else fallback_rows(team, p)
    roster_df = pd.concat(roster_frames, ignore_index=True).drop_duplicates(subset=["Team","Player"]) if roster_frames else empty_roster()
    stats_df  = pd.DataFrame(stat_rows, columns=STAT_COLS).drop_duplicates(subset=["Team","Player","Mode"]) if stat_rows else empty_stats()
    return roster_df, stats_df, calls

# ============================================================
# OPENAI
# ============================================================

def openai_client(api_key):
    if OpenAI is None:
        raise RuntimeError("openai package missing. Check requirements.txt includes openai, then reboot.")
    return OpenAI(api_key=api_key)

def openai_call(api_key, model, prompt, require_search=True):
    c = openai_client(api_key)
    attempts = [
        {"tools": [{"type":"web_search"}],         "tool_choice": "required" if require_search else "auto"},
        {"tools": [{"type":"web_search_preview"}], "tool_choice": "required" if require_search else "auto"},
        {"tools": [], "tool_choice": "none"},
    ]
    last = None
    for a in attempts:
        try:
            kwargs = {"model": model, "input": prompt}
            if a["tools"]:
                kwargs["tools"] = a["tools"]; kwargs["tool_choice"] = a["tool_choice"]
            resp = c.responses.create(**kwargs)
            return resp.output_text, {"model": model, "attempt": a}
        except Exception as e:
            last = str(e)
    raise RuntimeError(last or "OpenAI call failed")

def ai_match_list(api_key, model):
    teams_csv = ", ".join(TEAMS)
    prompt = f"""
Use web search to find current LIVE, in-play, upcoming and recently-started Call of Duty League (CDL) 2026 matches.
The 13 teams are: {teams_csv}.

Search Breaking Point matches page, the official CDL schedule, recent reputable esports news.

Return ONLY valid JSON:
{{
  "notes":"short confidence note",
  "matches":[
    {{"start_time":"","event":"","team_a":"","team_b":"","status":"live/upcoming/in-play/unknown","source":""}}
  ]
}}

Rules:
- Live/in-play matches first.
- Upcoming next 10 days after that.
- Do NOT invent matches.
- Only use team names from the list above (or close variants).
"""
    raw, meta = openai_call(api_key, model, prompt, True)
    parsed = extract_json(raw) or {"notes":"AI output not JSON","matches":[]}
    rows = []
    for m in parsed.get("matches", []) if isinstance(parsed, dict) else []:
        if not isinstance(m, dict): continue
        a, b = safe(m.get("team_a")), safe(m.get("team_b"))
        if a and b and a.lower() != b.lower():
            rows.append({"start_time": safe(m.get("start_time")),
                         "event": safe(m.get("event")) or "CDL",
                         "team_a": norm_team(a), "team_b": norm_team(b),
                         "status": safe(m.get("status")) or "unknown",
                         "source": safe(m.get("source")) or "OpenAI web search",
                         "match_id": ""})
    return rows, raw, meta, safe(parsed.get("notes"))

def ai_find_maps(api_key, model, match):
    prompt = f"""
Use web search to find the map vetoes/maps for this current or upcoming CDL match:
{match.get("team_a")} vs {match.get("team_b")}
Event/time: {match.get("event")} {match.get("start_time")}

Look at Breaking Point, official CDL, broadcast/live match pages.

CONSTRAINT: only use these BO7 competitive maps:
- Hardpoint: {", ".join(BO7_MAP_POOL["Hardpoint"])}
- Search & Destroy: {", ".join(BO7_MAP_POOL["Search & Destroy"])}
- Overload: {", ".join(BO7_MAP_POOL["Overload"])}

Return ONLY valid JSON:
{{
  "maps_found": true,
  "confidence": "High/Medium/Low",
  "maps": [
    {{"map":1, "mode":"Hardpoint",        "map_name":"", "picked_by":""}},
    {{"map":2, "mode":"Search & Destroy", "map_name":"", "picked_by":""}},
    {{"map":3, "mode":"Overload",         "map_name":"", "picked_by":""}},
    {{"map":4, "mode":"Hardpoint",        "map_name":"", "picked_by":""}},
    {{"map":5, "mode":"Search & Destroy", "map_name":"", "picked_by":""}}
  ],
  "sources_used":[""],
  "note":""
}}

If maps not yet available, return maps_found=false. Do NOT invent map names.
"""
    raw, meta = openai_call(api_key, model, prompt, True)
    parsed = extract_json(raw)
    rows = []
    if isinstance(parsed, dict) and parsed.get("maps_found") and isinstance(parsed.get("maps"), list):
        for i, mp in enumerate(parsed["maps"][:5], start=1):
            mode = mode_name(mp.get("mode") or MODES[i-1])
            map_name = safe(mp.get("map_name"))
            # Validate against pool
            if map_name and map_name not in BO7_MAP_POOL.get(mode, []):
                matched = next((p for p in BO7_MAP_POOL.get(mode, []) if p.lower() == map_name.lower()), "")
                map_name = matched
            rows.append({"Map": int(mp.get("map") or i), "Mode": mode,
                         "Map Name": map_name,
                         "Picked By": norm_team(mp.get("picked_by")) if safe(mp.get("picked_by")) else ""})
        if rows:
            while len(rows) < 5:
                i = len(rows) + 1
                rows.append({"Map": i, "Mode": MODES[i-1], "Map Name": "", "Picked By": ""})
            return pd.DataFrame(rows), raw, meta, parsed
    return None, raw, meta, parsed

def analysis_prompt(match, maps_df, roster_df, stats_df, live_mode):
    roster_csv = roster_df.to_csv(index=False)[:9000] if not roster_df.empty else "No roster rows loaded."
    stats_csv  = stats_df.to_csv(index=False)[:18000] if not stats_df.empty else "No stat rows loaded."
    # FIX #8: feed verified rosters as ground truth
    a_players = ", ".join(get_roster_for(match.get("team_a"))[0])
    b_players = ", ".join(get_roster_for(match.get("team_b"))[0])
    pool_text = "\n".join([f"  {k}: {', '.join(v)}" for k,v in BO7_MAP_POOL.items()])
    return f"""
You are a Call of Duty League match-day betting analyst.

Match: {match.get("team_a")} vs {match.get("team_b")}
Status/time/event/source: {match.get("status")} | {match.get("start_time")} | {match.get("event")} | {match.get("source")}

VERIFIED ROSTERS (GROUND TRUTH — these are the ONLY players who play for these teams in 2026):
  {match.get("team_a")}: {a_players}
  {match.get("team_b")}: {b_players}

BO7 map pool by mode (do NOT use any other map names):
{pool_text}

User cares about: player kills per map, team to win a map, live/in-play, decimal odds when discoverable.

CDL series format: M1 HP, M2 SnD, M3 Overload, M4 HP, M5 SnD.

Current map/veto info:
{maps_to_text(maps_df)}

Structured roster data (Cito + verified):
{roster_csv}

Structured player mode stats (Cito + fallback model):
{stats_csv}

Instructions:
1. Use structured stats as the base, then web search for current form, subs, roster news, BetMGM odds.
2. ONLY name players from the verified rosters above. NEVER assign a player to a team they don't play for.
3. If maps missing, lean by mode and say confidence is lower.
4. Try to find BetMGM decimal odds for player kills per map and map winner. Don't invent odds.
5. Live/in-play → include watch notes.
6. Rank ALL 8 starting players 1 (best) to 8 (worst) in all_8_player_rankings.

Return ONLY valid JSON:
{{
  "match_title":"{match.get("team_a")} vs {match.get("team_b")}",
  "summary":"",
  "status_assessment":"live/upcoming/in-play/unknown",
  "model_pick":"",
  "team_a_win_probability":0.0,
  "team_b_win_probability":0.0,
  "confidence":"High/Medium/Low",
  "data_quality":{{"cito_stats":"Good/Partial/Missing","breakingpoint_context":"Good/Partial/Missing","maps_vetoes":"Found/Partial/Not found","betmgm_odds":"Found/Partial/Not found","note":""}},
  "live_or_inplay_notes":["","",""],
  "key_context":["","",""],
  "all_8_player_rankings":[
    {{"rank":1,"player":"","team":"","overall_rating":0.0,"best_modes":"","projected_strength":"","reason":"","confidence":"High/Medium/Low"}},
    {{"rank":2,"player":"","team":"","overall_rating":0.0,"best_modes":"","projected_strength":"","reason":"","confidence":"High/Medium/Low"}},
    {{"rank":3,"player":"","team":"","overall_rating":0.0,"best_modes":"","projected_strength":"","reason":"","confidence":"High/Medium/Low"}},
    {{"rank":4,"player":"","team":"","overall_rating":0.0,"best_modes":"","projected_strength":"","reason":"","confidence":"High/Medium/Low"}},
    {{"rank":5,"player":"","team":"","overall_rating":0.0,"best_modes":"","projected_strength":"","reason":"","confidence":"High/Medium/Low"}},
    {{"rank":6,"player":"","team":"","overall_rating":0.0,"best_modes":"","projected_strength":"","reason":"","confidence":"High/Medium/Low"}},
    {{"rank":7,"player":"","team":"","overall_rating":0.0,"best_modes":"","projected_strength":"","reason":"","confidence":"High/Medium/Low"}},
    {{"rank":8,"player":"","team":"","overall_rating":0.0,"best_modes":"","projected_strength":"","reason":"","confidence":"High/Medium/Low"}}
  ],
  "best_players_overall":[{{"rank":1,"player":"","team":"","best_modes":"","reason":"","confidence":"High/Medium/Low"}}],
  "best_targets_without_odds":[{{"player":"","team":"","map":1,"mode":"","projected_kills":0.0,"target_note":"","confidence":"High/Medium/Low"}}],
  "player_kill_props":[{{"player":"","team":"","map":1,"mode":"","line":null,"over_decimal_odds":null,"under_decimal_odds":null,"projected_kills":0.0,"over_probability":0.0,"edge_percent":null,"recommendation":"Over/Under/No Bet/Target if line appears","confidence":"High/Medium/Low","reason":"","odds_found":false}}],
  "map_winner_leans":[{{"map":1,"mode":"","map_name":"","lean_team":"","probability":0.0,"betmgm_decimal_odds":null,"edge_percent":null,"confidence":"High/Medium/Low","reason":""}}],
  "best_bets":[{{"rank":1,"market":"Player kills per map/Map winner","selection":"","line":null,"odds":null,"edge_percent":null,"confidence":"High/Medium/Low","reason":""}}],
  "avoid_or_risk":[{{"selection":"","reason":"","risk":"High/Medium/Low"}}],
  "sources_used":[""],
  "final_note":"Analysis only. Odds can move."
}}
"""

def apply_roster_corrections(parsed):
    """FIX #7: post-process AI output, silently move mis-attributed players."""
    if not isinstance(parsed, dict): return parsed
    for section in ["all_8_player_rankings", "best_players_overall",
                    "best_targets_without_odds", "player_kill_props"]:
        items = parsed.get(section)
        if not isinstance(items, list): continue
        for item in items:
            if not isinstance(item, dict): continue
            name = item.get("player")
            claimed = item.get("team")
            corrected, was_changed = correct_player_team(name, claimed)
            if corrected:
                item["team"] = corrected
                if was_changed:
                    item["_corrected"] = True
    return parsed

def run_ai_analysis(api_key, model, match, maps_df, roster_df, stats_df):
    live = safe(match.get("status")).lower() in ["live","in-play","in play"]
    raw, meta = openai_call(api_key, model, analysis_prompt(match, maps_df, roster_df, stats_df, live), True)
    parsed = extract_json(raw)
    parsed = apply_roster_corrections(parsed)
    return parsed, raw, meta

# ============================================================
# MATCH MERGE / DIAGNOSTICS
# ============================================================

def cito_health_check(season):
    checks = []
    tests = [
        ("/matches/upcoming", {"season":season,"limit":5}),
        ("/matches/live",     {"season":season,"limit":5}),
        ("/cdl/schedule",     {"season":season,"limit":5}),
        ("/players",          {"team":"optic-texas","limit":5}),
    ]
    for path, params in tests:
        call = cito_get(path, tuple(params.items()))
        count = len(as_list(call.get("payload", {}))) if isinstance(call, dict) else 0
        checks.append({"Endpoint": path, "Status": call.get("status"), "OK": call.get("ok"),
                       "Rows": count, "URL": call.get("url")})
    return pd.DataFrame(checks)

def dedupe_matches(rows):
    out, seen = [], set()
    for m in rows:
        a, b = safe(m.get("team_a")), safe(m.get("team_b"))
        if not a or not b: continue
        key = tuple(sorted([a.lower(), b.lower()])) + (safe(m.get("start_time")).lower(),)
        if key in seen: continue
        seen.add(key); out.append(m)
    def rk(m):
        s = safe(m.get("status")).lower()
        if s in ["live","in-play","in play"]: return 0
        if s == "upcoming": return 1
        return 2
    return sorted(out, key=rk)

# ============================================================
# EV CALCULATOR (new)
# ============================================================

def normal_cdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def parse_odds_input(raw, fmt):
    s = safe(raw).lower()
    if not s: return None
    if fmt == "fractional":
        if s in ("evens","evs","even"): return 2.0
        if "/" in s:
            try:
                a, b = s.split("/", 1); a, b = float(a), float(b)
                return a / b + 1 if b else None
            except Exception: return None
        try:
            n = float(s); return n + 1
        except Exception: return None
    try: return float(s)
    except Exception: return None

def ev_calculation(samples_str, line, over_raw, under_raw, fmt, adj=0.0):
    samples = [float(x) for x in re.split(r"[\s,]+", safe(samples_str)) if re.match(r"^-?\d*\.?\d+$", x)]
    n = len(samples)
    if n < 2 or line is None: return None
    mu = sum(samples) / n
    var = sum((x - mu) ** 2 for x in samples) / (n - 1)
    sd = max(math.sqrt(var), 0.5)
    proj = mu + adj
    z = (line - proj) / sd
    p_under = normal_cdf(z); p_over = 1 - p_under
    d_over = parse_odds_input(over_raw, fmt); d_under = parse_odds_input(under_raw, fmt)
    sides = []
    if d_over:  sides.append({"side":"OVER",  "p":p_over,  "d":d_over,  "ev": p_over * d_over - 1})
    if d_under: sides.append({"side":"UNDER", "p":p_under, "d":d_under, "ev": p_under * d_under - 1})
    sides.sort(key=lambda x: -x["ev"])
    best = sides[0] if sides else None
    fair_p_over = (1/d_over) / ((1/d_over) + (1/d_under)) if (d_over and d_under) else None
    return {"n":n, "mu":mu, "sd":sd, "proj":proj, "p_over":p_over, "p_under":p_under,
            "best":best, "fair_p_over":fair_p_over}

# ============================================================
# RENDER ANALYSIS
# ============================================================

def cclass(conf):
    c = safe(conf).lower()
    if "high" in c: return "good"
    if "low" in c:  return "bad"
    return "mid"

def render_analysis(parsed, raw=""):
    if not parsed:
        st.error("AI returned output, but it was not valid JSON. Raw output below.")
        st.code(raw[:9000]); return
    dq = parsed.get("data_quality", {}) if isinstance(parsed.get("data_quality"), dict) else {}
    st.markdown(f"""
<div class="match-card">
  <div class="muted">Match analysis</div>
  <h2 style="margin:6px 0;">{safe(parsed.get("match_title"))}</h2>
  <span class="pill">Status: {safe(parsed.get("status_assessment"))}</span>
  <span class="pill">Model pick: {safe(parsed.get("model_pick"))}</span>
  <span class="pill {cclass(parsed.get("confidence"))}">Confidence: {safe(parsed.get("confidence"))}</span>
  <span class="pill">Cito: {safe(dq.get("cito_stats"))}</span>
  <span class="pill">Maps: {safe(dq.get("maps_vetoes"))}</span>
  <span class="pill">BetMGM: {safe(dq.get("betmgm_odds"))}</span>
  <p style="color:#CBD5E1;margin-top:12px;">{safe(parsed.get("summary"))}</p>
</div>
""", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    try: ta = round(float(parsed.get("team_a_win_probability", 0)) * 100)
    except Exception: ta = 0
    try: tb = round(float(parsed.get("team_b_win_probability", 0)) * 100)
    except Exception: tb = 0
    c1.metric("Team A", f"{ta}%")
    c2.metric("Model pick", safe(parsed.get("model_pick")) or "Unknown")
    c3.metric("Team B", f"{tb}%")
    if parsed.get("live_or_inplay_notes"):
        st.markdown("### Live / in-play notes")
        for x in parsed.get("live_or_inplay_notes", [])[:6]:
            if safe(x): st.markdown(f"- {safe(x)}")
    if parsed.get("key_context"):
        st.markdown("### Key context")
        for x in parsed.get("key_context", [])[:8]:
            if safe(x): st.markdown(f"- {safe(x)}")
    st.markdown("### Full 8-player ranking")
    rankings = parsed.get("all_8_player_rankings", [])
    if rankings:
        rank_df = pd.DataFrame(rankings)
        if "rank" in rank_df.columns: rank_df = rank_df.sort_values("rank")
        st.dataframe(rank_df, use_container_width=True)
        st.markdown("### Top player cards")
        top = rankings[:4]
        cols = st.columns(min(4, len(top)))
        for i, p in enumerate(top):
            with cols[i]:
                cor = " · corrected" if p.get("_corrected") else ""
                st.markdown(f"""
<div class="bet-card">
  <div class="muted">Rank #{safe(p.get("rank")) or i+1}{cor}</div>
  <h3 style="margin:6px 0;">{safe(p.get("player"))}</h3>
  <span class="pill">{safe(p.get("team"))}</span>
  <span class="pill">{safe(p.get("best_modes"))}</span>
  <span class="pill {cclass(p.get("confidence"))}">{safe(p.get("confidence"))}</span>
  <p style="color:#CBD5E1;margin-top:10px;">{safe(p.get("reason"))}</p>
</div>
""", unsafe_allow_html=True)
    else:
        st.info("No player rankings returned.")
    st.markdown("### Best Bets")
    bets = parsed.get("best_bets", [])
    if bets: st.dataframe(pd.DataFrame(bets), use_container_width=True)
    else: st.info("No best bets returned — usually means BetMGM odds were not discoverable.")
    st.markdown("### Player kill targets")
    props = parsed.get("player_kill_props", [])
    targets = parsed.get("best_targets_without_odds", [])
    if props: st.dataframe(pd.DataFrame(props), use_container_width=True)
    elif targets: st.dataframe(pd.DataFrame(targets), use_container_width=True)
    else: st.info("No kill targets returned.")
    st.markdown("### Map winner leans")
    maps = parsed.get("map_winner_leans", [])
    if maps: st.dataframe(pd.DataFrame(maps), use_container_width=True)
    else: st.info("No map winner leans returned.")
    st.markdown("### Avoid / Risk")
    for r in parsed.get("avoid_or_risk", []):
        st.markdown(f"""
<div class="risk-card">
  <b>{safe(r.get("selection"))}</b>
  <span class="pill bad">Risk: {safe(r.get("risk"))}</span>
  <p style="color:#CBD5E1;margin-top:8px;">{safe(r.get("reason"))}</p>
</div>
""", unsafe_allow_html=True)
    if parsed.get("sources_used"):
        st.markdown("### Sources used")
        for s in parsed.get("sources_used", []):
            if safe(s): st.markdown(f"- {safe(s)}")
    if parsed.get("final_note"):
        st.caption(safe(parsed.get("final_note")))

# ============================================================
# STATE
# ============================================================

if "saved" not in st.session_state:
    st.session_state.saved = load_json(CACHE_FILE)
if "matches" not in st.session_state:
    cached = load_json(MATCH_CACHE_FILE)
    st.session_state.matches = cached.get("matches", []) if isinstance(cached, dict) else []
if "selected_idx" not in st.session_state: st.session_state.selected_idx = 0
if "maps_df" not in st.session_state:      st.session_state.maps_df = default_maps()
if "active_key" not in st.session_state:   st.session_state.active_key = ""
if "last_calls" not in st.session_state:   st.session_state.last_calls = []

openai_key = get_secret("OPENAI_API_KEY")
cito_key   = get_secret("CITO_API_KEY")

with st.sidebar:
    st.header("Setup")
    st.write("OpenAI:", "✅ found" if openai_key else "❌ missing")
    st.write("Cito:",   "✅ found" if cito_key   else "❌ missing")
    season = st.text_input("Season", value="2026")
    model  = st.text_input("OpenAI model", value="gpt-4.1-mini")
    st.write(f"Matches loaded: **{len(st.session_state.matches)}**")
    st.write(f"Saved analyses: **{len(st.session_state.saved)}**")
    if st.button("Clear saved analyses"):
        st.session_state.saved = {}; save_json(CACHE_FILE, {}); st.rerun()
    if st.button("Clear app cache"):
        st.cache_data.clear(); st.rerun()

# ============================================================
# TABS
# ============================================================

tab_match, tab_ev, tab_rosters, tab_diag = st.tabs([
    "🎯 Match Day", "💰 EV Calculator", "👥 Rosters", "🔬 Diagnostics"
])

# ----------------- MATCH DAY (main workflow) -----------------
with tab_match:
    if st.session_state.saved:
        with st.expander("💾 Saved analyses (0 extra calls)"):
            saved_rows = []
            for k, v in st.session_state.saved.items():
                m = v.get("match", {})
                parsed = v.get("ai_parsed") or {}
                saved_rows.append({"Key":k, "Saved":v.get("saved_at",""),
                                   "Match":f"{safe(m.get('team_a'))} vs {safe(m.get('team_b'))}",
                                   "Status":safe(m.get("status")),
                                   "Model pick": safe(parsed.get("model_pick")) if isinstance(parsed, dict) else "",
                                   "Confidence": safe(parsed.get("confidence")) if isinstance(parsed, dict) else ""})
            saved_df = pd.DataFrame(saved_rows)
            st.dataframe(saved_df.drop(columns=["Key"]), use_container_width=True)
            saved_choice = st.selectbox("Load saved analysis", [r["Key"] for r in saved_rows], key="saved_choice_global")
            csave1, csave2 = st.columns(2)
            with csave1:
                if st.button("Load selected saved analysis", use_container_width=True):
                    st.session_state.active_key = saved_choice; st.success("Loaded with 0 API calls.")
            with csave2:
                if st.button("Delete selected saved analysis", use_container_width=True):
                    st.session_state.saved.pop(saved_choice, None); save_json(CACHE_FILE, st.session_state.saved); st.rerun()
            active_saved = st.session_state.saved.get(st.session_state.active_key)
            if active_saved:
                render_analysis(active_saved.get("ai_parsed"), active_saved.get("ai_raw",""))

    st.markdown("## 1) Refresh current/live matches")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("""
<div class="card">Pulls matches from Cito, Breaking Point, and OpenAI web search. Live/in-play games first.</div>
""", unsafe_allow_html=True)
    with c2:
        refresh_matches = st.button("🔄 Refresh match list", use_container_width=True, disabled=not bool(openai_key or cito_key))
        targeted_live = st.button("🔴 Force live match search", use_container_width=True, disabled=not bool(openai_key))

    if targeted_live:
        with st.spinner("Forcing AI search for live/in-play CDL matches..."):
            try:
                rows, raw, meta, notes = ai_match_list(openai_key, model)
                st.session_state.matches = dedupe_matches(rows + st.session_state.matches)
                st.session_state.last_calls.append({"ok":True,"status":"AI_LIVE_FORCE","url":"OpenAI forced live","payload":{"notes":notes,"raw":raw[:1500],"meta":meta}})
                save_json(MATCH_CACHE_FILE, {"saved_at": now(), "matches": st.session_state.matches}); st.rerun()
            except Exception as e: st.error(str(e))

    if refresh_matches:
        all_rows, all_calls = [], []
        with st.spinner("Refreshing from Cito + Breaking Point + AI..."):
            if cito_key:
                rows, calls = cito_match_list(season, 40); all_rows += rows; all_calls += calls
            rows, calls = bp_match_list(); all_rows += rows; all_calls += calls
            if openai_key:
                try:
                    rows, raw, meta, notes = ai_match_list(openai_key, model)
                    all_rows += rows
                    all_calls.append({"ok":True,"status":"AI","url":"OpenAI match search","payload":{"notes":notes,"raw":raw[:1200],"meta":meta}})
                except Exception as e:
                    all_calls.append({"ok":False,"status":"AI_ERR","url":"OpenAI match search","payload":{"error":str(e)}})
        st.session_state.matches = dedupe_matches(all_rows)
        st.session_state.last_calls = all_calls
        save_json(MATCH_CACHE_FILE, {"saved_at": now(), "matches": st.session_state.matches}); st.rerun()

    if not st.session_state.matches:
        st.warning("No matches loaded yet. Press **Refresh match list**.")
    else:
        df_matches = pd.DataFrame(st.session_state.matches)
        st.dataframe(df_matches, use_container_width=True)
        labels = [match_label(m, i) for i, m in enumerate(st.session_state.matches)]
        selected_label = st.selectbox("Select match", labels, index=min(st.session_state.selected_idx, len(labels)-1))
        st.session_state.selected_idx = int(selected_label.split(":")[0])
        match = st.session_state.matches[st.session_state.selected_idx]
        st.markdown(f"""
<div class="match-card">
  <div class="muted">{safe(match.get("start_time"))} · {safe(match.get("event"))} · {safe(match.get("source"))}</div>
  <h2 style="margin:6px 0;">{safe(match.get("team_a"))} <span class="muted">vs</span> {safe(match.get("team_b"))}</h2>
  <span class="pill">Status: {safe(match.get("status"))}</span>
  <span class="pill">Match ID: {safe(match.get("match_id")) or "not found"}</span>
</div>
""", unsafe_allow_html=True)

        # ----- MAPS -----
        st.markdown("## 2) Maps / vetoes")
        m1, m2 = st.columns([2, 1])
        with m1:
            st.markdown("""
<div class="card">Tries Cito then OpenAI web search. <b>If both fail, pick maps manually below — dropdowns use the BO7 pool.</b></div>
""", unsafe_allow_html=True)
        with m2:
            refresh_maps = st.button("🗺️ Refresh maps/vetoes", use_container_width=True, disabled=not bool(openai_key or match.get("match_id")))
            reset_maps = st.button("↺ Reset maps to default", use_container_width=True)

        if reset_maps:
            st.session_state.maps_df = default_maps(); st.rerun()

        if refresh_maps:
            found, calls = None, []
            with st.spinner("Trying Cito + AI for maps/vetoes..."):
                if match.get("match_id"):
                    found, calls = cito_maps_for_match(match.get("match_id"))
                    st.session_state.last_calls += calls
                if found is None and openai_key:
                    try:
                        found, raw, meta, parsed = ai_find_maps(openai_key, model, match)
                        st.session_state.last_calls.append({"ok": bool(found is not None), "status":"AI_MAPS","url":"OpenAI map search","payload":{"raw":raw[:1500],"parsed":parsed,"meta":meta}})
                    except Exception as e:
                        st.session_state.last_calls.append({"ok":False,"status":"AI_MAPS_ERR","url":"OpenAI map search","payload":{"error":str(e)}})
            if found is not None:
                st.session_state.maps_df = found; st.success("Maps/vetoes updated.")
            else:
                st.warning("Maps not found yet. Use the manual picker below — vetoes drop ~10 min before start.")
            st.rerun()

        # FIX #5: manual map editor with BO7 dropdowns
        st.markdown("**Manual map picker** (BO7 pool dropdowns)")
        new_rows = []
        for i, row in st.session_state.maps_df.iterrows():
            cc1, cc2, cc3, cc4 = st.columns([0.4, 1.4, 1.8, 1.4])
            with cc1: st.markdown(f"**M{int(row['Map'])}**")
            with cc2:
                mode = st.selectbox(f"Mode {i}", ["Hardpoint","Search & Destroy","Overload"],
                                    index=["Hardpoint","Search & Destroy","Overload"].index(mode_name(row["Mode"])),
                                    key=f"map_mode_{i}", label_visibility="collapsed")
            with cc3:
                pool = BO7_MAP_POOL.get(mode, [])
                options = [""] + pool
                cur = safe(row["Map Name"])
                idx = options.index(cur) if cur in options else 0
                map_name = st.selectbox(f"Map name {i}", options, index=idx, key=f"map_name_{i}", label_visibility="collapsed")
            with cc4:
                pick_options = ["", match.get("team_a"), match.get("team_b"), "League/Default"]
                cur_p = safe(row["Picked By"])
                pidx = pick_options.index(cur_p) if cur_p in pick_options else 0
                picker = st.selectbox(f"Picked by {i}", pick_options, index=pidx, key=f"map_pick_{i}", label_visibility="collapsed")
            new_rows.append({"Map": int(row["Map"]), "Mode": mode, "Map Name": map_name, "Picked By": picker})
        st.session_state.maps_df = pd.DataFrame(new_rows)

        # ----- ANALYSE -----
        st.markdown("## 3) Analyse selected match")
        key = analysis_key(match, st.session_state.maps_df, model)
        saved = st.session_state.saved.get(key)
        if saved:
            st.success(f"✅ Saved analysis from {saved.get('saved_at')} — 0 calls to re-view.")
        else:
            st.warning("No saved analysis for this exact setup. Press Analyse to run once.")
        a1, a2 = st.columns([2, 1])
        with a1:
            st.markdown("""
<div class="card">Full match-day process: Cito roster+stats (augmented by verified rosters), AI web research, BetMGM odds discovery.</div>
""", unsafe_allow_html=True)
        with a2:
            analyse = st.button("⚡ Analyse this match", use_container_width=True, disabled=not bool(openai_key))

        if analyse:
            with st.spinner("Pulling stats and running AI..."):
                try:
                    roster_df, stats_df, stat_calls = build_stats(match.get("team_a"), match.get("team_b"), season)
                    st.session_state.last_calls += stat_calls
                    parsed, raw, meta = run_ai_analysis(openai_key, model, match, st.session_state.maps_df, roster_df, stats_df)
                    st.session_state.saved[key] = {
                        "saved_at": now(), "match": match,
                        "maps":   st.session_state.maps_df.fillna("").to_dict(orient="records"),
                        "roster": roster_df.fillna("").to_dict(orient="records"),
                        "stats":  stats_df.fillna("").to_dict(orient="records"),
                        "ai_parsed": parsed, "ai_raw": raw, "ai_meta": meta,
                    }
                    save_json(CACHE_FILE, st.session_state.saved)
                    st.session_state.active_key = key; st.rerun()
                except Exception as e: st.error(str(e))

        active = st.session_state.saved.get(key)
        if active:
            st.session_state.active_key = key
            render_analysis(active.get("ai_parsed"), active.get("ai_raw",""))

        with st.expander("Stats / raw data"):
            active = st.session_state.saved.get(st.session_state.active_key)
            if active:
                st.markdown("### Roster"); st.dataframe(pd.DataFrame(active.get("roster", [])), use_container_width=True)
                st.markdown("### Player stats"); st.dataframe(pd.DataFrame(active.get("stats", [])), use_container_width=True)
                st.markdown("### Raw AI JSON"); st.json(active.get("ai_parsed"))
            else:
                st.info("No active analysis yet.")

# ----------------- EV CALCULATOR -----------------
with tab_ev:
    st.markdown("## Player Prop EV Calculator")
    st.caption("Paste recent kill counts (same mode only) + BetMGM line + odds. Get edge, EV %, fractional-Kelly stake.")
    c_a, c_b = st.columns(2)
    with c_a:
        fmt = st.radio("Odds format", ["fractional","decimal"], horizontal=True)
        bankroll = st.number_input("Bankroll (£)", value=200.0, min_value=0.0, step=10.0)
        kfrac    = st.slider("Kelly fraction", 0.05, 1.0, 0.25, 0.05)
    with c_b:
        st.markdown("**Quick guide:** Same-mode kills only (HP avg ~25, S&D ~7). At least 4 samples recommended.")

    if "ev_bets" not in st.session_state:
        st.session_state.ev_bets = [{"player":"Shotzzy","team":"OpTic Texas","mode":"Hardpoint","line":"25.5",
                                     "over_odds":"10/11","under_odds":"10/11","samples":"28, 31, 24, 27, 30, 26","adj":"0"}]
    add_col, clear_col = st.columns([1,1])
    with add_col:
        if st.button("➕ Add bet"):
            st.session_state.ev_bets.append({"player":"","team":"","mode":"Hardpoint","line":"",
                                             "over_odds":"","under_odds":"","samples":"","adj":"0"}); st.rerun()
    with clear_col:
        if st.button("🗑️ Clear all"):
            st.session_state.ev_bets = []; st.rerun()

    results = []
    for i, bet in enumerate(st.session_state.ev_bets):
        st.markdown('<div class="card">', unsafe_allow_html=True)
        r1c1, r1c2, r1c3 = st.columns([1.5, 1.5, 1])
        with r1c1: bet["player"] = st.text_input("Player", value=bet["player"], key=f"ev_p_{i}")
        with r1c2:
            team_opts = [""] + TEAMS
            cur = bet["team"] if bet["team"] in team_opts else ""
            bet["team"] = st.selectbox("Team", team_opts, index=team_opts.index(cur), key=f"ev_t_{i}")
        with r1c3:
            if st.button("Remove", key=f"ev_rm_{i}"):
                st.session_state.ev_bets.pop(i); st.rerun()
        r2c1, r2c2, r2c3, r2c4 = st.columns(4)
        with r2c1:
            bet["mode"] = st.selectbox("Mode", ["Hardpoint","Search & Destroy","Overload"],
                                       index=["Hardpoint","Search & Destroy","Overload"].index(bet["mode"]), key=f"ev_m_{i}")
        with r2c2: bet["line"]       = st.text_input("Line", value=bet["line"], key=f"ev_l_{i}", placeholder="22.5")
        with r2c3: bet["over_odds"]  = st.text_input("Over odds",  value=bet["over_odds"],  key=f"ev_o_{i}", placeholder="10/11 or 1.91")
        with r2c4: bet["under_odds"] = st.text_input("Under odds", value=bet["under_odds"], key=f"ev_u_{i}", placeholder="10/11 or 1.91")
        r3c1, r3c2 = st.columns([3,1])
        with r3c1: bet["samples"] = st.text_input("Recent kills (same mode, comma separated)", value=bet["samples"], key=f"ev_s_{i}", placeholder="28, 24, 31, 26, 29")
        with r3c2: bet["adj"] = st.text_input("Adjust ±", value=bet["adj"], key=f"ev_a_{i}")
        try: adj_val = float(bet["adj"]) if bet["adj"] else 0.0
        except: adj_val = 0.0
        try: line_val = float(bet["line"]) if bet["line"] else None
        except: line_val = None
        r = ev_calculation(bet["samples"], line_val, bet["over_odds"], bet["under_odds"], fmt, adj=adj_val)
        if r:
            best = r["best"]
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Proj", f"{r['proj']:.1f}k", f"n={r['n']}, σ={r['sd']:.1f}")
            m2.metric("P(over)", f"{r['p_over']*100:.1f}%")
            m3.metric("P(under)", f"{r['p_under']*100:.1f}%")
            if best:
                stake = max(0, (best["p"] * best["d"] - 1) / (best["d"] - 1)) * kfrac * bankroll if best["d"] > 1 else 0
                m4.metric("Best", f"{best['side']} {bet['line']}", f"EV {best['ev']*100:+.1f}%")
                m5.metric("Stake (fK)", f"£{stake:.2f}" if best["ev"] > 0 else "—")
            if r["n"] < 4:
                st.warning(f"Only {r['n']} samples — wide error bars.")
            results.append({"Player":bet["player"], "Team":bet["team"], "Mode":bet["mode"],
                            "Side": best["side"] if best else "—", "Line":bet["line"],
                            "EV%": round(best["ev"]*100, 1) if best else None,
                            "Proj": round(r["proj"], 1), "n": r["n"]})
        else:
            st.caption("Enter a line and ≥2 kill samples to evaluate.")
        st.markdown('</div>', unsafe_allow_html=True)

    if results:
        st.markdown("### Ranking")
        rdf = pd.DataFrame(results).dropna(subset=["EV%"]).sort_values("EV%", ascending=False)
        st.dataframe(rdf, use_container_width=True)
        positives = rdf[rdf["EV%"] > 0]
        if not positives.empty:
            for k in [2, 3, 4]:
                top = positives.head(k)
                if len(top) >= k:
                    label = ", ".join([f"**{r.Player}** {r.Side}" for _, r in top.iterrows()])
                    st.markdown(f"**Best {k}:** {label}")
        else:
            st.warning("Nothing +EV at these prices — 'no bet' is a valid answer.")

# ----------------- ROSTERS -----------------
with tab_rosters:
    st.markdown("## Roster Editor")
    st.caption("Verified CDL 2026 rosters baked in. Edit if a player moves mid-season; changes persist.")
    team_choice = st.selectbox("Team", TEAMS, key="roster_team_edit")
    current_players, source = get_roster_for(team_choice)
    st.markdown(f"**Source:** `{source}`")
    edited = []
    cols = st.columns(4)
    for i in range(4):
        val = current_players[i] if i < len(current_players) else ""
        with cols[i]:
            edited.append(st.text_input(f"Player {i+1}", value=val, key=f"r_{team_choice}_{i}"))
    rc1, rc2 = st.columns(2)
    if rc1.button("💾 Save override"):
        save_roster_override(team_choice, edited)
        st.success(f"Saved {team_choice}: {', '.join([p for p in edited if p])}"); st.rerun()
    if rc2.button("↩ Reset to verified"):
        reset_roster(team_choice); st.success("Reset."); st.rerun()
    st.divider()
    st.markdown("### All 2026 rosters")
    all_rows = []
    for t in TEAMS:
        plyrs, src = get_roster_for(t)
        all_rows.append({"Team": t, "Players": ", ".join(plyrs), "Source": src})
    st.dataframe(pd.DataFrame(all_rows), use_container_width=True)

# ----------------- DIAGNOSTICS -----------------
with tab_diag:
    st.markdown("## Diagnostics / Cito health")
    if cito_key:
        if st.button("Run Cito health check"):
            st.dataframe(cito_health_check(season), use_container_width=True)
            st.caption("200 + 0 rows: endpoint reachable but no usable data. 401/403: bad key. 404: wrong path.")
    else:
        st.warning("No CITO_API_KEY in Streamlit Secrets.")
    st.markdown("### Recent calls")
    if st.session_state.last_calls:
        st.dataframe(pd.DataFrame([{"OK":c.get("ok"),"Status":c.get("status"),"URL":c.get("url")} for c in st.session_state.last_calls]), use_container_width=True)
    else:
        st.info("No calls this session.")

st.caption("Analysis only. The app does not place bets and cannot guarantee profit. Odds may be unavailable or change quickly. 18+ · BeGambleAware.org · GamCare 0808 8020 133")
