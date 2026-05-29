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

st.set_page_config(page_title="CDL One-Click Analyst v13", layout="wide")

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
.mid { color:#F59E0B; }
.bad { color:#EF4444; }
.muted { color:#94A3B8; }
.big { font-size:32px; font-weight:900; }
div[data-testid="stMetric"] {
    background: rgba(15,23,42,.72);
    border: 1px solid rgba(148,163,184,.16);
    padding: 16px;
    border-radius: 18px;
}
.stButton > button {
    border-radius: 14px;
    font-weight: 800;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="hero-title">CDL <span class="accent">One‑Click Analyst v13</span></div>
  <div class="hero-sub">
    Built for match day: refresh live/current matches, select a game, analyse it, rank all 8 players, and save the result. 
    The selected match analysis uses Cito stats, Breaking Point context, OpenAI web research, map/veto discovery and BetMGM odds discovery where available.
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# CONFIG
# ============================================================

CACHE_FILE = Path("v12_saved_analyses.json")
MATCH_CACHE_FILE = Path("v12_match_cache.json")
BP_MATCHES_URL = "https://breakingpoint.gg/matches"
BP_TEAMS_URL = "https://breakingpoint.gg/cdl/teams-and-players"
CITO_ROOTS = ["https://api.citoapi.com/api/v1/cod", "https://api.citoapi.com/v1/cod"]

TEAMS = [
    "Boston Breach", "Carolina Royal Ravens", "Cloud9 New York", "FaZe Vegas",
    "G2 Minnesota", "Los Angeles Thieves", "Miami Heretics", "OpTic Texas",
    "Paris Gentle Mates", "Riyadh Falcons", "Toronto KOI", "Vancouver Surge",
]
MODES = ["Hardpoint", "Search & Destroy", "Overload", "Hardpoint", "Search & Destroy"]

TEAM_SLUGS = {t: re.sub(r"[^a-z0-9-]", "", t.lower().replace("&", "and").replace(" ", "-")) for t in TEAMS}
TEAM_SLUGS["FaZe Vegas"] = "faze-vegas"
TEAM_SLUGS["OpTic Texas"] = "optic-texas"
SLUG_TO_TEAM = {v:k for k,v in TEAM_SLUGS.items()}

# Fallback profiles only stop blank screens if Cito/BP fails.
PRIORS = {
    "Simp": [96, 97, 94], "Cellium": [94, 98, 93], "Scrap": [96, 92, 95],
    "HyDra": [96, 93, 95], "aBeZy": [95, 94, 93], "Shotzzy": [95, 93, 94],
    "Dashy": [92, 95, 91], "Kremp": [94, 91, 93], "JoeDeceives": [92, 94, 92],
    "Pred": [93, 91, 92], "Drazah": [91, 92, 90], "Abuzah": [90, 92, 90],
    "CleanX": [91, 89, 90], "Insight": [88, 93, 87], "Envoy": [91, 89, 90],
    "Skyz": [89, 92, 88], "Sib": [91, 88, 91], "Ghosty": [90, 90, 90],
    "KiSMET": [90, 88, 90], "Nero": [90, 87, 89], "Huke": [89, 87, 88],
    "Lurqxx": [89, 86, 88], "Standy": [88, 86, 87], "Lucky": [86, 88, 87],
    "Afro": [88, 85, 87], "Spart": [86, 86, 86], "Mamba": [86, 83, 85],
    "Nastie": [89, 87, 88], "Neptune": [89, 86, 88], "ReeaL": [88, 86, 87],
    "Wevy": [84, 84, 84], "Exceed": [84, 82, 83], "Fire": [83, 83, 83],
}

ROSTER_COLS = ["Team", "Player", "Source"]
STAT_COLS = ["Team", "Player", "Mode", "Score", "KD", "KP10", "KPR", "ProjectedKills", "Source"]

# ============================================================
# BASIC HELPERS
# ============================================================

def safe(x):
    return "" if x is None else str(x).strip()

def now():
    return datetime.now().strftime("%d %b %Y %H:%M")

def slug(x):
    return re.sub(r"[^a-z0-9-]", "", safe(x).lower().replace("&", "and").replace(" ", "-"))

def norm_team(x):
    s = safe(x)
    if not s:
        return ""
    sl = slug(s)
    if sl in SLUG_TO_TEAM:
        return SLUG_TO_TEAM[sl]
    for t in TEAMS:
        if s.lower() == t.lower() or t.lower() in s.lower() or s.lower() in t.lower():
            return t
    return s

def mode_name(x):
    m = safe(x).lower()
    if "search" in m or "snd" in m or "s&d" in m:
        return "Search & Destroy"
    if "overload" in m or "ovl" in m or "control" in m:
        return "Overload"
    return "Hardpoint"

def to_num(x, default=0.0):
    try:
        s = re.sub(r"[^0-9.\-]", "", safe(x))
        return float(s) if s not in ["", ".", "-"] else default
    except Exception:
        return default

def get_secret(name):
    try:
        return st.secrets.get(name, "")
    except Exception:
        return ""

def load_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def short_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:18]

def empty_roster():
    return pd.DataFrame(columns=ROSTER_COLS)

def empty_stats():
    return pd.DataFrame(columns=STAT_COLS)

def default_maps():
    return pd.DataFrame({
        "Map": [1,2,3,4,5],
        "Mode": MODES,
        "Map Name": ["", "", "", "", ""],
        "Picked By": ["", "", "", "", ""],
    })

def maps_to_text(df):
    lines = []
    for _, r in df.iterrows():
        lines.append(f"Map {int(r['Map'])}: {safe(r['Mode'])} | map: {safe(r['Map Name']) or 'unknown'} | picked by: {safe(r['Picked By']) or 'unknown'}")
    return "\n".join(lines)

def match_label(m, i):
    live = "🔴 LIVE" if safe(m.get("status")).lower() in ["live", "in-play", "in play"] else "🟢"
    return f"{i}: {live} {safe(m.get('start_time'))} — {safe(m.get('team_a'))} vs {safe(m.get('team_b'))} — {safe(m.get('event'))} [{safe(m.get('source'))}]"

def analysis_key(match, maps_df, model):
    return short_hash(f"{match.get('team_a')}|{match.get('team_b')}|{match.get('start_time')}|{maps_to_text(maps_df)}|{model}")

def nested(d, paths):
    for path in paths:
        cur, ok = d, True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and safe(cur):
            return cur
    return ""

def as_list(payload):
    d = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ["players", "matches", "items", "results", "data", "maps"]:
            if isinstance(d.get(k), list):
                return d[k]
    return []

def extract_json(text):
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", cleaned)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None

# ============================================================
# CITO
# ============================================================

def cito_headers():
    key = get_secret("CITO_API_KEY")
    h = {"accept": "application/json", "user-agent": "CDL-v12"}
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
            try:
                payload = r.json()
            except Exception:
                payload = {"raw_text": r.text[:1200]}
            res = {"ok": r.ok, "status": r.status_code, "url": r.url, "payload": payload}
            attempts.append(res)
            if r.ok:
                return res
        except Exception as e:
            attempts.append({"ok": False, "status": "ERR", "url": root + path, "payload": {"error": str(e)}})
    res = attempts[-1] if attempts else {"ok": False, "status": "ERR", "url": path, "payload": {"error": "No attempts"}}
    res["attempts"] = attempts
    return res

@st.cache_data(ttl=120, show_spinner=True)
def cito_match_list(season, limit):
    endpoints = [
        ("/matches/upcoming", {"season": season, "limit": limit}),
        ("/matches/live", {"season": season, "limit": limit}),
        ("/cdl/schedule", {"season": season, "limit": limit}),
    ]
    calls, rows = [], []
    for path, params in endpoints:
        call = cito_get(path, tuple(params.items()))
        calls.append(call)
        if not call["ok"]:
            continue
        for m in as_list(call["payload"]):
            if not isinstance(m, dict):
                continue
            blob = str(m)
            a = norm_team(nested(m, ["team1.name","teams.team1.name","homeTeam.name","teamA.name","team1.slug","teams.team1.slug","team1"]))
            b = norm_team(nested(m, ["team2.name","teams.team2.name","awayTeam.name","teamB.name","team2.slug","teams.team2.slug","team2"]))
            found = [t for t in TEAMS if t.lower() in blob.lower()]
            if not a and len(found) >= 1: a = found[0]
            if not b and len(found) >= 2: b = found[1]
            if a and b:
                status = safe(nested(m, ["status","state","matchStatus"])) or ("live" if "live" in path else "upcoming")
                rows.append({
                    "start_time": safe(nested(m, ["startsAt","startTime","scheduledAt","matchDate","date"])) or "",
                    "event": safe(nested(m, ["event.name","tournament.name","event","round","stage.name"])) or "CDL",
                    "team_a": a,
                    "team_b": b,
                    "status": status,
                    "source": "Cito",
                    "match_id": safe(nested(m, ["id","matchId","bpMatchId"])),
                })
    return rows, calls

@st.cache_data(ttl=120, show_spinner=True)
def cito_maps_for_match(match_id):
    if not match_id:
        return None, []
    endpoints = [
        f"/matches/{match_id}/maps",
        f"/matches/{match_id}/vetoes",
        f"/matches/{match_id}",
    ]
    calls = []
    for ep in endpoints:
        call = cito_get(ep, ())
        calls.append(call)
        if not call["ok"]:
            continue
        payload = call["payload"]
        items = as_list(payload)
        if not items and isinstance(payload, dict):
            for key in ["maps", "vetoes", "games"]:
                if isinstance(payload.get(key), list):
                    items = payload[key]
                    break
        rows = []
        for i, mp in enumerate(items[:5], start=1):
            if not isinstance(mp, dict):
                continue
            rows.append({
                "Map": i,
                "Mode": mode_name(nested(mp, ["mode","gameMode","game.mode","type"])),
                "Map Name": safe(nested(mp, ["mapName","map.name","name","map"])),
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
        if not call["ok"]:
            continue
        for p in as_list(call["payload"]):
            if not isinstance(p, dict):
                continue
            name = safe(nested(p, ["ign","playerName","gamertag","handle","name"]))
            pteam = norm_team(nested(p, ["currentTeam.name","team.name","teamName","team","currentTeam.slug","team.slug"])) or team
            if name and pteam == team:
                rows.append({"Team": team, "Player": name, "Source": "Cito roster"})
        if rows:
            break
    return (pd.DataFrame(rows, columns=ROSTER_COLS).drop_duplicates() if rows else empty_roster()), calls

@st.cache_data(ttl=21600, show_spinner=True)
def cito_player_stats(player, season):
    calls = []
    for candidate in dict.fromkeys([player, slug(player), player.lower()]):
        if not candidate:
            continue
        call = cito_get(f"/players/{candidate}/stats", tuple({"season": season}.items()))
        calls.append(call)
        if call["ok"]:
            return call["payload"], calls
    return {}, calls

# ============================================================
# BREAKING POINT
# ============================================================

@st.cache_data(ttl=120, show_spinner=False)
def page_text(url):
    r = requests.get(url, headers={"user-agent":"Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script","style","noscript"]):
        tag.decompose()
    return "\n".join(x.strip() for x in soup.get_text("\n").splitlines() if x.strip())

@st.cache_data(ttl=120, show_spinner=True)
def bp_match_list():
    try:
        text = " ".join(page_text(BP_MATCHES_URL).splitlines())
    except Exception as e:
        return [], [{"ok": False, "status": "ERR", "url": BP_MATCHES_URL, "payload": {"error": str(e)}}]

    alt = "|".join(map(re.escape, TEAMS))
    rows = []

    # Typical BP card text pattern.
    pat = rf"(LIVE|~\d+\s+(?:minutes?|hours?|days?))?\s*(CDL\s+(?:Major|Minor|Champs)[^~]*?)\s+({alt}|TBD)\s+0\s+({alt}|TBD)\s+0"
    for m in re.finditer(pat, text, flags=re.I):
        start = safe(m.group(1)) or ""
        event = safe(m.group(2)) or "CDL"
        a, b = safe(m.group(3)), safe(m.group(4))
        if a != "TBD" and b != "TBD" and a and b and a != b:
            rows.append({
                "start_time": start,
                "event": event,
                "team_a": a,
                "team_b": b,
                "status": "live" if start.lower() == "live" else "upcoming",
                "source": "Breaking Point",
                "match_id": "",
            })

    # Simple fallback pattern.
    pat2 = rf"({alt})\s+(?:vs|v|VS)\s+({alt})"
    for m in re.finditer(pat2, text):
        a, b = safe(m.group(1)), safe(m.group(2))
        row = {"start_time": "", "event": "CDL", "team_a": a, "team_b": b, "status": "unknown", "source": "Breaking Point", "match_id": ""}
        if a and b and a != b:
            rows.append(row)

    return dedupe_matches(rows), [{"ok": True, "status": 200, "url": BP_MATCHES_URL, "payload": {"matches": len(rows)}}]

@st.cache_data(ttl=21600, show_spinner=False)
def bp_rosters():
    try:
        lines = page_text(BP_TEAMS_URL).splitlines()
    except Exception:
        return {}
    out = {t: [] for t in TEAMS}
    active, team, collecting = False, "", False
    for line in lines:
        if line == "# CDL Teams":
            active = True
            continue
        if line == "# Players":
            break
        if not active:
            continue
        if line in TEAMS:
            team, collecting = line, False
            continue
        if team and line == "Players":
            collecting = True
            continue
        if team and collecting and 1 < len(line) < 26 and line.lower() not in ["players","coach","team stats","matches","news"]:
            if line not in out[team]:
                out[team].append(line)
    return {k:v for k,v in out.items() if v}

# ============================================================
# STATS MODEL
# ============================================================

def fallback_rows(team, player):
    hp, snd, ovl = PRIORS.get(player, [74,74,74])
    return [
        {"Team": team, "Player": player, "Mode": "Hardpoint", "Score": hp, "KD": None, "KP10": None, "KPR": None, "ProjectedKills": round(18 + (hp - 70) * 0.18, 1), "Source": "Fallback profile"},
        {"Team": team, "Player": player, "Mode": "Search & Destroy", "Score": snd, "KD": None, "KP10": None, "KPR": None, "ProjectedKills": round(5 + (snd - 70) * 0.06, 1), "Source": "Fallback profile"},
        {"Team": team, "Player": player, "Mode": "Overload", "Score": ovl, "KD": None, "KP10": None, "KPR": None, "ProjectedKills": round(18 + (ovl - 70) * 0.16, 1), "Source": "Fallback profile"},
    ]

def parse_stats(player, team, payload):
    d = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(d, dict):
        return []
    info = d.get("player", {}) if isinstance(d.get("player"), dict) else {}
    name = safe(info.get("ign") or info.get("name") or player)
    by = d.get("byMode", {}) if isinstance(d.get("byMode"), dict) else {}
    overall = d.get("overall", {}) if isinstance(d.get("overall"), dict) else {}
    modes = {
        "hardpoint": "Hardpoint", "hp": "Hardpoint",
        "searchAndDestroy": "Search & Destroy", "search_and_destroy": "Search & Destroy", "snd": "Search & Destroy",
        "overload": "Overload", "ovl": "Overload", "control": "Overload"
    }
    rows = []
    for key, mode in modes.items():
        m = by.get(key)
        if not isinstance(m, dict):
            continue
        kd = to_num(m.get("kd"), to_num(overall.get("kd"), 1))
        kp10 = to_num(m.get("killsPer10"), 0)
        dmg10 = to_num(m.get("damagePer10"), 0)
        kpr = to_num(m.get("killsPerRound"), 0)

        if mode == "Search & Destroy":
            score = 55 + kpr * 45 + (kd - 1) * 18
            proj = max(3, round(kpr * 11 if kpr else 5 + (score - 70) * 0.06, 1))
        else:
            score = 50 + kp10 * 1.75 + dmg10 / 180 + (kd - 1) * 16
            proj = max(10, round(kp10 * 2.5 if kp10 else 18 + (score - 70) * 0.18, 1))

        rows.append({
            "Team": team, "Player": name, "Mode": mode, "Score": round(score, 2),
            "KD": kd, "KP10": kp10, "KPR": kpr, "ProjectedKills": proj, "Source": "Cito player stats"
        })
    return rows

def build_stats(team_a, team_b, season):
    calls = []
    bp_map = bp_rosters()
    roster_frames, stat_rows = [], []

    for team in [team_a, team_b]:
        roster, rcalls = cito_roster(team)
        calls += rcalls
        if roster.empty and team in bp_map:
            roster = pd.DataFrame([{"Team": team, "Player": p, "Source": "Breaking Point roster"} for p in bp_map[team]], columns=ROSTER_COLS)

        roster_frames.append(roster)

        if not roster.empty:
            for _, r in roster.iterrows():
                payload, pcalls = cito_player_stats(r["Player"], season)
                calls += pcalls
                parsed = parse_stats(r["Player"], team, payload)
                stat_rows += parsed if parsed else fallback_rows(team, r["Player"])

    roster_df = pd.concat(roster_frames, ignore_index=True).drop_duplicates() if roster_frames else empty_roster()
    stats_df = pd.DataFrame(stat_rows, columns=STAT_COLS).drop_duplicates() if stat_rows else empty_stats()
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
        {"tools": [{"type": "web_search"}], "tool_choice": "required" if require_search else "auto"},
        {"tools": [{"type": "web_search_preview"}], "tool_choice": "required" if require_search else "auto"},
        {"tools": [], "tool_choice": "none"},
    ]
    last_error = None
    for a in attempts:
        try:
            kwargs = {"model": model, "input": prompt}
            if a["tools"]:
                kwargs["tools"] = a["tools"]
                kwargs["tool_choice"] = a["tool_choice"]
            resp = c.responses.create(**kwargs)
            return resp.output_text, {"model": model, "attempt": a}
        except Exception as e:
            last_error = str(e)
    raise RuntimeError(last_error or "OpenAI call failed")

def ai_match_list(api_key, model):
    prompt = """
Use web search to find current LIVE, in-play, upcoming and recently-started Call of Duty League (CDL) matches.

This is for match-day betting analysis, so live/in-play matches are highest priority.
Search especially:
- Breaking Point matches page
- official Call of Duty League schedule
- CDL event pages
- CDL Major qualifier live/current fixtures
- Toronto KOI vs Carolina Royal Ravens / Ravens if currently active
- reputable esports schedule pages

Return ONLY valid JSON:
{
  "notes": "short confidence note",
  "matches": [
    {"start_time":"", "event":"", "team_a":"", "team_b":"", "status":"live/upcoming/in-play/unknown", "source":""}
  ]
}

Rules:
- Include live/in-play matches first if any are being played.
- Include upcoming matches after live matches.
- Do not invent matches.
- If Toronto KOI vs Carolina Royal Ravens is currently being played or listed live, include it.
"""
    raw, meta = openai_call(api_key, model, prompt, True)
    parsed = extract_json(raw) or {"notes": "AI output not JSON", "matches": []}
    rows = []
    for m in parsed.get("matches", []) if isinstance(parsed, dict) else []:
        if not isinstance(m, dict):
            continue
        a, b = safe(m.get("team_a")), safe(m.get("team_b"))
        if a and b and a.lower() != b.lower():
            rows.append({
                "start_time": safe(m.get("start_time")),
                "event": safe(m.get("event")) or "CDL",
                "team_a": norm_team(a),
                "team_b": norm_team(b),
                "status": safe(m.get("status")) or "unknown",
                "source": safe(m.get("source")) or "OpenAI web search",
                "match_id": "",
            })
    return rows, raw, meta, safe(parsed.get("notes"))

def ai_maps_prompt(match):
    return f"""
Use web search to find the map vetoes/maps for this current or upcoming CDL match:

{match.get("team_a")} vs {match.get("team_b")}
Event/time: {match.get("event")} {match.get("start_time")}

Look at Breaking Point, official CDL, broadcasts/live match pages, and public match pages.

Return ONLY valid JSON:
{{
  "maps_found": true,
  "confidence": "High/Medium/Low",
  "maps": [
    {{"map":1, "mode":"Hardpoint", "map_name":"", "picked_by":""}},
    {{"map":2, "mode":"Search & Destroy", "map_name":"", "picked_by":""}},
    {{"map":3, "mode":"Overload", "map_name":"", "picked_by":""}},
    {{"map":4, "mode":"Hardpoint", "map_name":"", "picked_by":""}},
    {{"map":5, "mode":"Search & Destroy", "map_name":"", "picked_by":""}}
  ],
  "sources_used": [""],
  "note": ""
}}

If maps are not available yet, return maps_found=false and use empty map_name values.
Do not invent map names.
"""

def ai_find_maps(api_key, model, match):
    raw, meta = openai_call(api_key, model, ai_maps_prompt(match), True)
    parsed = extract_json(raw)
    rows = []
    if isinstance(parsed, dict) and parsed.get("maps_found") and isinstance(parsed.get("maps"), list):
        for i, mp in enumerate(parsed["maps"][:5], start=1):
            rows.append({
                "Map": int(mp.get("map") or i),
                "Mode": mode_name(mp.get("mode") or MODES[i-1]),
                "Map Name": safe(mp.get("map_name")),
                "Picked By": norm_team(mp.get("picked_by")) if safe(mp.get("picked_by")) else "",
            })
    if rows:
        while len(rows) < 5:
            i = len(rows) + 1
            rows.append({"Map": i, "Mode": MODES[i-1], "Map Name": "", "Picked By": ""})
        return pd.DataFrame(rows), raw, meta, parsed
    return None, raw, meta, parsed

def analysis_prompt(match, maps_df, roster_df, stats_df, live_mode):
    roster_csv = roster_df.to_csv(index=False)[:9000] if not roster_df.empty else "No roster rows loaded."
    stats_csv = stats_df.to_csv(index=False)[:18000] if not stats_df.empty else "No stat rows loaded."
    return f"""
You are a Call of Duty League match-day betting analyst.

Analyse this match:
{match.get("team_a")} vs {match.get("team_b")}
Status/time/event/source:
{match.get("status")} | {match.get("start_time")} | {match.get("event")} | {match.get("source")}

The user is using BetMGM and cares about:
- player kills per map
- team to win a map
- live/in-play usefulness
- decimal odds if discoverable

CDL map format:
Map 1 Hardpoint
Map 2 Search & Destroy
Map 3 Overload
Map 4 Hardpoint
Map 5 Search & Destroy

Current map/veto info:
{maps_to_text(maps_df)}

Structured roster data from Cito/Breaking Point:
{roster_csv}

Structured player mode stats from Cito/fallback model:
{stats_csv}

Instructions:
1. Use the structured stats as the base.
2. Use web search for current context: live state if available, recent results, roster/sub news, Breaking Point stats/context, official CDL, map/veto information and BetMGM/market info where publicly discoverable.
3. If maps are missing, explain that confidence is lower and still recommend by mode.
4. Try to find BetMGM decimal odds for player kills per map and team map winner. Do not invent odds. If unavailable, set odds_found=false or BetMGM odds as not found.
5. If this is live/in-play, include live/in-play watch notes: what to check before taking a player or map winner.
6. Return practical output: best players, best targets without odds, map winner leans, avoid list.
7. Do not place bets or guarantee profit.
8. Always rank all expected 8 starting players from 1 best to 8 worst in all_8_player_rankings. If only 7 players are discoverable, explain the missing player in data_quality.note but still rank all discoverable players.
9. The player ranking should be based on structured Cito/BP stats first, then current web research/context second.

Return ONLY valid JSON:
{{
  "match_title": "{match.get("team_a")} vs {match.get("team_b")}",
  "summary": "",
  "status_assessment": "live/upcoming/in-play/unknown",
  "model_pick": "",
  "team_a_win_probability": 0.0,
  "team_b_win_probability": 0.0,
  "confidence": "High/Medium/Low",
  "data_quality": {{
    "cito_stats": "Good/Partial/Missing",
    "breakingpoint_context": "Good/Partial/Missing",
    "maps_vetoes": "Found/Partial/Not found",
    "betmgm_odds": "Found/Partial/Not found",
    "note": ""
  }},
  "live_or_inplay_notes": ["", "", ""],
  "key_context": ["", "", ""],
  "all_8_player_rankings": [
    {{"rank":1, "player":"", "team":"", "overall_rating":0.0, "best_modes":"", "projected_strength":"", "reason":"", "confidence":"High/Medium/Low"}},
    {{"rank":2, "player":"", "team":"", "overall_rating":0.0, "best_modes":"", "projected_strength":"", "reason":"", "confidence":"High/Medium/Low"}},
    {{"rank":3, "player":"", "team":"", "overall_rating":0.0, "best_modes":"", "projected_strength":"", "reason":"", "confidence":"High/Medium/Low"}},
    {{"rank":4, "player":"", "team":"", "overall_rating":0.0, "best_modes":"", "projected_strength":"", "reason":"", "confidence":"High/Medium/Low"}},
    {{"rank":5, "player":"", "team":"", "overall_rating":0.0, "best_modes":"", "projected_strength":"", "reason":"", "confidence":"High/Medium/Low"}},
    {{"rank":6, "player":"", "team":"", "overall_rating":0.0, "best_modes":"", "projected_strength":"", "reason":"", "confidence":"High/Medium/Low"}},
    {{"rank":7, "player":"", "team":"", "overall_rating":0.0, "best_modes":"", "projected_strength":"", "reason":"", "confidence":"High/Medium/Low"}},
    {{"rank":8, "player":"", "team":"", "overall_rating":0.0, "best_modes":"", "projected_strength":"", "reason":"", "confidence":"High/Medium/Low"}}
  ],
  "best_players_overall": [
    {{"rank":1, "player":"", "team":"", "best_modes":"", "reason":"", "confidence":"High/Medium/Low"}}
  ],
  "best_targets_without_odds": [
    {{"player":"", "team":"", "map":1, "mode":"", "projected_kills":0.0, "target_note":"", "confidence":"High/Medium/Low"}}
  ],
  "player_kill_props": [
    {{"player":"", "team":"", "map":1, "mode":"", "line":null, "over_decimal_odds":null, "under_decimal_odds":null, "projected_kills":0.0, "over_probability":0.0, "edge_percent":null, "recommendation":"Over/Under/No Bet/Target if line appears", "confidence":"High/Medium/Low", "reason":"", "odds_found":false}}
  ],
  "map_winner_leans": [
    {{"map":1, "mode":"", "map_name":"", "lean_team":"", "probability":0.0, "betmgm_decimal_odds":null, "edge_percent":null, "confidence":"High/Medium/Low", "reason":""}}
  ],
  "best_bets": [
    {{"rank":1, "market":"Player kills per map/Map winner", "selection":"", "line":null, "odds":null, "edge_percent":null, "confidence":"High/Medium/Low", "reason":""}}
  ],
  "avoid_or_risk": [
    {{"selection":"", "reason":"", "risk":"High/Medium/Low"}}
  ],
  "sources_used": [""],
  "final_note": "Analysis only. Odds can move."
}}
"""

def run_ai_analysis(api_key, model, match, maps_df, roster_df, stats_df):
    live_mode = safe(match.get("status")).lower() in ["live", "in-play", "in play"]
    raw, meta = openai_call(api_key, model, analysis_prompt(match, maps_df, roster_df, stats_df, live_mode), True)
    parsed = extract_json(raw)
    return parsed, raw, meta

# ============================================================
# MATCH MERGE
# ============================================================


def cito_health_check(season):
    checks = []
    tests = [
        ("/matches/upcoming", {"season": season, "limit": 5}),
        ("/matches/live", {"season": season, "limit": 5}),
        ("/cdl/schedule", {"season": season, "limit": 5}),
    ]
    for path, params in tests:
        call = cito_get(path, tuple(params.items()))
        count = len(as_list(call.get("payload", {}))) if isinstance(call, dict) else 0
        checks.append({
            "Endpoint": path,
            "Status": call.get("status"),
            "OK": call.get("ok"),
            "Rows found": count,
            "URL": call.get("url"),
        })
    return pd.DataFrame(checks)

def dedupe_matches(rows):
    out, seen = [], set()
    for m in rows:
        a, b = safe(m.get("team_a")), safe(m.get("team_b"))
        if not a or not b:
            continue
        key = tuple(sorted([a.lower(), b.lower()])) + (safe(m.get("start_time")).lower(),)
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    # live first, then upcoming
    def rank(m):
        s = safe(m.get("status")).lower()
        if s in ["live", "in-play", "in play"]:
            return 0
        if s == "upcoming":
            return 1
        return 2
    return sorted(out, key=rank)

# ============================================================
# RENDERING
# ============================================================

def cclass(conf):
    c = safe(conf).lower()
    if "high" in c:
        return "good"
    if "low" in c:
        return "bad"
    return "mid"

def render_analysis(parsed, raw=""):
    if not parsed:
        st.error("AI returned output, but it was not valid JSON. Raw output below.")
        st.code(raw[:9000])
        return

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
            if safe(x):
                st.markdown(f"- {safe(x)}")

    if parsed.get("key_context"):
        st.markdown("### Key context")
        for x in parsed.get("key_context", [])[:8]:
            if safe(x):
                st.markdown(f"- {safe(x)}")

    st.markdown("### Full 8-player ranking")
    rankings = parsed.get("all_8_player_rankings", [])
    if rankings:
        rank_df = pd.DataFrame(rankings)
        if "rank" in rank_df.columns:
            rank_df = rank_df.sort_values("rank")
        st.dataframe(rank_df, use_container_width=True)

        st.markdown("### Top player cards")
        top_players = rankings[:4]
        cols = st.columns(min(4, len(top_players)))
        for i, p in enumerate(top_players):
            with cols[i]:
                st.markdown(f"""
<div class="bet-card">
  <div class="muted">Rank #{safe(p.get("rank")) or i+1}</div>
  <h3 style="margin:6px 0;">{safe(p.get("player"))}</h3>
  <span class="pill">{safe(p.get("team"))}</span>
  <span class="pill">{safe(p.get("best_modes"))}</span>
  <span class="pill {cclass(p.get("confidence"))}">{safe(p.get("confidence"))}</span>
  <p style="color:#CBD5E1;margin-top:10px;">{safe(p.get("reason"))}</p>
</div>
""", unsafe_allow_html=True)
    else:
        st.markdown("### Best players overall")
        players = parsed.get("best_players_overall", [])
        if players:
            cols = st.columns(min(4, len(players)))
            for i, p in enumerate(players[:4]):
                with cols[i]:
                    st.markdown(f"""
<div class="bet-card">
  <div class="muted">#{safe(p.get("rank")) or i+1}</div>
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
    if bets:
        st.dataframe(pd.DataFrame(bets), use_container_width=True)
    else:
        st.info("No best bets returned. This usually means BetMGM odds were not found or edge was too weak.")

    st.markdown("### Player kill targets")
    targets = parsed.get("best_targets_without_odds", [])
    props = parsed.get("player_kill_props", [])
    if props:
        st.dataframe(pd.DataFrame(props), use_container_width=True)
    elif targets:
        st.dataframe(pd.DataFrame(targets), use_container_width=True)
    else:
        st.info("No player kill targets returned.")

    st.markdown("### Map winner leans")
    maps = parsed.get("map_winner_leans", [])
    if maps:
        st.dataframe(pd.DataFrame(maps), use_container_width=True)
    else:
        st.info("No map winner leans returned.")

    st.markdown("### Avoid / Risk")
    risks = parsed.get("avoid_or_risk", [])
    if risks:
        for r in risks:
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
            if safe(s):
                st.markdown(f"- {safe(s)}")

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
if "selected_idx" not in st.session_state:
    st.session_state.selected_idx = 0
if "maps_df" not in st.session_state:
    st.session_state.maps_df = default_maps()
if "active_key" not in st.session_state:
    st.session_state.active_key = ""
if "last_calls" not in st.session_state:
    st.session_state.last_calls = []

openai_key = get_secret("OPENAI_API_KEY")
cito_key = get_secret("CITO_API_KEY")

with st.sidebar:
    st.header("Setup")
    st.write("OpenAI:", "✅ found" if openai_key else "❌ missing")
    st.write("Cito:", "✅ found" if cito_key else "❌ missing")
    season = st.text_input("Season", value="2026")
    model = st.text_input("OpenAI model", value="gpt-4.1-mini")
    st.write(f"Matches loaded: **{len(st.session_state.matches)}**")
    st.write(f"Saved analyses: **{len(st.session_state.saved)}**")
    if st.button("Clear saved analyses"):
        st.session_state.saved = {}
        save_json(CACHE_FILE, {})
        st.rerun()
    if st.button("Clear app cache"):
        st.cache_data.clear()
        st.rerun()


# ============================================================
# SAVED ANALYSES QUICK LOAD
# ============================================================

if st.session_state.saved:
    with st.expander("💾 Saved analyses - load without spending more tokens/Cito calls"):
        saved_rows = []
        for k, v in st.session_state.saved.items():
            m = v.get("match", {})
            parsed = v.get("ai_parsed") or {}
            saved_rows.append({
                "Key": k,
                "Saved": v.get("saved_at", ""),
                "Match": f"{safe(m.get('team_a'))} vs {safe(m.get('team_b'))}",
                "Status": safe(m.get("status")),
                "Model pick": safe(parsed.get("model_pick")) if isinstance(parsed, dict) else "",
                "Confidence": safe(parsed.get("confidence")) if isinstance(parsed, dict) else "",
            })
        saved_df = pd.DataFrame(saved_rows)
        st.dataframe(saved_df.drop(columns=["Key"]), use_container_width=True)
        saved_choice = st.selectbox("Load saved analysis", [r["Key"] for r in saved_rows], key="saved_choice_global")
        csave1, csave2 = st.columns(2)
        with csave1:
            if st.button("Load selected saved analysis", use_container_width=True):
                st.session_state.active_key = saved_choice
                st.success("Saved analysis loaded below. No API calls used.")
        with csave2:
            if st.button("Delete selected saved analysis", use_container_width=True):
                st.session_state.saved.pop(saved_choice, None)
                save_json(CACHE_FILE, st.session_state.saved)
                st.rerun()

        active_saved = st.session_state.saved.get(st.session_state.active_key)
        if active_saved:
            render_analysis(active_saved.get("ai_parsed"), active_saved.get("ai_raw", ""))


# ============================================================
# MAIN ONE-PAGE WORKFLOW
# ============================================================

st.markdown("## 1) Refresh current/live matches")

c1, c2 = st.columns([2, 1])
with c1:
    st.markdown("""
<div class="card">
  This button gets the match list from <b>Cito</b>, <b>Breaking Point</b> and <b>OpenAI web search</b>. 
  It is designed to include live/in-play games where available.
</div>
""", unsafe_allow_html=True)
with c2:
    refresh_matches = st.button("🔄 Refresh match list", use_container_width=True, disabled=not bool(openai_key or cito_key))
    targeted_live = st.button("🔴 Force live match search", use_container_width=True, disabled=not bool(openai_key))

if targeted_live:
    with st.spinner("Forcing AI search for live/in-play CDL matches..."):
        try:
            rows, raw, meta, notes = ai_match_list(openai_key, model)
            st.session_state.matches = dedupe_matches(rows + st.session_state.matches)
            st.session_state.last_calls.append({"ok": True, "status": "AI_LIVE_FORCE", "url": "OpenAI forced live match search", "payload": {"notes": notes, "raw": raw[:1500], "meta": meta}})
            save_json(MATCH_CACHE_FILE, {"saved_at": now(), "matches": st.session_state.matches})
            st.rerun()
        except Exception as e:
            st.error(str(e))

if refresh_matches:
    all_rows, all_calls = [], []
    with st.spinner("Refreshing matches from Cito, Breaking Point and AI web search..."):
        if cito_key:
            rows, calls = cito_match_list(season, 40)
            all_rows += rows
            all_calls += calls
        rows, calls = bp_match_list()
        all_rows += rows
        all_calls += calls
        if openai_key:
            try:
                rows, raw, meta, notes = ai_match_list(openai_key, model)
                all_rows += rows
                all_calls.append({"ok": True, "status": "AI", "url": "OpenAI live/upcoming match search", "payload": {"notes": notes, "raw": raw[:1200], "meta": meta}})
            except Exception as e:
                all_calls.append({"ok": False, "status": "AI_ERR", "url": "OpenAI live/upcoming match search", "payload": {"error": str(e)}})

    st.session_state.matches = dedupe_matches(all_rows)
    st.session_state.last_calls = all_calls
    save_json(MATCH_CACHE_FILE, {"saved_at": now(), "matches": st.session_state.matches})
    st.rerun()

if not st.session_state.matches:
    st.warning("No matches loaded yet. Press **Refresh match list**.")
    st.stop()

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

st.markdown("## 2) Maps / vetoes")

m1, m2 = st.columns([2, 1])
with m1:
    st.markdown("""
<div class="card">
  Maps update often and may only appear close to start time. Use <b>Refresh maps/vetoes</b> once maps are available.
  The app tries Cito first and then AI web search.
</div>
""", unsafe_allow_html=True)
with m2:
    refresh_maps = st.button("🗺️ Refresh maps/vetoes", use_container_width=True, disabled=not bool(openai_key or match.get("match_id")))

if refresh_maps:
    found = None
    calls = []
    with st.spinner("Trying to refresh maps/vetoes from Cito and AI web search..."):
        if match.get("match_id"):
            found, calls = cito_maps_for_match(match.get("match_id"))
            st.session_state.last_calls += calls
        if found is None and openai_key:
            try:
                found, raw, meta, parsed = ai_find_maps(openai_key, model, match)
                st.session_state.last_calls.append({"ok": bool(found is not None), "status": "AI_MAPS", "url": "OpenAI map/veto search", "payload": {"raw": raw[:1500], "parsed": parsed, "meta": meta}})
            except Exception as e:
                st.session_state.last_calls.append({"ok": False, "status": "AI_MAPS_ERR", "url": "OpenAI map/veto search", "payload": {"error": str(e)}})
    if found is not None:
        st.session_state.maps_df = found
        st.success("Maps/vetoes updated.")
    else:
        st.warning("Maps/vetoes not found yet. Keeping default format.")
    st.rerun()

st.session_state.maps_df = st.data_editor(
    st.session_state.maps_df,
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "Mode": st.column_config.SelectboxColumn("Mode", options=MODES),
        "Picked By": st.column_config.SelectboxColumn("Picked By", options=["", match.get("team_a"), match.get("team_b"), "League/Default"]),
    },
    key="maps_editor_main",
)

st.markdown("## 3) Analyse selected match")

key = analysis_key(match, st.session_state.maps_df, model)
saved = st.session_state.saved.get(key)

if saved:
    st.success(f"✅ Saved analysis found from {saved.get('saved_at')}. You can view this with 0 extra OpenAI/Cito calls.")
else:
    st.warning("No saved analysis for this exact match/maps setup yet. Press Analyse once, then it will save automatically.")

a1, a2 = st.columns([2, 1])
with a1:
    st.markdown("""
<div class="card">
  This runs the full match-day process: Cito roster/stats, Breaking Point fallback, OpenAI web research, map context and BetMGM odds discovery where accessible.
</div>
""", unsafe_allow_html=True)
with a2:
    analyse = st.button("⚡ Analyse this match", use_container_width=True, disabled=not bool(openai_key))

if analyse:
    with st.spinner("Analysing selected match. Pulling stats and running AI web research..."):
        try:
            roster_df, stats_df, stat_calls = build_stats(match.get("team_a"), match.get("team_b"), season)
            st.session_state.last_calls += stat_calls
            parsed, raw, meta = run_ai_analysis(openai_key, model, match, st.session_state.maps_df, roster_df, stats_df)

            st.session_state.saved[key] = {
                "saved_at": now(),
                "match": match,
                "maps": st.session_state.maps_df.fillna("").to_dict(orient="records"),
                "roster": roster_df.fillna("").to_dict(orient="records"),
                "stats": stats_df.fillna("").to_dict(orient="records"),
                "ai_parsed": parsed,
                "ai_raw": raw,
                "ai_meta": meta,
            }
            save_json(CACHE_FILE, st.session_state.saved)
            st.session_state.active_key = key
            st.rerun()
        except Exception as e:
            st.error(str(e))

active = st.session_state.saved.get(key)
if active:
    st.session_state.active_key = key
    render_analysis(active.get("ai_parsed"), active.get("ai_raw", ""))

with st.expander("Stats / raw data"):
    active = st.session_state.saved.get(st.session_state.active_key)
    if active:
        st.markdown("### Roster")
        st.dataframe(pd.DataFrame(active.get("roster", [])), use_container_width=True)
        st.markdown("### Player stats")
        st.dataframe(pd.DataFrame(active.get("stats", [])), use_container_width=True)
        st.markdown("### Raw AI JSON")
        st.json(active.get("ai_parsed"))
    else:
        st.info("No active analysis yet.")

with st.expander("Diagnostics / Cito health"):
    st.markdown("### Cito health check")
    if cito_key:
        if st.button("Run Cito health check"):
            st.dataframe(cito_health_check(season), use_container_width=True)
            st.caption("If these show 200 but 0 rows, the endpoint is reachable but not returning usable data for the selected season/params. If 401/403, the key/auth is wrong. If 404, endpoint path is wrong.")
    else:
        st.warning("No CITO_API_KEY found in Streamlit Secrets.")

    st.markdown("### Recent calls")
    if st.session_state.last_calls:
        st.dataframe(pd.DataFrame([{"OK": c.get("ok"), "Status": c.get("status"), "URL": c.get("url")} for c in st.session_state.last_calls]), use_container_width=True)
    else:
        st.info("No calls recorded this session.")

st.caption("Analysis only. The app does not place bets and cannot guarantee profit. Betting odds may be unavailable or change quickly.")
