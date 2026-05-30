"""
CDL Match-Day Analyst — FINAL
=============================
Black Ops 7 / CDL 2026 season.

Data sources (NO Cito — removed entirely):
  • OpenAI web search ....... live + upcoming matches, form, context, stat fallback
  • Breaking Point .......... player per-mode stats (scraped from your Streamlit server)
  • CoD Esports Wiki ........ roster / stat fallback
  • callofdutyleague.com .... official stats fallback
  • Polymarket Gamma API .... free, no key, crowd win probabilities

Secrets needed in Streamlit Cloud (Settings → Secrets):
  OPENAI_API_KEY = "sk-..."

Workflow:
  1. Refresh matches      → OpenAI (+ Breaking Point) finds live & upcoming
  2. Select a match
  3. Pick the 5 maps       → from the CORRECT current BO7 pool, as vetoes drop on Twitter/X
  4. Analyse               → pulls stats, blends with Polymarket odds, full output
  5. EV Calculator tab     → paste BetMGM line + odds → edge, EV%, stake

Honest limits:
  • Public sites publish per-MODE player stats, not per-MAP. The tool shows each
    player's stats for the mode of the map you picked. It does not fake map-specific kills.
  • Predictions are estimates. No bets are placed. 18+. BeGambleAware.org.
"""

import json
import math
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# ============================================================
# PAGE / STYLE
# ============================================================

st.set_page_config(page_title="CDL Match-Day Analyst", page_icon="🎯", layout="wide")

st.markdown("""
<style>
.stApp { background: radial-gradient(circle at top left, #12182a 0, #080b14 45%, #03050b 100%); color:#F1F5F9; }
.hero { padding:26px; border-radius:26px; border:1px solid rgba(255,90,31,.40);
  background:linear-gradient(135deg, rgba(255,90,31,.16), rgba(15,23,42,.92));
  box-shadow:0 24px 70px rgba(0,0,0,.45); margin-bottom:18px; }
.hero h1 { font-size:42px; font-weight:900; margin:0 0 8px; letter-spacing:-1px; }
.accent { color:#FF5A1F; }
.card { border:1px solid rgba(148,163,184,.18); border-radius:18px; padding:16px;
  background:rgba(15,23,42,.76); margin-bottom:12px; }
.match-card { border:1px solid rgba(255,90,31,.30); border-radius:20px; padding:18px;
  background:linear-gradient(135deg, rgba(255,90,31,.12), rgba(15,23,42,.85)); margin-bottom:14px; }
.pick-card { border:1px solid rgba(34,197,94,.32); border-radius:16px; padding:14px;
  background:linear-gradient(135deg, rgba(34,197,94,.12), rgba(15,23,42,.85)); min-height:150px; }
.risk-card { border:1px solid rgba(239,68,68,.30); border-radius:14px; padding:12px;
  background:rgba(239,68,68,.08); margin-bottom:10px; }
.pill { display:inline-block; border:1px solid rgba(148,163,184,.25); background:rgba(2,6,23,.7);
  border-radius:999px; padding:3px 10px; color:#CBD5E1; font-size:12px; margin:0 6px 5px 0; }
.pill-live { border-color:#ff2d55; color:#ff5470; }
.good{color:#22C55E;} .mid{color:#F59E0B;} .bad{color:#EF4444;} .muted{color:#94A3B8;}
div[data-testid="stMetric"]{ background:rgba(15,23,42,.7); border:1px solid rgba(148,163,184,.16);
  padding:14px; border-radius:16px; }
.stButton > button { border-radius:13px; font-weight:800; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>CDL <span class="accent">Match-Day Analyst</span></h1>
  <div class="muted" style="font-size:15px;line-height:1.55;">
    Black Ops 7 · 2026 Season. Pick the maps as vetoes drop, get player kill targets, win
    probabilities (blended with Polymarket), and EV on your BetMGM lines.
    <b>Analysis only — no bets placed, no profit guarantee. 18+.</b>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# GROUND TRUTH
# ============================================================

CACHE_FILE      = Path("cdl_final_saved.json")
MATCH_FILE      = Path("cdl_final_matches.json")
ROSTER_OVR_FILE = Path("cdl_final_rosters.json")

TEAMS = [
    "Boston Breach", "Carolina Royal Ravens", "Cloud9 New York", "FaZe Vegas",
    "G2 Minnesota", "Los Angeles Guerrillas M8", "Los Angeles Thieves",
    "Miami Heretics", "OpTic Texas", "Paris Gentle Mates",
    "Riyadh Falcons", "Toronto KOI", "Vancouver Surge",
]

# CORRECT current pool — from official @intelCDL "CDL 2026 UPDATE · Maps & Modes".
BO7_MAP_POOL = {
    "Hardpoint":        ["Sake", "Colossus", "Den", "Scar", "Gridlock", "Hacienda"],
    "Search & Destroy": ["Den", "Gridlock", "Raid", "Fringe", "Sake", "Hacienda"],
    "Overload":         ["Den", "Exposure", "Scar", "Gridlock"],
}
MODES_ORDER = ["Hardpoint", "Search & Destroy", "Overload", "Hardpoint", "Search & Destroy"]

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
PLAYER_TO_TEAM = {p.lower(): t for t, ps in VERIFIED_ROSTERS.items() for p in ps}

PRIORS = {
    "Dashy":[92,95,91],"Shotzzy":[95,93,94],"Huke":[89,87,88],"Mercules":[88,86,87],
    "aBeZy":[95,94,93],"Kenny":[92,93,91],"HyDra":[96,93,95],"Scrap":[96,92,95],
    "Simp":[96,97,94],"Drazah":[91,92,90],"04":[84,82,83],"Abuzah":[90,92,90],
    "Cellium":[94,98,93],"Exnid":[86,86,86],"KiSMET":[90,88,90],"Pred":[93,91,92],
    "Estreal":[91,89,90],"Kremp":[94,91,93],"Mamba":[86,83,85],"Skyz":[89,92,88],
    "Envoy":[91,89,90],"Ghosty":[90,90,90],"Neptune":[89,86,88],"Sib":[91,88,91],
    "CleanX":[91,89,90],"Insight":[88,93,87],"JoeDeceives":[92,94,92],"Kips":[85,85,85],
    "Snoopy":[86,85,85],"Purj":[86,84,85],"Cammy":[89,88,88],"Nastie":[89,87,88],
    "Craze":[85,83,84],"Lurqxx":[89,86,88],"Nero":[90,87,89],"SlasheR":[86,88,86],
    "Encourage":[85,82,84],"Hide":[83,85,83],"Nejra":[83,83,83],"Okis":[83,83,83],
    "MettalZ":[86,85,85],"RenKoR":[85,84,84],"SupeR":[87,86,86],"Traixx":[83,83,83],
    "Lucky":[86,88,86],"ReeaL":[88,86,87],"Standy":[88,86,87],"Fire":[83,83,83],
    "Atura":[84,86,84],"Lunarz":[85,85,85],"Nero2":[82,82,82],"Wevy":[84,84,84],
}

POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"

# ============================================================
# HELPERS
# ============================================================

def safe(x): return "" if x is None else str(x).strip()
def now(): return datetime.now().strftime("%d %b %Y %H:%M")

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

def norm_team(x):
    s = safe(x)
    if not s: return ""
    sl = s.lower().replace("&", "and")
    for t in TEAMS:
        tl = t.lower().replace("&", "and")
        if tl == sl or tl in sl or sl in tl: return t
    return s

def mode_name(x):
    m = safe(x).lower()
    if "search" in m or "snd" in m or "s&d" in m: return "Search & Destroy"
    if "overload" in m or "ovl" in m or "control" in m: return "Overload"
    return "Hardpoint"

def to_num(x, d=0.0):
    try:
        s = re.sub(r"[^0-9.\-]", "", safe(x))
        return float(s) if s not in ["", ".", "-"] else d
    except Exception: return d

def extract_json(text):
    """Tolerant JSON extraction: strips fences, finds outermost object, repairs truncation."""
    if not text: return None
    c = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.I)
    c = re.sub(r"\s*```$", "", c)
    try: return json.loads(c)
    except Exception: pass
    first = c.find("{")
    if first < 0: return None
    cand = c[first:]
    try: return json.loads(cand)
    except Exception: pass
    fixed = re.sub(r",(\s*[}\]])", r"\1", cand)
    try: return json.loads(fixed)
    except Exception: pass
    working = fixed
    for _ in range(40):
        try: return json.loads(working)
        except Exception:
            b = max(working.rfind("},"), working.rfind("],"))
            if b < 0: break
            working = working[:b+1]
            tail = working.rstrip(", \n\t")
            for _ in range(max(0, tail.count("[") - tail.count("]"))): tail += "]"
            for _ in range(max(0, tail.count("{") - tail.count("}"))): tail += "}"
            try: return json.loads(tail)
            except Exception: continue
    return None

def correct_player_team(name, claimed):
    if not name: return claimed, False
    c = PLAYER_TO_TEAM.get(name.lower().strip())
    if c and c != claimed: return c, True
    return (claimed or c or ""), False

def get_roster_for(team):
    ovr = load_json(ROSTER_OVR_FILE)
    if isinstance(ovr, dict) and ovr.get(team): return list(ovr[team]), "User override"
    if team in VERIFIED_ROSTERS: return list(VERIFIED_ROSTERS[team]), "Verified 2026"
    return [], "Unknown"

def save_roster_override(team, players):
    ovr = load_json(ROSTER_OVR_FILE)
    if not isinstance(ovr, dict): ovr = {}
    ovr[team] = [p for p in players if safe(p)]
    save_json(ROSTER_OVR_FILE, ovr)

def reset_roster(team):
    ovr = load_json(ROSTER_OVR_FILE)
    if isinstance(ovr, dict): ovr.pop(team, None); save_json(ROSTER_OVR_FILE, ovr)

def default_maps():
    return [{"map": i+1, "mode": MODES_ORDER[i], "map_name": "", "picked_by": ""} for i in range(5)]

# ============================================================
# OPENAI
# ============================================================

def openai_client(key):
    if OpenAI is None:
        raise RuntimeError("openai package missing — add `openai` to requirements.txt and reboot.")
    return OpenAI(api_key=key)

def openai_search(key, model, prompt):
    """Responses API with web_search; falls back across tool spellings."""
    c = openai_client(key)
    for tool in [{"type": "web_search"}, {"type": "web_search_preview"}, None]:
        try:
            kw = {"model": model, "input": prompt}
            if tool: kw["tools"] = [tool]; kw["tool_choice"] = "auto"
            return c.responses.create(**kw).output_text
        except Exception as e:
            last = str(e)
    raise RuntimeError(last)

def ai_match_list(key, model):
    today = datetime.now().strftime("%Y-%m-%d")
    teams = ", ".join(TEAMS)
    prompt = f"""Today is {today}. Use web search to find Call of Duty League (CDL) 2026 (Black Ops 7) matches:
- any LIVE / in-progress matches right now
- all upcoming matches in the next ~10 days

Check breakingpoint.gg, callofdutyleague.com, cod-esports.fandom.com, esports news, and X/Twitter.
The 13 teams: {teams}.

Return ONLY JSON (no prose, no fences):
{{"matches":[{{"start_time":"e.g. Sat 7 Jun 18:00 UK","event":"e.g. Major 2 Qualifiers","team_a":"","team_b":"","status":"live|upcoming"}}]}}
Live first. Max 12 matches. Only real matches. Only team names from the list."""
    raw = openai_search(key, model, prompt)
    parsed = extract_json(raw) or {}
    rows = []
    for m in parsed.get("matches", []) if isinstance(parsed, dict) else []:
        if not isinstance(m, dict): continue
        a, b = norm_team(m.get("team_a")), norm_team(m.get("team_b"))
        if a and b and a != b:
            rows.append({"start_time": safe(m.get("start_time")), "event": safe(m.get("event")) or "CDL 2026",
                         "team_a": a, "team_b": b, "status": safe(m.get("status")) or "upcoming", "source": "OpenAI"})
    return rows, raw

def ai_player_stats(key, model, team_a, team_b):
    """Get per-mode stats for all 8 players from public sites via OpenAI web search."""
    a_players = ", ".join(get_roster_for(team_a)[0])
    b_players = ", ".join(get_roster_for(team_b)[0])
    prompt = f"""Use web search on breakingpoint.gg, callofdutyleague.com stats, and cod-esports.fandom.com
to find current CDL 2026 (Black Ops 7) per-MODE player stats for these players.

{team_a}: {a_players}
{team_b}: {b_players}

For each player give per-mode figures where available:
- Hardpoint: kills per 10 minutes (kp10) and K/D
- Search & Destroy: kills per round (kpr) and K/D
- Overload: K/D and kills per game if available

Return ONLY JSON:
{{"players":[{{"player":"","team":"","hp_kp10":0.0,"hp_kd":0.0,"snd_kpr":0.0,"snd_kd":0.0,"ovl_kd":0.0,"form_note":""}}]}}
Use real numbers from the sites. If a figure is unknown, use null. No prose, no fences."""
    raw = openai_search(key, model, prompt)
    parsed = extract_json(raw) or {}
    return (parsed.get("players", []) if isinstance(parsed, dict) else []), raw

def ai_full_analysis(key, model, match, maps, stats_df):
    a_players = ", ".join(get_roster_for(match["team_a"])[0])
    b_players = ", ".join(get_roster_for(match["team_b"])[0])
    maps_text = "\n".join([f"  Map {m['map']}: {m['mode']} | {m['map_name'] or 'TBD'} | picked by {m['picked_by'] or 'TBD'}" for m in maps])
    stats_csv = stats_df.to_csv(index=False)[:12000] if not stats_df.empty else "No structured stats."
    pool = "\n".join([f"  {k}: {', '.join(v)}" for k, v in BO7_MAP_POOL.items()])
    return f"""You are a CDL 2026 (Black Ops 7) match-day betting analyst.

MATCH: {match['team_a']} vs {match['team_b']}  ({match.get('status')}, {match.get('start_time')}, {match.get('event')})

VERIFIED ROSTERS (only these players exist for these teams):
  {match['team_a']}: {a_players}
  {match['team_b']}: {b_players}

MAP POOL (only use these names):
{pool}

SELECTED MAPS for this series:
{maps_text}

Structured per-mode stats gathered:
{stats_csv}

Series format: M1 HP, M2 SnD, M3 Overload, M4 HP, M5 SnD.

Do: use the stats as the base, then web-search current form, subs and roster news. Rank ALL 8 starters
for kills. For each selected map, name the best 2 kill targets. Lean a map winner per map. Give a series
pick with probability. If you can find BetMGM decimal odds or Polymarket prices, include them; never invent odds.
Only name players from the verified rosters.

Return ONLY JSON (no prose, no fences):
{{
  "summary":"",
  "series_pick":"",
  "team_a_win_prob":0.0,
  "team_b_win_prob":0.0,
  "confidence":"High|Medium|Low",
  "player_rankings":[{{"rank":1,"player":"","team":"","best_mode":"","proj_strength":"","reason":""}}],
  "map_targets":[{{"map":1,"mode":"","map_name":"","targets":[{{"player":"","team":"","projected_kills":0.0,"note":""}}]}}],
  "map_winner_leans":[{{"map":1,"mode":"","map_name":"","lean_team":"","probability":0.0,"reason":""}}],
  "best_bets":[{{"selection":"","market":"","reason":"","confidence":"High|Medium|Low"}}],
  "avoid":[{{"selection":"","reason":""}}],
  "final_note":""
}}"""

# ============================================================
# BREAKING POINT / WIKI SCRAPE (runs on Streamlit server)
# ============================================================

@st.cache_data(ttl=900, show_spinner=False)
def scrape_text(url):
    if BeautifulSoup is None: return ""
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=20)
        if not r.ok: return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "noscript"]): t.decompose()
        return "\n".join(x.strip() for x in soup.get_text("\n").splitlines() if x.strip())
    except Exception:
        return ""

@st.cache_data(ttl=900, show_spinner=False)
def bp_match_list():
    txt = " ".join(scrape_text("https://breakingpoint.gg/matches").splitlines())
    if not txt: return []
    alt = "|".join(map(re.escape, TEAMS))
    rows = []
    for m in re.finditer(rf"(LIVE)?\s*(CDL[^~]*?)?\s*({alt})\s+\d*\s*(?:vs|v)?\s*({alt})", txt, flags=re.I):
        a, b = norm_team(m.group(3)), norm_team(m.group(4))
        if a and b and a != b:
            rows.append({"start_time": "LIVE" if m.group(1) else "", "event": safe(m.group(2)) or "CDL 2026",
                         "team_a": a, "team_b": b, "status": "live" if m.group(1) else "upcoming", "source": "Breaking Point"})
    return rows

# ============================================================
# POLYMARKET (free Gamma API, no key)
# ============================================================

@st.cache_data(ttl=600, show_spinner=False)
def polymarket_cdl(team_a, team_b):
    """Returns dict with implied win probs for the two teams if a market is found."""
    try:
        r = requests.get(f"{POLYMARKET_GAMMA}/markets",
                         params={"tag": "call-of-duty", "active": "true", "closed": "false", "limit": 60},
                         headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=15)
        if not r.ok: return None
        markets = r.json()
        markets = markets if isinstance(markets, list) else markets.get("data", markets.get("markets", []))
        sa = {w.lower() for w in team_a.split()}
        sb = {w.lower() for w in team_b.split()}
        for m in markets:
            q = safe(m.get("question") or m.get("title")).lower()
            if any(w in q for w in sa if len(w) > 3) and any(w in q for w in sb if len(w) > 3):
                prices = m.get("outcomePrices")
                outs = m.get("outcomes")
                if isinstance(prices, str): prices = json.loads(prices)
                if isinstance(outs, str): outs = json.loads(outs)
                if prices and outs and len(prices) == len(outs):
                    pm = {}
                    for o, p in zip(outs, prices):
                        team = norm_team(o)
                        pm[team] = to_num(p)
                    return {"market": q, "probs": pm, "url": "https://polymarket.com/esports/call-of-duty/games"}
        return None
    except Exception:
        return None

# ============================================================
# STATS MODEL
# ============================================================

STAT_COLS = ["Team", "Player", "Mode", "ProjKills", "KD", "Source", "Form"]

def fallback_player(team, player):
    hp, snd, ovl = PRIORS.get(player, [80, 80, 80])
    return [
        {"Team": team, "Player": player, "Mode": "Hardpoint",        "ProjKills": round(18 + (hp  - 80) * 0.35, 1), "KD": None, "Source": "Prior", "Form": ""},
        {"Team": team, "Player": player, "Mode": "Search & Destroy", "ProjKills": round(5.5 + (snd - 80) * 0.10, 1), "KD": None, "Source": "Prior", "Form": ""},
        {"Team": team, "Player": player, "Mode": "Overload",         "ProjKills": round(17 + (ovl - 80) * 0.32, 1), "KD": None, "Source": "Prior", "Form": ""},
    ]

def ai_stats_to_rows(team_a, team_b, ai_players):
    """Convert AI per-mode stat dicts to projected kills per mode."""
    rows = []
    seen = set()
    for p in ai_players:
        if not isinstance(p, dict): continue
        name = safe(p.get("player"))
        team, _ = correct_player_team(name, norm_team(p.get("team")))
        if not name or team not in (team_a, team_b): continue
        seen.add((team, name))
        hp_kp10 = to_num(p.get("hp_kp10")); snd_kpr = to_num(p.get("snd_kpr"))
        hp_kd = to_num(p.get("hp_kd")); snd_kd = to_num(p.get("snd_kd")); ovl_kd = to_num(p.get("ovl_kd"))
        form = safe(p.get("form_note"))
        # Conversions agreed: HP ≈ kp10 × 2.5 ; SnD ≈ kpr × 11
        hp_proj  = round(hp_kp10 * 2.5, 1) if hp_kp10 else (fallback_player(team, name)[0]["ProjKills"])
        snd_proj = round(snd_kpr * 11, 1)  if snd_kpr  else (fallback_player(team, name)[1]["ProjKills"])
        ovl_proj = round(17 + (ovl_kd - 1) * 9, 1) if ovl_kd else (fallback_player(team, name)[2]["ProjKills"])
        rows += [
            {"Team": team, "Player": name, "Mode": "Hardpoint",        "ProjKills": hp_proj,  "KD": hp_kd or None,  "Source": "Web stats", "Form": form},
            {"Team": team, "Player": name, "Mode": "Search & Destroy", "ProjKills": snd_proj, "KD": snd_kd or None, "Source": "Web stats", "Form": form},
            {"Team": team, "Player": name, "Mode": "Overload",         "ProjKills": ovl_proj, "KD": ovl_kd or None, "Source": "Web stats", "Form": form},
        ]
    # Fill any verified players the AI missed
    for team in (team_a, team_b):
        for player in get_roster_for(team)[0]:
            if (team, player) not in seen:
                rows += fallback_player(team, player)
    return pd.DataFrame(rows, columns=STAT_COLS)

def build_targets(stats_df, maps):
    """For each selected map, rank players by projected kills for that mode."""
    out = []
    for m in maps:
        mode = m["mode"]
        sub = stats_df[stats_df["Mode"] == mode].copy()
        if sub.empty: continue
        sub = sub.sort_values("ProjKills", ascending=False)
        out.append({"map": m["map"], "mode": mode, "map_name": m["map_name"],
                    "rows": sub[["Player", "Team", "ProjKills", "Form"]].to_dict("records")})
    return out

# ============================================================
# EV CALC
# ============================================================

def normal_cdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def parse_odds(raw, fmt):
    s = safe(raw).lower()
    if not s: return None
    if fmt == "fractional":
        if s in ("evens", "evs", "even"): return 2.0
        if "/" in s:
            try: a, b = s.split("/", 1); return float(a)/float(b)+1 if float(b) else None
            except Exception: return None
        try: return float(s)+1
        except Exception: return None
    try: return float(s)
    except Exception: return None

def ev_calc(samples_str, line, over_raw, under_raw, fmt, adj=0.0):
    samples = [float(x) for x in re.split(r"[\s,]+", safe(samples_str)) if re.match(r"^-?\d*\.?\d+$", x)]
    n = len(samples)
    if n < 2 or line is None: return None
    mu = sum(samples)/n
    sd = max(math.sqrt(sum((x-mu)**2 for x in samples)/(n-1)), 0.5)
    proj = mu + adj
    z = (line - proj)/sd
    p_under = normal_cdf(z); p_over = 1 - p_under
    do, du = parse_odds(over_raw, fmt), parse_odds(under_raw, fmt)
    sides = []
    if do: sides.append({"side": "OVER", "p": p_over, "d": do, "ev": p_over*do-1})
    if du: sides.append({"side": "UNDER", "p": p_under, "d": du, "ev": p_under*du-1})
    sides.sort(key=lambda x: -x["ev"])
    best = sides[0] if sides else None
    return {"n": n, "mu": mu, "sd": sd, "proj": proj, "p_over": p_over, "p_under": p_under, "best": best}

# ============================================================
# RENDER
# ============================================================

def cclass(c):
    c = safe(c).lower()
    return "good" if "high" in c else ("bad" if "low" in c else "mid")

def render_analysis(parsed, polymarket, maps, stats_df):
    if not parsed:
        st.error("Analysis came back unreadable. Try Analyse again."); return
    ta = round(to_num(parsed.get("team_a_win_prob")) * (100 if to_num(parsed.get("team_a_win_prob")) <= 1 else 1))
    tb = round(to_num(parsed.get("team_b_win_prob")) * (100 if to_num(parsed.get("team_b_win_prob")) <= 1 else 1))
    st.markdown(f"""<div class="match-card">
      <div class="muted">Series analysis</div>
      <h2 style="margin:6px 0;">{safe(parsed.get('series_pick')) or 'Pick'} <span class="muted">to win</span></h2>
      <span class="pill {cclass(parsed.get('confidence'))}">Confidence: {safe(parsed.get('confidence'))}</span>
      <p style="color:#CBD5E1;margin-top:10px;">{safe(parsed.get('summary'))}</p>
    </div>""", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Model — Team A", f"{ta}%")
    c2.metric("Pick", safe(parsed.get("series_pick")) or "—")
    c3.metric("Model — Team B", f"{tb}%")

    if polymarket and polymarket.get("probs"):
        st.markdown("#### Polymarket crowd odds (cross-check)")
        cols = st.columns(len(polymarket["probs"]) or 1)
        for i, (team, p) in enumerate(polymarket["probs"].items()):
            with cols[i]: st.metric(team, f"{round(p*100)}%")
        st.caption(f"Source: Polymarket · {polymarket.get('market','')[:80]}")

    st.markdown("### Player ranking (kills)")
    pr = parsed.get("player_rankings", [])
    if pr:
        df = pd.DataFrame(pr)
        if "rank" in df.columns: df = df.sort_values("rank")
        st.dataframe(df, use_container_width=True)
        top = (df.head(4)).to_dict("records")
        cols = st.columns(min(4, len(top)) or 1)
        for i, p in enumerate(top):
            with cols[i]:
                st.markdown(f"""<div class="pick-card">
                  <div class="muted">#{p.get('rank', i+1)}</div>
                  <h3 style="margin:5px 0;">{safe(p.get('player'))}</h3>
                  <span class="pill">{safe(p.get('team'))}</span>
                  <span class="pill">{safe(p.get('best_mode'))}</span>
                  <p style="color:#CBD5E1;margin-top:8px;font-size:13px;">{safe(p.get('reason'))}</p>
                </div>""", unsafe_allow_html=True)

    st.markdown("### Per-map kill targets")
    mt = parsed.get("map_targets", [])
    if mt:
        for m in mt:
            names = ", ".join([f"{safe(t.get('player'))} ({to_num(t.get('projected_kills'))} k)" for t in m.get("targets", [])])
            st.markdown(f"**Map {m.get('map')} · {safe(m.get('mode'))} · {safe(m.get('map_name')) or 'TBD'}** — {names}")
    else:
        # fall back to our own model targets
        for m in build_targets(stats_df, maps):
            top2 = m["rows"][:2]
            names = ", ".join([f"{r['Player']} ({r['ProjKills']} k)" for r in top2])
            st.markdown(f"**Map {m['map']} · {m['mode']} · {m['map_name'] or 'TBD'}** — {names}")

    st.markdown("### Map winner leans")
    ml = parsed.get("map_winner_leans", [])
    if ml: st.dataframe(pd.DataFrame(ml), use_container_width=True)

    st.markdown("### Best bets")
    bb = parsed.get("best_bets", [])
    if bb: st.dataframe(pd.DataFrame(bb), use_container_width=True)
    else: st.info("No best bets — usually means odds weren't discoverable. Use the EV tab with your BetMGM line.")

    if parsed.get("avoid"):
        st.markdown("### Avoid / risk")
        for r in parsed["avoid"]:
            st.markdown(f"""<div class="risk-card"><b>{safe(r.get('selection'))}</b><br>
              <span class="muted">{safe(r.get('reason'))}</span></div>""", unsafe_allow_html=True)
    if parsed.get("final_note"): st.caption(safe(parsed.get("final_note")))

# ============================================================
# STATE
# ============================================================

if "saved" not in st.session_state: st.session_state.saved = load_json(CACHE_FILE)
if "matches" not in st.session_state:
    mc = load_json(MATCH_FILE); st.session_state.matches = mc.get("matches", []) if isinstance(mc, dict) else []
if "maps" not in st.session_state: st.session_state.maps = default_maps()
if "sel" not in st.session_state: st.session_state.sel = 0
if "active_key" not in st.session_state: st.session_state.active_key = ""
if "ai_log" not in st.session_state: st.session_state.ai_log = []

openai_key = get_secret("OPENAI_API_KEY")
with st.sidebar:
    st.header("Setup")
    st.write("OpenAI:", "✅" if openai_key else "❌ missing")
    model = st.text_input("OpenAI model", value="gpt-4.1-mini")
    st.caption("Polymarket + Breaking Point need no key.")
    st.divider()
    st.write(f"Matches: **{len(st.session_state.matches)}**")
    st.write(f"Saved analyses: **{len(st.session_state.saved)}**")
    if st.button("Clear saved"): st.session_state.saved = {}; save_json(CACHE_FILE, {}); st.rerun()
    if st.button("Clear cache"): st.cache_data.clear(); st.rerun()

tab_match, tab_ev, tab_rosters = st.tabs(["🎯 Match Day", "💰 EV Calculator", "👥 Rosters"])

# ----------------- MATCH DAY -----------------
with tab_match:
    st.markdown("### 1 · Refresh matches")
    c1, c2 = st.columns([3, 1])
    c1.markdown('<div class="card">Pulls live + upcoming from OpenAI web search and Breaking Point.</div>', unsafe_allow_html=True)
    with c2:
        if st.button("🔄 Refresh", use_container_width=True, disabled=not openai_key):
            rows = []
            with st.spinner("Searching for matches…"):
                rows += bp_match_list()
                try:
                    ai_rows, raw = ai_match_list(openai_key, model)
                    rows += ai_rows
                    st.session_state.ai_log.append(("match_list", raw[:1500]))
                except Exception as e:
                    st.error(f"OpenAI match search failed: {e}")
            # dedupe
            seen, dd = set(), []
            for m in rows:
                k = tuple(sorted([m["team_a"].lower(), m["team_b"].lower()])) + (m.get("start_time","").lower(),)
                if k in seen: continue
                seen.add(k); dd.append(m)
            dd.sort(key=lambda m: 0 if safe(m.get("status")).lower()=="live" else 1)
            st.session_state.matches = dd
            save_json(MATCH_FILE, {"saved_at": now(), "matches": dd})
            st.rerun()

    if not st.session_state.matches:
        st.info("No matches loaded yet — hit Refresh.")
    else:
        st.dataframe(pd.DataFrame(st.session_state.matches), use_container_width=True)
        labels = [f"{i}: {'🔴 LIVE ' if safe(m.get('status')).lower()=='live' else ''}{safe(m.get('start_time'))} — {m['team_a']} vs {m['team_b']} — {safe(m.get('event'))}"
                  for i, m in enumerate(st.session_state.matches)]
        choice = st.selectbox("Select match", labels, index=min(st.session_state.sel, len(labels)-1))
        st.session_state.sel = int(choice.split(":")[0])
        match = st.session_state.matches[st.session_state.sel]

        st.markdown(f"""<div class="match-card">
          <div class="muted">{safe(match.get('start_time'))} · {safe(match.get('event'))}</div>
          <h2 style="margin:6px 0;">{match['team_a']} <span class="muted">vs</span> {match['team_b']}</h2>
          <span class="pill {'pill-live' if safe(match.get('status')).lower()=='live' else ''}">Status: {safe(match.get('status'))}</span>
        </div>""", unsafe_allow_html=True)

        st.markdown("### 2 · Pick the maps")
        st.caption("As vetoes drop on Twitter/X, pick them here. Modes are fixed; map names come from the current BO7 pool.")
        new_maps = []
        for i, row in enumerate(st.session_state.maps):
            cc1, cc2, cc3, cc4 = st.columns([0.4, 1.3, 1.6, 1.4])
            cc1.markdown(f"**M{row['map']}**")
            with cc2:
                mode = st.selectbox(f"mode{i}", ["Hardpoint","Search & Destroy","Overload"],
                                    index=["Hardpoint","Search & Destroy","Overload"].index(mode_name(row["mode"])),
                                    key=f"mode{i}", label_visibility="collapsed")
            with cc3:
                pool = [""] + BO7_MAP_POOL.get(mode, [])
                cur = row["map_name"] if row["map_name"] in pool else ""
                mapn = st.selectbox(f"map{i}", pool, index=pool.index(cur), key=f"mapn{i}", label_visibility="collapsed")
            with cc4:
                picks = ["", match["team_a"], match["team_b"], "League"]
                curp = row["picked_by"] if row["picked_by"] in picks else ""
                pb = st.selectbox(f"pick{i}", picks, index=picks.index(curp), key=f"pick{i}", label_visibility="collapsed")
            new_maps.append({"map": row["map"], "mode": mode, "map_name": mapn, "picked_by": pb})
        st.session_state.maps = new_maps

        st.markdown("### 3 · Analyse")
        key = f"{match['team_a']}|{match['team_b']}|{match.get('start_time')}|" + "|".join(f"{m['mode']}:{m['map_name']}:{m['picked_by']}" for m in new_maps)
        if st.session_state.saved.get(key):
            st.success(f"Saved analysis exists ({st.session_state.saved[key].get('saved_at')}). 0 calls to re-view.")
        a1, a2 = st.columns([3, 1])
        a1.markdown('<div class="card">Pulls per-mode stats (web), blends Polymarket odds, runs full AI analysis.</div>', unsafe_allow_html=True)
        with a2:
            go = st.button("⚡ Analyse", use_container_width=True, disabled=not openai_key)

        if go:
            with st.spinner("Gathering stats and analysing…"):
                try:
                    ai_players, raw_stats = ai_player_stats(openai_key, model, match["team_a"], match["team_b"])
                    stats_df = ai_stats_to_rows(match["team_a"], match["team_b"], ai_players)
                    pm = polymarket_cdl(match["team_a"], match["team_b"])
                    parsed = extract_json(openai_search(openai_key, model, ai_full_analysis(openai_key, model, match, new_maps, stats_df)))
                    # roster corrections
                    if isinstance(parsed, dict):
                        for sec in ["player_rankings"]:
                            for it in parsed.get(sec, []):
                                if isinstance(it, dict):
                                    t, ch = correct_player_team(it.get("player"), it.get("team"))
                                    if t: it["team"] = t
                    st.session_state.saved[key] = {"saved_at": now(), "match": match, "maps": new_maps,
                                                   "parsed": parsed, "polymarket": pm,
                                                   "stats": stats_df.fillna("").to_dict("records")}
                    save_json(CACHE_FILE, st.session_state.saved)
                    st.session_state.active_key = key
                    st.rerun()
                except Exception as e:
                    st.error(f"Analysis failed: {e}")

        active = st.session_state.saved.get(key)
        if active:
            st.session_state.active_key = key
            stats_df = pd.DataFrame(active.get("stats", []))
            render_analysis(active.get("parsed"), active.get("polymarket"), new_maps, stats_df)
            with st.expander("Raw stats gathered"):
                st.dataframe(stats_df, use_container_width=True)

# ----------------- EV CALC -----------------
with tab_ev:
    st.markdown("### Player Prop EV Calculator")
    st.caption("Paste recent kills (same mode only) + the BetMGM line + odds. Tells you edge, EV%, and a fractional-Kelly stake.")
    cc1, cc2 = st.columns(2)
    with cc1:
        fmt = st.radio("Odds format", ["fractional", "decimal"], horizontal=True)
        bankroll = st.number_input("Bankroll (£)", value=200.0, min_value=0.0, step=10.0)
        kfrac = st.slider("Kelly fraction", 0.05, 1.0, 0.25, 0.05)
    with cc2:
        st.markdown("**Tip:** HP averages ~22–30, S&D ~6–9, Overload ~16–22. Use 4+ recent maps for a stable read.")

    if "ev_bets" not in st.session_state:
        st.session_state.ev_bets = [{"player":"Shotzzy","mode":"Hardpoint","line":"25.5","over":"10/11","under":"10/11","samples":"28, 31, 24, 27, 30, 26","adj":"0"}]
    cadd, cclear = st.columns(2)
    if cadd.button("➕ Add bet"):
        st.session_state.ev_bets.append({"player":"","mode":"Hardpoint","line":"","over":"","under":"","samples":"","adj":"0"}); st.rerun()
    if cclear.button("🗑️ Clear all"):
        st.session_state.ev_bets = []; st.rerun()

    results = []
    for i, bet in enumerate(st.session_state.ev_bets):
        st.markdown('<div class="card">', unsafe_allow_html=True)
        r1c1, r1c2, r1c3 = st.columns([2, 1.4, 0.7])
        bet["player"] = r1c1.text_input("Player", value=bet["player"], key=f"evp{i}")
        bet["mode"] = r1c2.selectbox("Mode", ["Hardpoint","Search & Destroy","Overload"],
                                     index=["Hardpoint","Search & Destroy","Overload"].index(bet["mode"]), key=f"evm{i}")
        if r1c3.button("✕", key=f"evx{i}"):
            st.session_state.ev_bets.pop(i); st.rerun()
        r2 = st.columns(4)
        bet["line"] = r2[0].text_input("Line", value=bet["line"], key=f"evl{i}", placeholder="25.5")
        bet["over"] = r2[1].text_input("Over odds", value=bet["over"], key=f"evo{i}", placeholder="10/11 or 1.91")
        bet["under"] = r2[2].text_input("Under odds", value=bet["under"], key=f"evu{i}", placeholder="10/11 or 1.91")
        bet["adj"] = r2[3].text_input("Adjust ±", value=bet["adj"], key=f"eva{i}")
        bet["samples"] = st.text_input("Recent kills (same mode, comma separated)", value=bet["samples"], key=f"evs{i}")
        try: adj = float(bet["adj"]) if bet["adj"] else 0.0
        except: adj = 0.0
        try: line = float(bet["line"]) if bet["line"] else None
        except: line = None
        r = ev_calc(bet["samples"], line, bet["over"], bet["under"], fmt, adj)
        if r and r["best"]:
            b = r["best"]
            m = st.columns(5)
            m[0].metric("Proj", f"{r['proj']:.1f}k", f"n={r['n']}, σ={r['sd']:.1f}")
            m[1].metric("P(over)", f"{r['p_over']*100:.0f}%")
            m[2].metric("P(under)", f"{r['p_under']*100:.0f}%")
            m[3].metric("Best", f"{b['side']} {bet['line']}", f"EV {b['ev']*100:+.1f}%")
            stake = max(0, (b['p']*b['d']-1)/(b['d']-1))*kfrac*bankroll if b['d']>1 else 0
            m[4].metric("Stake", f"£{stake:.2f}" if b['ev']>0 else "—")
            if r["n"] < 4: st.warning(f"Only {r['n']} samples — shaky read.")
            results.append({"Player":bet["player"],"Mode":bet["mode"],"Side":b["side"],"Line":bet["line"],"EV%":round(b["ev"]*100,1),"Proj":round(r["proj"],1)})
        else:
            st.caption("Enter a line and ≥2 kill samples.")
        st.markdown('</div>', unsafe_allow_html=True)

    if results:
        st.markdown("### Ranking")
        rdf = pd.DataFrame(results).sort_values("EV%", ascending=False)
        st.dataframe(rdf, use_container_width=True)
        pos = rdf[rdf["EV%"] > 0]
        for k in [2, 3, 4]:
            if len(pos) >= k:
                st.markdown(f"**Best {k}:** " + ", ".join(f"**{r.Player}** {r.Side}" for _, r in pos.head(k).iterrows()))
        if pos.empty:
            st.warning("Nothing +EV at these prices — 'no bet' is a valid answer.")

# ----------------- ROSTERS -----------------
with tab_rosters:
    st.markdown("### Roster editor")
    st.caption("Verified 2026 rosters baked in. Edit if a player moves mid-season; changes persist.")
    team = st.selectbox("Team", TEAMS)
    players, source = get_roster_for(team)
    st.markdown(f"**Source:** `{source}`")
    edited = []
    cols = st.columns(4)
    for i in range(4):
        edited.append(cols[i].text_input(f"Player {i+1}", value=players[i] if i < len(players) else "", key=f"r{team}{i}"))
    b1, b2 = st.columns(2)
    if b1.button("💾 Save override"):
        save_roster_override(team, edited); st.success("Saved."); st.rerun()
    if b2.button("↩ Reset to verified"):
        reset_roster(team); st.success("Reset."); st.rerun()
    st.divider()
    st.dataframe(pd.DataFrame([{"Team": t, "Players": ", ".join(get_roster_for(t)[0]), "Source": get_roster_for(t)[1]} for t in TEAMS]), use_container_width=True)

st.caption("Analysis only · no bets placed · no profit guarantee · odds may be unavailable or move · 18+ · BeGambleAware.org · GamCare 0808 8020 133")
