import json
import math
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

# ============================================================
# PAGE / THEME
# ============================================================

st.set_page_config(page_title="CDL Analyst v8", layout="wide")

st.markdown(
    """
<style>
    .stApp {
        background: radial-gradient(circle at top left, #111827 0, #070A12 42%, #05070D 100%);
        color: #EEF2FF;
    }
    h1, h2, h3 {
        letter-spacing: .02em;
    }
    .hero-card {
        padding: 22px 24px;
        border: 1px solid rgba(148,163,184,.20);
        border-radius: 22px;
        background: linear-gradient(135deg, rgba(17,24,39,.94), rgba(15,23,42,.72));
        box-shadow: 0 20px 60px rgba(0,0,0,.30);
        margin-bottom: 18px;
    }
    .hero-title {
        font-size: 42px;
        line-height: 1.05;
        font-weight: 900;
        margin: 0 0 8px 0;
    }
    .hero-sub {
        color: #94A3B8;
        font-size: 15px;
        line-height: 1.55;
    }
    .accent {
        color: #FF5B04;
    }
    .card {
        border: 1px solid rgba(148,163,184,.18);
        border-radius: 18px;
        padding: 16px;
        background: rgba(15,23,42,.74);
        margin-bottom: 14px;
    }
    .match-card {
        border: 1px solid rgba(255,91,4,.26);
        border-radius: 20px;
        padding: 18px;
        background: linear-gradient(135deg, rgba(255,91,4,.10), rgba(15,23,42,.82));
        margin-bottom: 14px;
    }
    .pick-card {
        border: 1px solid rgba(34,197,94,.30);
        border-radius: 18px;
        padding: 16px;
        background: linear-gradient(135deg, rgba(34,197,94,.10), rgba(15,23,42,.82));
        margin-bottom: 12px;
    }
    .warn-card {
        border: 1px solid rgba(245,158,11,.34);
        border-radius: 18px;
        padding: 16px;
        background: rgba(245,158,11,.08);
        margin-bottom: 12px;
    }
    .danger-card {
        border: 1px solid rgba(239,68,68,.35);
        border-radius: 18px;
        padding: 16px;
        background: rgba(239,68,68,.08);
        margin-bottom: 12px;
    }
    .pill {
        display: inline-block;
        padding: 4px 9px;
        border-radius: 999px;
        border: 1px solid rgba(148,163,184,.25);
        background: rgba(15,23,42,.9);
        color: #CBD5E1;
        font-size: 12px;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    .good { color: #22C55E; }
    .mid { color: #F59E0B; }
    .bad { color: #EF4444; }
    .muted { color: #94A3B8; }
    div[data-testid="stMetric"] {
        background: rgba(15,23,42,.68);
        border: 1px solid rgba(148,163,184,.16);
        padding: 14px;
        border-radius: 16px;
    }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="hero-card">
  <div class="hero-title">CDL <span class="accent">Analyst v8</span></div>
  <div class="hero-sub">
    Match builder, saved analysis cache, veto/map updater, best 2/3/4 player targets and low Cito usage.
    Selecting matches and editing maps does <b>not</b> spend Cito calls. Only Load / Force Refresh does.
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ============================================================
# CONSTANTS
# ============================================================

CACHE_FILE = Path("saved_analysis_cache.json")

CITO_ROOTS = ["https://api.citoapi.com/api/v1/cod", "https://api.citoapi.com/v1/cod"]
BP_MATCHES_URL = "https://breakingpoint.gg/matches"
BP_TEAMS_URL = "https://breakingpoint.gg/cdl/teams-and-players"

TEAMS = [
    "Boston Breach", "Carolina Royal Ravens", "Cloud9 New York", "FaZe Vegas",
    "G2 Minnesota", "Los Angeles Thieves", "Miami Heretics", "OpTic Texas",
    "Paris Gentle Mates", "Riyadh Falcons", "Toronto KOI", "Vancouver Surge",
]

MODES = ["Hardpoint", "Search & Destroy", "Overload", "Hardpoint", "Search & Destroy"]

SLUGS = {t: re.sub(r"[^a-z0-9-]", "", t.lower().replace("&", "and").replace(" ", "-")) for t in TEAMS}
SLUGS["FaZe Vegas"] = "faze-vegas"
SLUGS["OpTic Texas"] = "optic-texas"
SLUG_TO_TEAM = {v: k for k, v in SLUGS.items()}

# Fallback profile keeps the app useful if Cito does not return player stat rows.
# Scores are priors, not guarantees.
PRIORS = {
    "Simp": [96, 97, 94], "Cellium": [94, 98, 93], "Scrap": [96, 92, 95],
    "HyDra": [96, 93, 95], "aBeZy": [95, 94, 93], "Shotzzy": [95, 93, 94],
    "Dashy": [92, 95, 91], "Kremp": [94, 91, 93], "JoeDeceives": [92, 94, 92],
    "Pred": [93, 91, 92], "Drazah": [91, 92, 90], "Abuzah": [90, 92, 90],
    "CleanX": [91, 89, 90], "Insight": [88, 93, 87], "Envoy": [91, 89, 90],
    "Skyz": [89, 92, 88], "Sib": [91, 88, 91], "Ghosty": [90, 90, 90],
    "KiSMET": [90, 88, 90], "Nero": [90, 87, 89], "Huke": [89, 87, 88],
    "Lurqxx": [89, 86, 88], "Standy": [88, 86, 87], "Lucky": [86, 88, 86],
    "Afro": [88, 85, 87], "Spart": [86, 86, 86], "Mamba": [86, 83, 85],
    "Nastie": [89, 87, 88], "Neptune": [89, 86, 88], "ReeaL": [88, 86, 87],
    "Wevy": [84, 84, 84], "Exceed": [84, 82, 83], "Fire": [83, 83, 83],
    "04": [84, 82, 83], "Abuzah": [90, 92, 90], "Purj": [86, 84, 85],
    "Lunarz": [85, 85, 85], "Atura": [84, 86, 84], "Craze": [85, 83, 84],
    "Hide": [83, 85, 83], "Encourage": [85, 82, 84], "Nejra": [83, 83, 83],
}

STAT_COLS = ["Team", "Player", "Mode", "Score", "KD", "KP10", "KPR", "Source"]
ROSTER_COLS = ["Team", "Player", "Source"]

# ============================================================
# HELPERS
# ============================================================

def safe(x):
    return "" if x is None else str(x).strip()

def slug(x):
    return re.sub(r"[^a-z0-9-]", "", safe(x).lower().replace("&", "and").replace(" ", "-"))

def to_num(x, default=0.0):
    try:
        s = re.sub(r"[^0-9.\-]", "", safe(x))
        return float(s) if s not in ["", ".", "-"] else default
    except Exception:
        return default

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
    return ""

def mode_name(x):
    m = safe(x).lower()
    if "search" in m or "snd" in m or "s&d" in m:
        return "Search & Destroy"
    if "overload" in m or "ovl" in m:
        return "Overload"
    return "Hardpoint"

def get_secret(name):
    try:
        return st.secrets.get(name, "")
    except Exception:
        return ""

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
        for k in ["players", "matches", "items", "results", "data"]:
            if isinstance(d.get(k), list):
                return d[k]
    return []

def empty_roster():
    return pd.DataFrame(columns=ROSTER_COLS)

def empty_stats():
    return pd.DataFrame(columns=STAT_COLS)

def default_maps_df():
    return pd.DataFrame({
        "Map": [1, 2, 3, 4, 5],
        "Mode": MODES,
        "Map Name": ["", "", "", "", ""],
        "Picked By": ["", "", "", "", ""],
    })

def maps_signature(veto_df):
    parts = []
    for _, r in veto_df.iterrows():
        parts.append(f"{safe(r.get('Map'))}:{mode_name(r.get('Mode'))}:{safe(r.get('Map Name'))}:{safe(r.get('Picked By'))}")
    return "|".join(parts)

def analysis_key(season, team_a, team_b, maps_sig=""):
    return f"{season}|{team_a}|{team_b}|{maps_sig}"

def now_label():
    return datetime.now().strftime("%d %b %Y %H:%M")

# ============================================================
# PERSISTENT CACHE
# ============================================================

def load_saved_cache():
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_cache(cache):
    try:
        CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False

def serialise_df(df):
    if df is None or df.empty:
        return []
    return df.fillna("").to_dict(orient="records")

def df_from_records(records, cols):
    if not records:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(records)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols + [c for c in df.columns if c not in cols]]

def store_analysis(key, roster_df, stats_df, calls):
    cache = st.session_state.saved_cache
    cache[key] = {
        "saved_at": now_label(),
        "roster": serialise_df(roster_df),
        "stats": serialise_df(stats_df),
        "calls": calls,
    }
    st.session_state.saved_cache = cache
    save_cache(cache)

def get_analysis(key):
    item = st.session_state.saved_cache.get(key)
    if not item:
        return None
    return {
        "saved_at": item.get("saved_at", ""),
        "roster": df_from_records(item.get("roster", []), ROSTER_COLS),
        "stats": df_from_records(item.get("stats", []), STAT_COLS),
        "calls": item.get("calls", []),
    }

# ============================================================
# CITO + BP
# ============================================================

def cito_headers():
    key = get_secret("CITO_API_KEY")
    h = {"accept": "application/json", "user-agent": "CDL-v8"}
    if key:
        h["Authorization"] = f"Bearer {key}"
        h["x-api-key"] = key
    return h

@st.cache_data(ttl=21600, show_spinner=False)
def cito_get(path, params_tuple=()):
    params = dict(params_tuple)
    attempts = []
    for root in CITO_ROOTS:
        try:
            r = requests.get(root + path, headers=cito_headers(), params=params, timeout=25)
            try:
                payload = r.json()
            except Exception:
                payload = {"raw_text": r.text[:1000]}
            res = {"ok": r.ok, "status": r.status_code, "url": r.url, "payload": payload}
            attempts.append(res)
            if r.ok:
                return res
        except Exception as e:
            attempts.append({"ok": False, "status": "ERR", "url": root + path, "payload": {"error": str(e)}})
    res = attempts[-1] if attempts else {"ok": False, "status": "ERR", "url": path, "payload": {"error": "No attempts"}}
    res["attempts"] = attempts
    return res

@st.cache_data(ttl=21600, show_spinner=True)
def load_cito_matches(season, limit):
    calls = [
        cito_get("/matches/upcoming", tuple({"season": season, "limit": limit}.items())),
        cito_get("/cdl/schedule", tuple({"season": season, "limit": limit}.items())),
    ]
    rows = []
    for call in calls:
        if not call["ok"]:
            continue
        for m in as_list(call["payload"]):
            if not isinstance(m, dict):
                continue
            a = norm_team(nested(m, ["team1.name","teams.team1.name","homeTeam.name","teamA.name","team1.slug","teams.team1.slug","team1"]))
            b = norm_team(nested(m, ["team2.name","teams.team2.name","awayTeam.name","teamB.name","team2.slug","teams.team2.slug","team2"]))
            blob = str(m)
            found = [t for t in TEAMS if t.lower() in blob.lower()]
            if not a and len(found) >= 1:
                a = found[0]
            if not b and len(found) >= 2:
                b = found[1]
            if a and b:
                rows.append({
                    "match_id": safe(nested(m, ["matchId", "id", "bpMatchId"])),
                    "start": safe(nested(m, ["startsAt","startTime","scheduledAt","matchDate","date"])),
                    "event": safe(nested(m, ["event.name","tournament.name","event","round","stage.name"])) or "CDL",
                    "team_a": a, "team_b": b, "source": call["url"],
                })
    return (pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()), calls

@st.cache_data(ttl=21600, show_spinner=False)
def page_text(url):
    r = requests.get(url, headers={"user-agent":"Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script","style","noscript"]):
        tag.decompose()
    return "\n".join(x.strip() for x in soup.get_text("\n").splitlines() if x.strip())

@st.cache_data(ttl=21600, show_spinner=False)
def bp_matches():
    try:
        text = " ".join(page_text(BP_MATCHES_URL).splitlines())
    except Exception:
        return pd.DataFrame()
    alt = "|".join(map(re.escape, TEAMS))
    pat = rf"(~\d+\s+(?:hours?|days?))\s+(CDL\s+(?:Major|Minor|Champs)[^~]*?)\s+({alt}|TBD)\s+0\s+({alt}|TBD)\s+0"
    rows = [{"match_id":"", "start":m.group(1), "event":m.group(2), "team_a":m.group(3), "team_b":m.group(4), "source":"Breaking Point fallback"} for m in re.finditer(pat, text)]
    return pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()

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

@st.cache_data(ttl=21600, show_spinner=True)
def cito_roster(team):
    rows, calls = [], []
    for val in [SLUGS.get(team, slug(team)), team]:
        call = cito_get("/players", tuple({"team": val, "activeOnly":"true", "limit":12}.items()))
        calls.append(call)
        if not call["ok"]:
            continue
        for p in as_list(call["payload"]):
            if not isinstance(p, dict):
                continue
            name = safe(nested(p, ["ign","playerName","gamertag","handle","name"]))
            pteam = norm_team(nested(p, ["currentTeam.name","team.name","teamName","team","currentTeam.slug","team.slug"])) or team
            if name and pteam == team:
                rows.append({"Team":team,"Player":name,"Source":"Cito roster"})
        if rows:
            break
    return (pd.DataFrame(rows, columns=ROSTER_COLS).drop_duplicates() if rows else empty_roster()), calls

@st.cache_data(ttl=21600, show_spinner=True)
def cito_player_stats(player, season):
    calls = []
    for candidate in dict.fromkeys([player, slug(player), player.lower()]):
        if not candidate:
            continue
        call = cito_get(f"/players/{candidate}/stats", tuple({"season":season}.items()))
        calls.append(call)
        if call["ok"]:
            return call["payload"], calls
    return {}, calls

def try_auto_maps(match_id):
    if not match_id:
        return None, []
    calls = []
    for endpoint in [f"/matches/{match_id}/maps", f"/matches/bp-match-{match_id}/maps" if not str(match_id).startswith("bp-match") else ""]:
        if not endpoint:
            continue
        call = cito_get(endpoint, ())
        calls.append(call)
        if not call["ok"]:
            continue
        items = as_list(call["payload"])
        rows = []
        for i, mp in enumerate(items[:5], start=1):
            if not isinstance(mp, dict):
                continue
            mode = mode_name(nested(mp, ["mode", "gameMode", "game.mode"]))
            map_name = safe(nested(mp, ["mapName", "map.name", "name"]))
            pick = norm_team(nested(mp, ["pickedBy.name", "pickedBy", "pickTeam.name", "team.name"]))
            rows.append({"Map": i, "Mode": mode or MODES[i-1], "Map Name": map_name, "Picked By": pick})
        if rows:
            while len(rows) < 5:
                i = len(rows) + 1
                rows.append({"Map": i, "Mode": MODES[i-1], "Map Name": "", "Picked By": ""})
            return pd.DataFrame(rows), calls
    return None, calls

# ============================================================
# MODEL
# ============================================================

def fallback_rows(team, player):
    hp, snd, ovl = PRIORS.get(player, [74,74,74])
    return [
        {"Team":team,"Player":player,"Mode":"Hardpoint","Score":hp,"KD":None,"KP10":None,"KPR":None,"Source":"Fallback profile"},
        {"Team":team,"Player":player,"Mode":"Search & Destroy","Score":snd,"KD":None,"KP10":None,"KPR":None,"Source":"Fallback profile"},
        {"Team":team,"Player":player,"Mode":"Overload","Score":ovl,"KD":None,"KP10":None,"KPR":None,"Source":"Fallback profile"},
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
        "hardpoint":"Hardpoint", "hp":"Hardpoint",
        "searchAndDestroy":"Search & Destroy", "search_and_destroy":"Search & Destroy", "snd":"Search & Destroy",
        "overload":"Overload", "ovl":"Overload", "control":"Overload"
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
        score = 55 + kpr*45 + (kd-1)*18 if mode == "Search & Destroy" else 50 + kp10*1.75 + dmg10/180 + (kd-1)*16
        rows.append({"Team":team,"Player":name,"Mode":mode,"Score":round(score,2),"KD":kd,"KP10":kp10,"KPR":kpr,"Source":"Cito player stats"})
    return rows

def build_analysis(team_a, team_b, season, use_cito, bp_roster_map):
    calls, roster_frames, stat_rows = [], [], []
    for team in [team_a, team_b]:
        roster, rcalls = cito_roster(team) if use_cito else (empty_roster(), [])
        calls += rcalls
        if roster.empty and team in bp_roster_map:
            roster = pd.DataFrame([{"Team":team,"Player":p,"Source":"Breaking Point fallback"} for p in bp_roster_map[team]], columns=ROSTER_COLS)
        roster_frames.append(roster)
        if not roster.empty and {"Team","Player"}.issubset(roster.columns):
            for _, r in roster.iterrows():
                payload, pcalls = cito_player_stats(r["Player"], season) if use_cito else ({}, [])
                calls += pcalls
                parsed = parse_stats(r["Player"], team, payload)
                stat_rows += parsed if parsed else fallback_rows(team, r["Player"])
    roster_df = pd.concat(roster_frames, ignore_index=True).drop_duplicates() if roster_frames else empty_roster()
    stats_df = pd.DataFrame(stat_rows, columns=STAT_COLS).drop_duplicates() if stat_rows else empty_stats()
    return roster_df, stats_df, calls

def team_model(stats):
    if stats.empty or not {"Team","Player","Score","Source"}.issubset(stats.columns):
        return pd.DataFrame()
    x = stats.groupby("Team", as_index=False).agg(
        Players=("Player","nunique"),
        AvgScore=("Score","mean"),
        CitoRows=("Source", lambda s: sum(str(v).startswith("Cito") for v in s))
    )
    x["AvgScore"] = x["AvgScore"].round(2)
    return x.sort_values("AvgScore", ascending=False)

def win_prob(team_a, team_b, stats):
    model = team_model(stats)
    scores = dict(zip(model.Team, model.AvgScore)) if not model.empty else {}
    sa, sb = float(scores.get(team_a,74)), float(scores.get(team_b,74))
    p = 1/(1+math.exp(-(sa-sb)/12))
    return p, sa, sb

def intel_adjustments(notes, player, team, mode):
    t = safe(notes).lower()
    if not t:
        return 0, []
    reasons = []
    score = 0
    entity_hit = player.lower() in t or team.lower() in t or mode.lower() in t
    if not entity_hit:
        return 0, []
    pos = ["hot","frying","on form","good form","dominant","great","strong","improved","mvp","carry"]
    neg = ["sick","ill","benched","sub","struggling","bad form","poor","unwell","visa","dropped","role change"]
    if any(w in t for w in pos):
        score += 2.5
        reasons.append("positive intel")
    if any(w in t for w in neg):
        score -= 3.5
        reasons.append("negative intel")
    return score, reasons

def recommendations(team_a, team_b, stats, veto, notes):
    required = {"Team","Player","Mode","Score","Source"}
    if stats.empty or not required.issubset(stats.columns):
        return pd.DataFrame()
    lookup = {(r.Team, r.Player, r.Mode): r for _, r in stats.iterrows()}
    rows = []
    for _, p in stats[["Team","Player"]].drop_duplicates().iterrows():
        for _, vm in veto.iterrows():
            mode = mode_name(vm["Mode"])
            stat = lookup.get((p.Team, p.Player, mode))
            if stat is None:
                continue
            score = float(stat.Score)
            reasons = [str(stat.Source)]
            if safe(vm["Picked By"]) == p.Team:
                score += 1.25
                reasons.append("team picked map")
            if safe(vm["Map Name"]):
                score += 0.4
                reasons.append("map entered")
            adj, intel_reasons = intel_adjustments(notes, p.Player, p.Team, mode)
            score += adj
            reasons += intel_reasons
            confidence = "High" if str(stat.Source).startswith("Cito") and safe(vm["Map Name"]) else ("Medium" if str(stat.Source).startswith("Cito") else "Fallback")
            rows.append({
                "Team":p.Team, "Player":p.Player, "Map":int(vm["Map"]), "Mode":mode,
                "Map Name":safe(vm["Map Name"]), "Picked By":safe(vm["Picked By"]),
                "Score":round(score,2), "Confidence":confidence, "Source":stat.Source,
                "Reason":"; ".join(reasons)
            })
    return pd.DataFrame(rows).sort_values(["Map","Score"], ascending=[True,False]) if rows else pd.DataFrame()

# ============================================================
# DISPLAY
# ============================================================

def render_pick_cards(overall, title="Best player targets"):
    st.markdown(f"### {title}")
    if overall.empty:
        st.info("No targets found yet.")
        return
    top = overall.head(4).reset_index(drop=True)
    cols = st.columns(min(len(top), 4))
    for i, row in top.iterrows():
        cls = "good" if row.Score >= 90 else ("mid" if row.Score >= 80 else "muted")
        with cols[i]:
            st.markdown(
                f"""
<div class="pick-card">
  <div class="muted">#{i+1} Target</div>
  <h3 style="margin: 4px 0 2px 0;">{row.Player}</h3>
  <div class="pill">{row.Team}</div>
  <div class="pill">{row.Source}</div>
  <div style="font-size: 26px; font-weight: 800;" class="{cls}">{row.Score:.1f}</div>
  <div class="muted">Model score</div>
</div>
""",
                unsafe_allow_html=True,
            )

def render_analysis(team_a, team_b, stats_df, veto_df, notes):
    p, sa, sb = win_prob(team_a, team_b, stats_df)

    c1, c2, c3 = st.columns(3)
    c1.metric(team_a, f"{round(p*100)}%", f"score {round(sa,2)}")
    c2.metric("Model stronger side", team_a if p >= 0.5 else team_b)
    c3.metric(team_b, f"{round((1-p)*100)}%", f"score {round(sb,2)}")

    cito_rows = sum(str(x).startswith("Cito") for x in stats_df.Source) if not stats_df.empty and "Source" in stats_df.columns else 0
    if cito_rows:
        st.success(f"Loaded {cito_rows} Cito player/mode stat rows.")
    else:
        st.warning("No Cito stat rows loaded. The app is using fallback profiles/Breaking Point roster data.")

    recs = recommendations(team_a, team_b, stats_df, veto_df, notes)
    if recs.empty:
        st.info("No recommendation rows. Check Loaded Data and Diagnostics.")
        return recs

    overall = recs.groupby(["Team","Player"], as_index=False).agg(
        Score=("Score","mean"),
        BestMap=("Score","max"),
        Source=("Source", lambda s: ", ".join(sorted(set(map(str,s))))),
        Confidence=("Confidence", lambda s: ", ".join(sorted(set(map(str,s))))),
        Reason=("Reason", lambda s: "; ".join(sorted(set(map(str,s))))[:280])
    ).sort_values("Score", ascending=False)

    render_pick_cards(overall, "Best 2 / 3 / 4 player targets")

    st.markdown("#### Best 2")
    st.write(", ".join([f"**{r.Player}** ({r.Team})" for _, r in overall.head(2).iterrows()]))
    st.markdown("#### Best 3")
    st.write(", ".join([f"**{r.Player}** ({r.Team})" for _, r in overall.head(3).iterrows()]))
    st.markdown("#### Best 4")
    st.write(", ".join([f"**{r.Player}** ({r.Team})" for _, r in overall.head(4).iterrows()]))

    view = st.selectbox("Detailed view", ["Series Overall", "Per Map", "Avoid / Fallback", "Raw Recommendations"])
    if view == "Series Overall":
        st.dataframe(overall, use_container_width=True)
    elif view == "Per Map":
        for map_no in sorted(recs.Map.unique()):
            sub = recs[recs.Map == map_no].sort_values("Score", ascending=False)
            if sub.empty:
                continue
            top = sub.iloc[0]
            st.markdown(
                f"""
<div class="match-card">
  <div class="muted">Map {map_no} · {top.Mode} · {safe(top['Map Name']) or 'map name not entered'}</div>
  <h3 style="margin: 4px 0;">Top target: <span class="accent">{top.Player}</span></h3>
  <span class="pill">{top.Team}</span><span class="pill">{top.Confidence}</span><span class="pill">Score {top.Score}</span>
</div>
""",
                unsafe_allow_html=True,
            )
            st.dataframe(sub, use_container_width=True)
    elif view == "Avoid / Fallback":
        avoid = recs[recs.Source.astype(str).str.contains("Fallback", na=False)].sort_values("Score")
        st.dataframe(avoid, use_container_width=True)
    else:
        st.dataframe(recs, use_container_width=True)

    return recs

# ============================================================
# STATE / SIDEBAR
# ============================================================

if "saved_cache" not in st.session_state:
    st.session_state.saved_cache = load_saved_cache()
if "notes" not in st.session_state:
    st.session_state.notes = ""
if "latest_key" not in st.session_state:
    st.session_state.latest_key = ""

with st.sidebar:
    st.header("Setup")
    has_key = bool(get_secret("CITO_API_KEY"))
    st.write("Cito key:", "✅ found" if has_key else "❌ missing")
    season = st.text_input("Season", value="2026")
    limit = st.slider("Upcoming match limit", 5, 30, 15)
    use_bp = st.checkbox("Use Breaking Point fallback", value=True)
    st.info("Low usage: only Load / Force Refresh spends player-stat Cito calls.")
    st.write(f"Saved analyses: **{len(st.session_state.saved_cache)}**")
    if st.button("Clear Streamlit cache only"):
        st.cache_data.clear()
        st.rerun()
    if st.button("Delete saved analysis cache"):
        st.session_state.saved_cache = {}
        save_cache({})
        st.rerun()

bp_map = bp_rosters() if use_bp else {}
upcoming, match_calls = load_cito_matches(season, limit) if has_key else (pd.DataFrame(), [])
if upcoming.empty and use_bp:
    upcoming = bp_matches()

# ============================================================
# TABS
# ============================================================

tabs = st.tabs(["Dashboard", "Manual Match Builder", "Saved Analyses", "Intel Notes", "Loaded Data", "Diagnostics"])

with tabs[0]:
    st.markdown("## Dashboard")

    if upcoming.empty:
        st.error("No upcoming matches found from Cito or Breaking Point.")
    else:
        mdf = upcoming.reset_index(drop=True)
        labels = [f"{i}: {r.start} — {r.team_a} vs {r.team_b} — {r.event}" for i, r in mdf.iterrows()]
        choice = st.selectbox("Select upcoming match", labels)
        match = mdf.iloc[int(choice.split(":")[0])]

        st.markdown(
            f"""
<div class="match-card">
  <div class="muted">{match.start} · {match.event}</div>
  <h2 style="margin: 6px 0;">{match.team_a} <span class="muted">vs</span> {match.team_b}</h2>
  <span class="pill">Selecting this match uses 0 player-stat calls</span>
  <span class="pill">Source: {match.source}</span>
</div>
""",
            unsafe_allow_html=True,
        )

        veto_key = f"veto_dashboard_{match.team_a}_{match.team_b}_{match.start}"
        if veto_key not in st.session_state:
            st.session_state[veto_key] = default_maps_df()

        c_auto1, c_auto2 = st.columns([1, 2])
        with c_auto1:
            if st.button("Try auto-load maps/vetoes"):
                auto, auto_calls = try_auto_maps(safe(match.get("match_id")))
                if auto is not None:
                    st.session_state[veto_key] = auto
                    st.success("Maps/vetoes found and loaded.")
                else:
                    st.warning("No maps/vetoes found yet. Enter them manually.")
                st.session_state.last_auto_map_calls = auto_calls

        veto_df = st.data_editor(
            st.session_state[veto_key],
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "Mode": st.column_config.SelectboxColumn("Mode", options=MODES),
                "Picked By": st.column_config.SelectboxColumn("Picked By", options=["", match.team_a, match.team_b, "League/Default"]),
            },
            key=f"editor_{veto_key}",
        )
        st.session_state[veto_key] = veto_df

        key = analysis_key(season, match.team_a, match.team_b, maps_signature(veto_df))
        saved = get_analysis(key)

        if saved:
            st.success(f"Saved analysis found — last saved {saved['saved_at']}. Cito calls required: 0.")
            if st.button("Use saved analysis"):
                st.session_state.latest_key = key
                st.rerun()
        else:
            st.warning("No saved analysis for this exact team/map setup.")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Load analysis for this match"):
                with st.spinner("Loading selected-match rosters and player stats..."):
                    roster_df, stats_df, calls = build_analysis(match.team_a, match.team_b, season, has_key, bp_map)
                    store_analysis(key, roster_df, stats_df, calls)
                    st.session_state.latest_key = key
                    st.rerun()
        with c2:
            if st.button("Force refresh analysis"):
                with st.spinner("Force refreshing selected-match analysis..."):
                    roster_df, stats_df, calls = build_analysis(match.team_a, match.team_b, season, has_key, bp_map)
                    store_analysis(key, roster_df, stats_df, calls)
                    st.session_state.latest_key = key
                    st.rerun()

        active = get_analysis(key)
        if active:
            st.session_state.latest_key = key
            render_analysis(match.team_a, match.team_b, active["stats"], veto_df, st.session_state.notes)

with tabs[1]:
    st.markdown("## Manual Match Builder")
    st.markdown('<div class="card">Use this when you already know the teams and map veto/picks. This is the best workflow for match day.</div>', unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        manual_a = st.selectbox("Team A", TEAMS, index=TEAMS.index("OpTic Texas") if "OpTic Texas" in TEAMS else 0)
    with col_b:
        default_b = TEAMS.index("Los Angeles Thieves") if "Los Angeles Thieves" in TEAMS else 1
        manual_b = st.selectbox("Team B", TEAMS, index=default_b)

    if manual_a == manual_b:
        st.error("Choose two different teams.")
    else:
        manual_veto_key = f"manual_veto_{manual_a}_{manual_b}"
        if manual_veto_key not in st.session_state:
            df = default_maps_df()
            df["Picked By"] = ["", "", "", "", ""]
            st.session_state[manual_veto_key] = df

        manual_veto = st.data_editor(
            st.session_state[manual_veto_key],
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "Mode": st.column_config.SelectboxColumn("Mode", options=MODES),
                "Picked By": st.column_config.SelectboxColumn("Picked By", options=["", manual_a, manual_b, "League/Default"]),
            },
            key=f"editor_{manual_veto_key}",
        )
        st.session_state[manual_veto_key] = manual_veto

        mkey = analysis_key(season, manual_a, manual_b, maps_signature(manual_veto))
        saved = get_analysis(mkey)

        if saved:
            st.success(f"Saved analysis exists for this exact setup — saved {saved['saved_at']}.")
        else:
            st.warning("No saved analysis for this exact setup.")

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Load manual match analysis"):
                with st.spinner("Loading manual match analysis..."):
                    roster_df, stats_df, calls = build_analysis(manual_a, manual_b, season, has_key, bp_map)
                    store_analysis(mkey, roster_df, stats_df, calls)
                    st.session_state.latest_key = mkey
                    st.rerun()
        with c2:
            if st.button("Use saved manual analysis", disabled=not bool(saved)):
                st.session_state.latest_key = mkey
                st.rerun()
        with c3:
            if st.button("Force refresh manual analysis"):
                with st.spinner("Force refreshing manual match analysis..."):
                    roster_df, stats_df, calls = build_analysis(manual_a, manual_b, season, has_key, bp_map)
                    store_analysis(mkey, roster_df, stats_df, calls)
                    st.session_state.latest_key = mkey
                    st.rerun()

        active = get_analysis(mkey)
        if active:
            st.session_state.latest_key = mkey
            render_analysis(manual_a, manual_b, active["stats"], manual_veto, st.session_state.notes)

with tabs[2]:
    st.markdown("## Saved Analyses")
    if not st.session_state.saved_cache:
        st.info("No saved analyses yet.")
    else:
        rows = []
        for key, item in st.session_state.saved_cache.items():
            parts = key.split("|")
            rows.append({
                "Key": key,
                "Season": parts[0] if len(parts) > 0 else "",
                "Team A": parts[1] if len(parts) > 1 else "",
                "Team B": parts[2] if len(parts) > 2 else "",
                "Saved": item.get("saved_at", ""),
                "Players": len({r.get("Player") for r in item.get("stats", []) if r.get("Player")}),
                "Cito Rows": sum(1 for r in item.get("stats", []) if str(r.get("Source","")).startswith("Cito")),
            })
        saved_df = pd.DataFrame(rows)
        st.dataframe(saved_df.drop(columns=["Key"]), use_container_width=True)

        selected_saved = st.selectbox("Select saved analysis", list(st.session_state.saved_cache.keys()))
        if st.button("Set as active saved analysis"):
            st.session_state.latest_key = selected_saved
            st.success("Active saved analysis set. Check Loaded Data tab.")

        if st.button("Delete selected saved analysis"):
            cache = st.session_state.saved_cache
            cache.pop(selected_saved, None)
            st.session_state.saved_cache = cache
            save_cache(cache)
            st.rerun()

with tabs[3]:
    st.markdown("## Intel Notes")
    st.markdown(
        """
<div class="card">
Paste useful notes from Twitter/X, Reddit, YouTube transcripts, Breaking Point, CDL broadcast comments or your own reads.
The app applies small adjustments when a team/player/mode is mentioned with positive or negative wording.
</div>
""",
        unsafe_allow_html=True,
    )
    st.session_state.notes = st.text_area(
        "Intel notes",
        value=st.session_state.notes,
        height=260,
        placeholder="Example: Shotzzy frying in HP. Dashy looked ill. LAT likely pick S&D. OpTic weak on Overload.",
    )
    st.markdown("### Adjustment keywords")
    c1, c2 = st.columns(2)
    c1.markdown('<div class="pick-card"><b>Positive</b><br>hot, frying, on form, good form, dominant, great, strong, improved, MVP, carry</div>', unsafe_allow_html=True)
    c2.markdown('<div class="danger-card"><b>Negative</b><br>sick, ill, benched, sub, struggling, bad form, poor, unwell, visa, dropped, role change</div>', unsafe_allow_html=True)

with tabs[4]:
    st.markdown("## Loaded Data")
    key = st.session_state.latest_key
    active = get_analysis(key) if key else None
    if not active:
        st.info("No active analysis loaded yet.")
    else:
        st.success(f"Active analysis saved at {active['saved_at']}")
        st.markdown("### Rosters")
        st.dataframe(active["roster"], use_container_width=True)
        st.markdown("### Player Stats")
        st.dataframe(active["stats"], use_container_width=True)
        st.markdown("### Cito / API Calls Used For This Saved Analysis")
        st.dataframe(pd.DataFrame([{"Status":c.get("status"), "OK":c.get("ok"), "URL":c.get("url")} for c in active["calls"]]), use_container_width=True)

with tabs[5]:
    st.markdown("## Diagnostics")
    st.markdown("### Match list calls")
    st.dataframe(pd.DataFrame([{"Status":c.get("status"),"OK":c.get("ok"),"URL":c.get("url")} for c in match_calls]), use_container_width=True)

    auto_calls = st.session_state.get("last_auto_map_calls", [])
    if auto_calls:
        st.markdown("### Auto-map/veto calls")
        st.dataframe(pd.DataFrame([{"Status":c.get("status"),"OK":c.get("ok"),"URL":c.get("url")} for c in auto_calls]), use_container_width=True)

    st.markdown("### Manual Cito endpoint tester")
    endpoint = st.text_input("Endpoint", value="/matches/upcoming")
    if st.button("Test endpoint"):
        res = cito_get(endpoint, tuple({"season":season,"limit":5}.items()) if "upcoming" in endpoint else ())
        st.write(f"Status: {res['status']} | OK: {res['ok']} | URL: {res['url']}")
        st.json(res["payload"])

st.caption("Analysis only. This app does not place bets and does not guarantee profit.")
