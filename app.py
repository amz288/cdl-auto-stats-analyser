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

st.set_page_config(page_title="CDL Hybrid Betting Analyst v11", layout="wide")

st.markdown("""
<style>
.stApp {
    background: radial-gradient(circle at top left, #121827 0, #080B12 42%, #03050A 100%);
    color: #F8FAFC;
}
h1,h2,h3 { letter-spacing:-.02em; }
.hero {
    padding: 28px;
    border-radius: 28px;
    border: 1px solid rgba(255,91,4,.34);
    background: linear-gradient(135deg, rgba(255,91,4,.16), rgba(15,23,42,.9));
    box-shadow: 0 24px 80px rgba(0,0,0,.40);
    margin-bottom: 18px;
}
.hero-title { font-size:46px; font-weight:950; line-height:1; margin-bottom:10px; }
.hero-sub { color:#CBD5E1; font-size:16px; line-height:1.55; }
.accent { color:#FF5B04; }
.card {
    border: 1px solid rgba(148,163,184,.18);
    border-radius: 20px;
    padding: 18px;
    background: rgba(15,23,42,.74);
    margin-bottom: 14px;
}
.match-card {
    border: 1px solid rgba(255,91,4,.26);
    border-radius: 22px;
    padding: 18px;
    background: linear-gradient(135deg, rgba(255,91,4,.12), rgba(15,23,42,.78));
    margin-bottom: 14px;
}
.bet-card {
    border: 1px solid rgba(34,197,94,.32);
    border-radius: 20px;
    padding: 16px;
    background: linear-gradient(135deg, rgba(34,197,94,.12), rgba(15,23,42,.82));
    min-height: 190px;
}
.warn-card {
    border: 1px solid rgba(245,158,11,.35);
    border-radius: 20px;
    padding: 16px;
    background: linear-gradient(135deg, rgba(245,158,11,.10), rgba(15,23,42,.82));
}
.risk-card {
    border: 1px solid rgba(239,68,68,.32);
    border-radius: 20px;
    padding: 16px;
    background: linear-gradient(135deg, rgba(239,68,68,.10), rgba(15,23,42,.82));
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
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="hero-title">CDL <span class="accent">Hybrid Betting Analyst v11</span></div>
  <div class="hero-sub">
    Cito stats + Breaking Point context + OpenAI web research + BetMGM odds discovery.
    Built for player kills per map and team map-winner markets. Nothing refreshes unless you press the refresh button.
  </div>
</div>
""", unsafe_allow_html=True)

CACHE_FILE = Path("v11_saved_bundles.json")
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
    "04": [84, 82, 83], "Purj": [86, 84, 85],
}

ROSTER_COLS = ["Team", "Player", "Source"]
STAT_COLS = ["Team", "Player", "Mode", "Score", "KD", "KP10", "KPR", "ProjectedKills", "Source"]

def safe(x):
    return "" if x is None else str(x).strip()

def now():
    return datetime.now().strftime("%d %b %Y %H:%M")

def slug(x):
    return re.sub(r"[^a-z0-9-]", "", safe(x).lower().replace("&", "and").replace(" ", "-"))

def norm_team(x):
    s = safe(x)
    if not s: return ""
    sl = slug(s)
    if sl in SLUG_TO_TEAM: return SLUG_TO_TEAM[sl]
    for t in TEAMS:
        if s.lower() == t.lower() or t.lower() in s.lower() or s.lower() in t.lower():
            return t
    return ""

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

def load_cache():
    if not CACHE_FILE.exists(): return {}
    try: return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception: return {}

def save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")

def short_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:18]

def empty_roster():
    return pd.DataFrame(columns=ROSTER_COLS)

def empty_stats():
    return pd.DataFrame(columns=STAT_COLS)

def default_maps():
    return pd.DataFrame({"Map":[1,2,3,4,5], "Mode":MODES, "Map Name":["","","","",""], "Picked By":["","","","",""]})

def maps_to_text(df):
    lines=[]
    for _,r in df.iterrows():
        lines.append(f"Map {int(r['Map'])}: {safe(r['Mode'])} | map: {safe(r['Map Name']) or 'unknown'} | picked by: {safe(r['Picked By']) or 'unknown'}")
    return "\n".join(lines)

def bundle_key(match, maps_df, model):
    raw = f"{match.get('team_a')}|{match.get('team_b')}|{match.get('start_time')}|{maps_to_text(maps_df)}|{model}"
    return short_hash(raw)

def nested(d, paths):
    for path in paths:
        cur, ok = d, True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and safe(cur): return cur
    return ""

def as_list(payload):
    d = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(d, list): return d
    if isinstance(d, dict):
        for k in ["players","matches","items","results","data"]:
            if isinstance(d.get(k), list): return d[k]
    return []

def extract_json(text):
    if not text: return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try: return json.loads(cleaned)
    except Exception: pass
    m = re.search(r"\{[\s\S]*\}", cleaned)
    if m:
        try: return json.loads(m.group(0))
        except Exception: pass
    return None

def implied_prob(decimal_odds):
    o = to_num(decimal_odds, 0)
    return 1/o if o > 1 else None

def ev_percent(prob, odds):
    p = to_num(prob, 0)
    if p > 1: p = p/100
    o = to_num(odds, 0)
    if not p or o <= 1: return None
    return (p * o - 1) * 100

def conf_class(conf):
    c=safe(conf).lower()
    if "high" in c: return "good"
    if "low" in c: return "bad"
    return "mid"

# -----------------------------
# CITO / BREAKING POINT
# -----------------------------

def cito_headers():
    key = get_secret("CITO_API_KEY")
    h = {"accept":"application/json", "user-agent":"CDL-v11"}
    if key:
        h["Authorization"] = f"Bearer {key}"
        h["x-api-key"] = key
    return h

@st.cache_data(ttl=21600, show_spinner=False)
def cito_get(path, params_tuple=()):
    params = dict(params_tuple)
    attempts=[]
    for root in CITO_ROOTS:
        try:
            r = requests.get(root+path, headers=cito_headers(), params=params, timeout=25)
            try: payload = r.json()
            except Exception: payload = {"raw_text": r.text[:1000]}
            res = {"ok":r.ok, "status":r.status_code, "url":r.url, "payload":payload}
            attempts.append(res)
            if r.ok: return res
        except Exception as e:
            attempts.append({"ok":False, "status":"ERR", "url":root+path, "payload":{"error":str(e)}})
    res = attempts[-1] if attempts else {"ok":False,"status":"ERR","url":path,"payload":{"error":"No attempts"}}
    res["attempts"] = attempts
    return res

@st.cache_data(ttl=21600, show_spinner=False)
def page_text(url):
    r = requests.get(url, headers={"user-agent":"Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script","style","noscript"]): tag.decompose()
    return "\n".join(x.strip() for x in soup.get_text("\n").splitlines() if x.strip())

@st.cache_data(ttl=21600, show_spinner=True)
def cito_matches(season="2026", limit=30):
    calls=[
        cito_get("/matches/upcoming", tuple({"season":season,"limit":limit}.items())),
        cito_get("/cdl/schedule", tuple({"season":season,"limit":limit}.items())),
    ]
    rows=[]
    for call in calls:
        if not call["ok"]: continue
        for m in as_list(call["payload"]):
            if not isinstance(m, dict): continue
            a = norm_team(nested(m, ["team1.name","teams.team1.name","homeTeam.name","teamA.name","team1.slug","teams.team1.slug","team1"]))
            b = norm_team(nested(m, ["team2.name","teams.team2.name","awayTeam.name","teamB.name","team2.slug","teams.team2.slug","team2"]))
            blob = str(m)
            found=[t for t in TEAMS if t.lower() in blob.lower()]
            if not a and len(found)>=1: a=found[0]
            if not b and len(found)>=2: b=found[1]
            if a and b:
                rows.append({
                    "start_time": safe(nested(m, ["startsAt","startTime","scheduledAt","matchDate","date"])),
                    "event": safe(nested(m, ["event.name","tournament.name","event","round","stage.name"])) or "CDL",
                    "team_a": a,
                    "team_b": b,
                    "status": "upcoming",
                    "source": "Cito",
                    "match_id": safe(nested(m, ["id","matchId","bpMatchId"])),
                })
    return rows, calls

@st.cache_data(ttl=21600, show_spinner=True)
def bp_matches():
    try: text = " ".join(page_text(BP_MATCHES_URL).splitlines())
    except Exception as e: return [], [{"ok":False,"status":"ERR","url":BP_MATCHES_URL,"payload":{"error":str(e)}}]
    alt = "|".join(map(re.escape, TEAMS))
    pats = [
        rf"(~\d+\s+(?:hours?|days?))\s+(CDL\s+(?:Major|Minor|Champs)[^~]*?)\s+({alt}|TBD)\s+0\s+({alt}|TBD)\s+0",
        rf"({alt})\s+(?:vs|v|VS)\s+({alt})",
    ]
    rows=[]
    for pat in pats:
        for m in re.finditer(pat, text):
            if len(m.groups()) >= 4:
                start,event,a,b=m.group(1),m.group(2),m.group(3),m.group(4)
            else:
                start,event,a,b="", "CDL", m.group(1), m.group(2)
            if a != "TBD" and b != "TBD" and a != b:
                row={"start_time":start,"event":event,"team_a":a,"team_b":b,"status":"upcoming","source":"Breaking Point","match_id":""}
                if row not in rows: rows.append(row)
    return rows, [{"ok":True,"status":200,"url":BP_MATCHES_URL,"payload":{"matches":len(rows)}}]

@st.cache_data(ttl=21600, show_spinner=False)
def bp_rosters():
    try: lines = page_text(BP_TEAMS_URL).splitlines()
    except Exception: return {}
    out={t:[] for t in TEAMS}
    active, team, collecting=False,"",False
    for line in lines:
        if line == "# CDL Teams": active=True; continue
        if line == "# Players": break
        if not active: continue
        if line in TEAMS:
            team=line; collecting=False; continue
        if team and line == "Players":
            collecting=True; continue
        if team and collecting and 1 < len(line) < 26 and line.lower() not in ["players","coach","team stats","matches","news"]:
            if line not in out[team]: out[team].append(line)
    return {k:v for k,v in out.items() if v}

@st.cache_data(ttl=21600, show_spinner=True)
def cito_roster(team):
    rows,calls=[],[]
    for val in [TEAM_SLUGS.get(team, slug(team)), team]:
        call = cito_get("/players", tuple({"team":val, "activeOnly":"true", "limit":12}.items()))
        calls.append(call)
        if not call["ok"]: continue
        for p in as_list(call["payload"]):
            if not isinstance(p, dict): continue
            name=safe(nested(p, ["ign","playerName","gamertag","handle","name"]))
            pteam=norm_team(nested(p, ["currentTeam.name","team.name","teamName","team","currentTeam.slug","team.slug"])) or team
            if name and pteam == team:
                rows.append({"Team":team,"Player":name,"Source":"Cito roster"})
        if rows: break
    return (pd.DataFrame(rows, columns=ROSTER_COLS).drop_duplicates() if rows else empty_roster()), calls

@st.cache_data(ttl=21600, show_spinner=True)
def cito_player_stats(player, season):
    calls=[]
    for candidate in dict.fromkeys([player, slug(player), player.lower()]):
        if not candidate: continue
        call = cito_get(f"/players/{candidate}/stats", tuple({"season":season}.items()))
        calls.append(call)
        if call["ok"]: return call["payload"], calls
    return {}, calls

def fallback_rows(team, player):
    hp,snd,ovl = PRIORS.get(player, [74,74,74])
    return [
        {"Team":team,"Player":player,"Mode":"Hardpoint","Score":hp,"KD":None,"KP10":None,"KPR":None,"ProjectedKills":round(18+(hp-70)*0.18,1),"Source":"Fallback profile"},
        {"Team":team,"Player":player,"Mode":"Search & Destroy","Score":snd,"KD":None,"KP10":None,"KPR":None,"ProjectedKills":round(5+(snd-70)*0.06,1),"Source":"Fallback profile"},
        {"Team":team,"Player":player,"Mode":"Overload","Score":ovl,"KD":None,"KP10":None,"KPR":None,"ProjectedKills":round(18+(ovl-70)*0.16,1),"Source":"Fallback profile"},
    ]

def parse_stats(player, team, payload):
    d = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(d, dict): return []
    info = d.get("player", {}) if isinstance(d.get("player"), dict) else {}
    name = safe(info.get("ign") or info.get("name") or player)
    by = d.get("byMode", {}) if isinstance(d.get("byMode"), dict) else {}
    overall = d.get("overall", {}) if isinstance(d.get("overall"), dict) else {}
    modes = {"hardpoint":"Hardpoint","hp":"Hardpoint","searchAndDestroy":"Search & Destroy","search_and_destroy":"Search & Destroy","snd":"Search & Destroy","overload":"Overload","ovl":"Overload","control":"Overload"}
    rows=[]
    for key,mode in modes.items():
        m = by.get(key)
        if not isinstance(m, dict): continue
        kd = to_num(m.get("kd"), to_num(overall.get("kd"), 1))
        kp10 = to_num(m.get("killsPer10"), 0)
        dmg10 = to_num(m.get("damagePer10"), 0)
        kpr = to_num(m.get("killsPerRound"), 0)
        if mode == "Search & Destroy":
            score = 55 + kpr*45 + (kd-1)*18
            proj = max(3, round(kpr*11 if kpr else 5+(score-70)*0.06, 1))
        else:
            score = 50 + kp10*1.75 + dmg10/180 + (kd-1)*16
            proj = max(10, round(kp10*2.5 if kp10 else 18+(score-70)*0.18, 1))
        rows.append({"Team":team,"Player":name,"Mode":mode,"Score":round(score,2),"KD":kd,"KP10":kp10,"KPR":kpr,"ProjectedKills":proj,"Source":"Cito player stats"})
    return rows

def build_stats_bundle(team_a, team_b, season):
    calls=[]
    bp_map=bp_rosters()
    roster_frames=[]
    stat_rows=[]
    for team in [team_a, team_b]:
        roster, rcalls = cito_roster(team)
        calls += rcalls
        if roster.empty and team in bp_map:
            roster=pd.DataFrame([{"Team":team,"Player":p,"Source":"Breaking Point roster"} for p in bp_map[team]], columns=ROSTER_COLS)
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

# -----------------------------
# OPENAI RESEARCH
# -----------------------------

def openai_client(api_key):
    if OpenAI is None: raise RuntimeError("openai package not installed. requirements.txt must include openai.")
    return OpenAI(api_key=api_key)

def openai_call(api_key, model, prompt, require_search=True):
    c = openai_client(api_key)
    attempts=[
        {"tools":[{"type":"web_search"}], "tool_choice":"required" if require_search else "auto"},
        {"tools":[{"type":"web_search_preview"}], "tool_choice":"required" if require_search else "auto"},
        {"tools":[], "tool_choice":"none"},
    ]
    last=None
    for a in attempts:
        try:
            kwargs={"model":model, "input":prompt}
            if a["tools"]:
                kwargs["tools"]=a["tools"]
                kwargs["tool_choice"]=a["tool_choice"]
            resp=c.responses.create(**kwargs)
            return resp.output_text, {"model":model, "attempt":a}
        except Exception as e:
            last=str(e)
    raise RuntimeError(last or "OpenAI call failed")

def discover_matches_ai(api_key, model):
    prompt = """
Find the latest upcoming/current Call of Duty League (CDL) matches using web search.
Prioritise Breaking Point, official CDL schedule, and event schedule pages.

Return ONLY valid JSON:
{
  "notes": "short notes/confidence",
  "matches": [
    {"start_time":"", "event":"", "team_a":"", "team_b":"", "status":"upcoming/live/unknown", "source":""}
  ]
}
Only real CDL teams. Do not invent matches.
"""
    raw, meta = openai_call(api_key, model, prompt, True)
    parsed = extract_json(raw) or {"notes":"AI output not valid JSON","matches":[]}
    rows=[]
    for m in parsed.get("matches", []) if isinstance(parsed, dict) else []:
        if not isinstance(m, dict): continue
        a,b=safe(m.get("team_a")), safe(m.get("team_b"))
        if a and b and a.lower()!=b.lower():
            rows.append({"start_time":safe(m.get("start_time")),"event":safe(m.get("event")),"team_a":a,"team_b":b,"status":safe(m.get("status")) or "unknown","source":safe(m.get("source")) or "AI web search","match_id":""})
    return rows, raw, meta, safe(parsed.get("notes"))

def build_ai_prompt(match, maps_df, roster_df, stats_df):
    stats_summary = stats_df.to_csv(index=False)[:16000] if not stats_df.empty else "No Cito stats loaded."
    roster_summary = roster_df.to_csv(index=False)[:8000] if not roster_df.empty else "No roster loaded."
    return f"""
You are a Call of Duty League betting analyst. Analyse this match using the structured stats below plus web search.

MATCH:
{match.get("team_a")} vs {match.get("team_b")}
Start/event/status/source:
{match.get("start_time")} | {match.get("event")} | {match.get("status")} | {match.get("source")}

MAP FORMAT:
Best of 5
Map 1 Hardpoint
Map 2 Search & Destroy
Map 3 Overload
Map 4 Hardpoint
Map 5 Search & Destroy

MAPS/VETOES IF KNOWN:
{maps_to_text(maps_df)}

STRUCTURED ROSTER DATA:
{roster_summary}

STRUCTURED PLAYER/MODE STATS:
{stats_summary}

Tasks:
1. Research current CDL context using web search: Breaking Point, official CDL, recent results, roster/sub news, map tendencies, team form.
2. Try to find current BetMGM decimal odds for:
   - player kills per map
   - team to win each map
   If BetMGM odds are not accessible, clearly state "BetMGM odds not found".
3. Use Cito stats as the hard stats layer. Use web research as context, not as a replacement.
4. Return practical best-value recommendations and avoid/risk items.
5. Do not invent odds. If odds are missing, still give projected targets but mark odds_found=false.

Return ONLY valid JSON in this exact schema:
{{
  "match_title": "{match.get("team_a")} vs {match.get("team_b")}",
  "summary": "",
  "model_pick": "",
  "team_a_win_probability": 0.0,
  "team_b_win_probability": 0.0,
  "confidence": "High/Medium/Low",
  "data_quality": {{
    "cito_stats": "Good/Partial/Missing",
    "breakingpoint_context": "Good/Partial/Missing",
    "betmgm_odds": "Found/Partial/Not found",
    "notes": ""
  }},
  "key_context": ["", "", ""],
  "map_winner_leans": [
    {{"map":1, "mode":"Hardpoint", "map_name":"", "lean_team":"", "probability":0.0, "betmgm_decimal_odds":null, "edge_percent":null, "confidence":"High/Medium/Low", "reason":""}}
  ],
  "player_kill_props": [
    {{"player":"", "team":"", "map":1, "mode":"Hardpoint", "line":null, "over_decimal_odds":null, "under_decimal_odds":null, "projected_kills":0.0, "over_probability":0.0, "edge_percent":null, "recommendation":"Over/Under/No Bet/Target if line appears", "confidence":"High/Medium/Low", "reason":"", "odds_found":false}}
  ],
  "best_bets": [
    {{"rank":1, "market":"Player kills per map/Map winner", "selection":"", "line":null, "odds":null, "edge_percent":null, "confidence":"High/Medium/Low", "reason":""}}
  ],
  "best_targets_without_odds": [
    {{"player":"", "team":"", "map":1, "mode":"", "projected_kills":0.0, "target_note":"", "confidence":"High/Medium/Low"}}
  ],
  "avoid_or_risk": [
    {{"selection":"", "reason":"", "risk":"High/Medium/Low"}}
  ],
  "sources_used": [""],
  "final_note": "Analysis only. Odds may move."
}}
"""

def run_ai_research(api_key, model, match, maps_df, roster_df, stats_df):
    raw, meta = openai_call(api_key, model, build_ai_prompt(match, maps_df, roster_df, stats_df), True)
    parsed = extract_json(raw)
    return parsed, raw, meta

# -----------------------------
# DISPLAY
# -----------------------------

def render_bet_card(item, i):
    conf = conf_class(item.get("confidence"))
    ev = item.get("edge_percent")
    try: ev_txt = f"{float(ev):.1f}%" if ev is not None else "N/A"
    except Exception: ev_txt = "N/A"
    st.markdown(f"""
<div class="bet-card">
  <div class="muted">#{i} Best Bet</div>
  <h3 style="margin:6px 0;">{safe(item.get("selection")) or "Unknown"}</h3>
  <span class="pill">{safe(item.get("market"))}</span>
  <span class="pill {conf}">{safe(item.get("confidence")) or "Medium"}</span>
  <span class="pill">Edge: {ev_txt}</span>
  <p style="color:#CBD5E1;margin-top:10px;">{safe(item.get("reason"))}</p>
</div>
""", unsafe_allow_html=True)

def render_analysis(parsed, raw=""):
    if not parsed:
        st.error("AI returned output but it was not valid JSON.")
        st.code(raw[:7000])
        return
    dq = parsed.get("data_quality", {}) if isinstance(parsed.get("data_quality"), dict) else {}
    st.markdown(f"""
<div class="match-card">
  <div class="muted">Hybrid Match Centre</div>
  <h2 style="margin:6px 0;">{safe(parsed.get("match_title"))}</h2>
  <span class="pill">Model pick: {safe(parsed.get("model_pick"))}</span>
  <span class="pill {conf_class(parsed.get("confidence"))}">Confidence: {safe(parsed.get("confidence"))}</span>
  <span class="pill">Cito: {safe(dq.get("cito_stats"))}</span>
  <span class="pill">BetMGM: {safe(dq.get("betmgm_odds"))}</span>
  <p style="color:#CBD5E1;margin-top:12px;">{safe(parsed.get("summary"))}</p>
</div>
""", unsafe_allow_html=True)
    c1,c2,c3=st.columns(3)
    try: ta=round(float(parsed.get("team_a_win_probability",0))*100)
    except Exception: ta=0
    try: tb=round(float(parsed.get("team_b_win_probability",0))*100)
    except Exception: tb=0
    c1.metric("Team A win probability", f"{ta}%")
    c2.metric("Model pick", safe(parsed.get("model_pick")) or "Unknown")
    c3.metric("Team B win probability", f"{tb}%")

    if parsed.get("key_context"):
        st.markdown("### Key context")
        for x in parsed.get("key_context", [])[:8]:
            st.markdown(f"- {safe(x)}")

    best = parsed.get("best_bets", [])
    st.markdown("### Best Bets")
    if best:
        cols = st.columns(min(3, len(best)))
        for idx, item in enumerate(best[:3], start=1):
            with cols[idx-1]:
                render_bet_card(item, idx)
        if len(best) > 3:
            st.dataframe(pd.DataFrame(best), use_container_width=True)
    else:
        st.info("No best bets returned. Usually this means odds were not found or confidence was too low.")

    st.markdown("### Player kills per map")
    props = parsed.get("player_kill_props", [])
    if props:
        st.dataframe(pd.DataFrame(props), use_container_width=True)
    else:
        st.info("No player-kill props returned.")

    st.markdown("### Best targets if BetMGM odds are not found")
    targets = parsed.get("best_targets_without_odds", [])
    if targets:
        st.dataframe(pd.DataFrame(targets), use_container_width=True)
    else:
        st.info("No target-only recommendations returned.")

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
            st.markdown(f"- {safe(s)}")

    if parsed.get("final_note"):
        st.caption(safe(parsed.get("final_note")))

def merge_matches(*lists):
    out=[]
    seen=set()
    for lst in lists:
        for m in lst:
            key=(safe(m.get("team_a")).lower(), safe(m.get("team_b")).lower(), safe(m.get("start_time")).lower())
            rev=(key[1], key[0], key[2])
            if key in seen or rev in seen: continue
            if safe(m.get("team_a")) and safe(m.get("team_b")):
                out.append(m); seen.add(key)
    return out

# -----------------------------
# STATE
# -----------------------------

if "cache" not in st.session_state:
    st.session_state.cache = load_cache()
if "matches" not in st.session_state:
    st.session_state.matches = []
if "match_calls" not in st.session_state:
    st.session_state.match_calls = []
if "selected_match_idx" not in st.session_state:
    st.session_state.selected_match_idx = 0
if "maps_df" not in st.session_state:
    st.session_state.maps_df = default_maps()
if "active_key" not in st.session_state:
    st.session_state.active_key = ""

with st.sidebar:
    st.header("Setup")
    openai_key = get_secret("OPENAI_API_KEY")
    cito_key = get_secret("CITO_API_KEY")
    st.write("OpenAI:", "✅ found" if openai_key else "❌ missing")
    st.write("Cito:", "✅ found" if cito_key else "❌ missing")
    season = st.text_input("Season", value="2026")
    model = st.text_input("OpenAI model", value="gpt-4.1-mini")
    st.write(f"Saved bundles: **{len(st.session_state.cache)}**")
    st.info("Auto-refresh only happens when you press a refresh button.")
    if st.button("Clear saved bundles"):
        st.session_state.cache={}
        save_cache({})
        st.rerun()
    if st.button("Clear Streamlit cache"):
        st.cache_data.clear()
        st.rerun()

tabs = st.tabs(["Live Matches", "Full Refresh", "Best Bets", "Stats", "Saved", "Diagnostics"])

with tabs[0]:
    st.markdown("## Live Matches")
    st.markdown('<div class="card">Fetch matches from Cito, Breaking Point and AI web search. This does not pull full player stats until the Full Refresh tab.</div>', unsafe_allow_html=True)
    c1,c2,c3=st.columns(3)
    with c1:
        if st.button("Refresh Cito Matches"):
            rows,calls=cito_matches(season,30)
            st.session_state.matches = merge_matches(st.session_state.matches, rows)
            st.session_state.match_calls += calls
            st.rerun()
    with c2:
        if st.button("Refresh Breaking Point Matches"):
            rows,calls=bp_matches()
            st.session_state.matches = merge_matches(st.session_state.matches, rows)
            st.session_state.match_calls += calls
            st.rerun()
    with c3:
        if st.button("Refresh AI Web Matches", disabled=not bool(openai_key)):
            with st.spinner("AI web-searching latest CDL matches..."):
                try:
                    rows, raw, meta, notes = discover_matches_ai(openai_key, model)
                    st.session_state.matches = merge_matches(st.session_state.matches, rows)
                    st.session_state.match_calls.append({"ok":True,"status":"AI","url":"OpenAI web match discovery","payload":{"notes":notes,"meta":meta,"raw":raw[:1200]}})
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    if not st.session_state.matches:
        st.warning("No matches loaded yet. Press the refresh buttons above. If one source fails, try the others.")
    else:
        df=pd.DataFrame(st.session_state.matches)
        st.dataframe(df, use_container_width=True)
        labels=[f"{i}: {m.get('start_time','')} — {m.get('team_a')} vs {m.get('team_b')} — {m.get('event','')} [{m.get('source')}]" for i,m in enumerate(st.session_state.matches)]
        choice=st.selectbox("Select match", labels, index=min(st.session_state.selected_match_idx, len(labels)-1))
        st.session_state.selected_match_idx = int(choice.split(":")[0])
        m=st.session_state.matches[st.session_state.selected_match_idx]
        st.markdown(f"""
<div class="match-card">
  <div class="muted">{safe(m.get("start_time"))} · {safe(m.get("event"))} · {safe(m.get("source"))}</div>
  <h2 style="margin:6px 0;">{safe(m.get("team_a"))} <span class="muted">vs</span> {safe(m.get("team_b"))}</h2>
  <span class="pill">Status: {safe(m.get("status"))}</span>
</div>
""", unsafe_allow_html=True)

with tabs[1]:
    st.markdown("## Full Refresh")
    if not st.session_state.matches:
        st.warning("Load/select a match first in Live Matches.")
    else:
        match=st.session_state.matches[st.session_state.selected_match_idx]
        st.markdown(f"### {match.get('team_a')} vs {match.get('team_b')}")
        st.markdown("#### Map format")
        maps_df = st.data_editor(
            st.session_state.maps_df,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "Mode": st.column_config.SelectboxColumn("Mode", options=MODES),
                "Picked By": st.column_config.SelectboxColumn("Picked By", options=["", match.get("team_a"), match.get("team_b"), "League/Default"]),
            },
            key="maps_editor",
        )
        st.session_state.maps_df = maps_df

        key=bundle_key(match, maps_df, model)
        saved=st.session_state.cache.get(key)
        if saved:
            st.success(f"Saved bundle found from {saved.get('saved_at')}. Viewing it uses 0 extra API calls.")
        else:
            st.warning("No saved full analysis for this exact match/maps setup.")

        if st.button("FULL REFRESH: Cito stats + Breaking Point + AI research + BetMGM odds", disabled=not bool(openai_key)):
            with st.spinner("Building full hybrid bundle. This may use Cito and OpenAI calls..."):
                try:
                    roster_df, stats_df, cito_calls = build_stats_bundle(match.get("team_a"), match.get("team_b"), season)
                    parsed, raw, meta = run_ai_research(openai_key, model, match, maps_df, roster_df, stats_df)
                    st.session_state.cache[key] = {
                        "saved_at": now(),
                        "match": match,
                        "maps": maps_df.fillna("").to_dict(orient="records"),
                        "roster": roster_df.fillna("").to_dict(orient="records"),
                        "stats": stats_df.fillna("").to_dict(orient="records"),
                        "cito_calls": cito_calls,
                        "ai_raw": raw,
                        "ai_parsed": parsed,
                        "ai_meta": meta,
                    }
                    save_cache(st.session_state.cache)
                    st.session_state.active_key = key
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        if saved:
            if st.button("Use saved bundle"):
                st.session_state.active_key=key
                st.rerun()

        active=st.session_state.cache.get(key)
        if active:
            st.session_state.active_key=key
            render_analysis(active.get("ai_parsed"), active.get("ai_raw",""))

with tabs[2]:
    st.markdown("## Best Bets")
    active=st.session_state.cache.get(st.session_state.active_key)
    if not active:
        st.info("No active bundle yet. Run or use saved analysis in Full Refresh.")
    else:
        render_analysis(active.get("ai_parsed"), active.get("ai_raw",""))

with tabs[3]:
    st.markdown("## Stats")
    active=st.session_state.cache.get(st.session_state.active_key)
    if not active:
        st.info("No active bundle yet.")
    else:
        st.markdown("### Roster")
        st.dataframe(pd.DataFrame(active.get("roster", [])), use_container_width=True)
        st.markdown("### Cito / fallback player stats")
        st.dataframe(pd.DataFrame(active.get("stats", [])), use_container_width=True)

with tabs[4]:
    st.markdown("## Saved")
    if not st.session_state.cache:
        st.info("No saved bundles yet.")
    else:
        rows=[]
        for k,v in st.session_state.cache.items():
            m=v.get("match",{})
            parsed=v.get("ai_parsed") or {}
            dq=parsed.get("data_quality",{}) if isinstance(parsed,dict) else {}
            rows.append({"Key":k,"Saved":v.get("saved_at"),"Match":f"{m.get('team_a')} vs {m.get('team_b')}","BetMGM":dq.get("betmgm_odds",""),"Cito rows":len(v.get("stats",[]))})
        df=pd.DataFrame(rows)
        st.dataframe(df.drop(columns=["Key"]), use_container_width=True)
        sel=st.selectbox("Select saved bundle", [r["Key"] for r in rows])
        c1,c2=st.columns(2)
        with c1:
            if st.button("Set selected active"):
                st.session_state.active_key=sel
                st.rerun()
        with c2:
            if st.button("Delete selected"):
                st.session_state.cache.pop(sel,None)
                save_cache(st.session_state.cache)
                st.rerun()

with tabs[5]:
    st.markdown("## Diagnostics")
    st.markdown("### Match discovery calls")
    if st.session_state.match_calls:
        st.dataframe(pd.DataFrame([{"OK":c.get("ok"),"Status":c.get("status"),"URL":c.get("url")} for c in st.session_state.match_calls]), use_container_width=True)
    active=st.session_state.cache.get(st.session_state.active_key)
    if active:
        st.markdown("### Cito calls in active bundle")
        st.dataframe(pd.DataFrame([{"OK":c.get("ok"),"Status":c.get("status"),"URL":c.get("url")} for c in active.get("cito_calls",[])]), use_container_width=True)
        st.markdown("### AI parsed JSON")
        st.json(active.get("ai_parsed"))
        st.markdown("### Raw AI output")
        st.code((active.get("ai_raw") or "")[:12000])

st.caption("Analysis only. This app does not place bets and cannot guarantee profit. BetMGM odds may not be discoverable via public web search.")
