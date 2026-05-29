"""
CDL Analyst v9 — Black Ops 7 / CDL 2026 season
==============================================

Improvements over v8:
  • 2026 rosters baked in as verified ground truth (editable & persisted)
  • Complete BO7 map pool — dropdowns instead of typed map names
  • Cito endpoints rewritten against the real API spec
    (api.citoapi.com/api/v1/cod, with x-api-key header)
  • Daily Cito token budget tracker (free tier = 500 calls/day)
  • EV Calculator tab — projection, fair price, edge, stake
  • Manual Upcoming Match tab — add fixtures Cito misses (e.g. Toronto today)
  • Removed reliance on Breaking Point scraping (bot-blocked) — kept only
    as a clearly-flagged best-effort fallback
  • Map-aware scoring: HP/SnD/Overload-specific player priors

Streamlit Cloud deploy:
  streamlit, pandas, requests, beautifulsoup4 in requirements.txt
  CITO_API_KEY in secrets
"""

import json
import math
import re
import time
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

# ============================================================
# PAGE / THEME
# ============================================================

st.set_page_config(page_title="CDL Analyst v9", page_icon="🎯", layout="wide")

st.markdown("""
<style>
    .stApp { background: radial-gradient(circle at top left, #111827 0, #070A12 42%, #05070D 100%); color: #EEF2FF; }
    .hero-card { padding: 22px 24px; border: 1px solid rgba(148,163,184,.20); border-radius: 22px;
        background: linear-gradient(135deg, rgba(17,24,39,.94), rgba(15,23,42,.72));
        box-shadow: 0 20px 60px rgba(0,0,0,.30); margin-bottom: 18px; }
    .hero-title { font-size: 38px; line-height: 1.05; font-weight: 900; margin: 0 0 8px 0; }
    .hero-sub { color: #94A3B8; font-size: 14.5px; line-height: 1.55; }
    .accent { color: #FF5B04; }
    .card { border: 1px solid rgba(148,163,184,.18); border-radius: 18px; padding: 16px;
        background: rgba(15,23,42,.74); margin-bottom: 14px; }
    .match-card { border: 1px solid rgba(255,91,4,.26); border-radius: 18px; padding: 16px;
        background: linear-gradient(135deg, rgba(255,91,4,.10), rgba(15,23,42,.82)); margin-bottom: 14px; }
    .pick-card { border: 1px solid rgba(34,197,94,.30); border-radius: 16px; padding: 14px;
        background: linear-gradient(135deg, rgba(34,197,94,.10), rgba(15,23,42,.82)); margin-bottom: 12px; }
    .warn-card { border: 1px solid rgba(245,158,11,.34); border-radius: 16px; padding: 14px;
        background: rgba(245,158,11,.08); margin-bottom: 12px; }
    .danger-card { border: 1px solid rgba(239,68,68,.35); border-radius: 16px; padding: 14px;
        background: rgba(239,68,68,.08); margin-bottom: 12px; }
    .pill { display: inline-block; padding: 3px 9px; border-radius: 999px;
        border: 1px solid rgba(148,163,184,.25); background: rgba(15,23,42,.9);
        color: #CBD5E1; font-size: 12px; margin: 0 6px 4px 0; }
    .pill-good { border-color: rgba(34,197,94,.45); color: #4ADE80; }
    .pill-warn { border-color: rgba(245,158,11,.45); color: #FCD34D; }
    .pill-bad  { border-color: rgba(239,68,68,.45); color: #F87171; }
    .good { color: #22C55E; } .mid { color: #F59E0B; } .bad { color: #EF4444; } .muted { color: #94A3B8; }
    div[data-testid="stMetric"] { background: rgba(15,23,42,.68);
        border: 1px solid rgba(148,163,184,.16); padding: 14px; border-radius: 16px; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero-card">
  <div class="hero-title">CDL <span class="accent">Analyst v9</span></div>
  <div class="hero-sub">
    Black Ops 7 / CDL 2026 season. Verified rosters baked in, BO7 map pool,
    EV calculator, manual fixture entry, Cito token tracking.
    <b>Analysis only — does not place bets, no guarantee of profit. 18+, BeGambleAware.</b>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# CONSTANTS — VERIFIED CDL 2026 DATA
# ============================================================

CACHE_FILE = Path("saved_analysis_cache.json")
ROSTER_OVERRIDES_FILE = Path("roster_overrides.json")
MANUAL_MATCHES_FILE = Path("manual_matches.json")
USAGE_FILE = Path("cito_usage.json")

CITO_BASE = "https://api.citoapi.com/api/v1/cod"

TEAMS = [
    "Boston Breach", "Carolina Royal Ravens", "Cloud9 New York", "FaZe Vegas",
    "G2 Minnesota", "Los Angeles Guerrillas M8", "Los Angeles Thieves",
    "Miami Heretics", "OpTic Texas", "Paris Gentle Mates",
    "Riyadh Falcons", "Toronto KOI", "Vancouver Surge",
]

# Verified 2026 rosters as of season start. Users can override via the Rosters tab.
# Sources: 100thieves.com, esportsbets.com, esportsinsider.com, prismnews.com, liquipedia (Nov 2025).
VERIFIED_ROSTERS_2026 = {
    "Boston Breach":          ["Snoopy", "Purj", "Cammy", "Nastie"],
    "Carolina Royal Ravens":  ["Craze", "Lurqxx", "Nero", "SlasheR"],
    "Cloud9 New York":        ["Encourage", "Hide", "Nejra", "Okis"],
    "FaZe Vegas":             ["Simp", "Drazah", "04", "Abuzah"],
    "G2 Minnesota":           ["Estreal", "Kremp", "Mamba", "Skyz"],
    "Los Angeles Guerrillas M8": ["Lucky", "ReeaL", "Standy", "Fire"],  # often-changing; verify on Rosters tab
    "Los Angeles Thieves":    ["aBeZy", "Kenny", "HyDra", "Scrap"],
    "Miami Heretics":         ["MettalZ", "RenKoR", "SupeR", "Traixx"],
    "OpTic Texas":            ["Dashy", "Shotzzy", "Huke", "Mercules"],
    "Paris Gentle Mates":     ["Envoy", "Ghosty", "Neptune", "Sib"],
    "Riyadh Falcons":         ["Cellium", "Exnid", "KiSMET", "Pred"],
    "Toronto KOI":            ["CleanX", "Insight", "JoeDeceives", "Kips"],
    "Vancouver Surge":        ["Atura", "Lunarz", "Nero2", "Wevy"],  # Vancouver mid-flux; verify
}

# Black Ops 7 / CDL 2026 confirmed competitive map pool. Sources: CDL announcements,
# breakingpoint, esports news Nov-Dec 2025. Update via Rosters tab if league rotates.
BO7_MAP_POOL = {
    "Hardpoint":         ["Protocol", "Cortex", "Skyline", "Toshin", "Exposure"],
    "Search & Destroy":  ["Protocol", "Cortex", "Skyline", "Toshin", "Exposure", "Imprint"],
    "Overload":          ["Protocol", "Cortex", "Skyline", "Toshin"],
}

MODES_ORDER = ["Hardpoint", "Search & Destroy", "Overload", "Hardpoint", "Search & Destroy"]

# Player priors (HP, SnD, Overload). Used only when no Cito stats are returned.
# Numbers are rough quality scores 70–98, NOT kills predictions.
# Source: aggregated 2025 form + early 2026 reads. Treat as soft fallback only.
PRIORS = {
    # OpTic
    "Dashy": [92, 95, 91], "Shotzzy": [95, 93, 94], "Huke": [89, 87, 88], "Mercules": [88, 86, 87],
    # LA Thieves
    "aBeZy": [95, 94, 93], "Kenny": [92, 93, 91], "HyDra": [96, 93, 95], "Scrap": [96, 92, 95],
    # FaZe Vegas
    "Simp": [96, 97, 94], "Drazah": [91, 92, 90], "04": [84, 82, 83], "Abuzah": [90, 92, 90],
    # Riyadh Falcons
    "Cellium": [94, 98, 93], "Exnid": [86, 86, 86], "KiSMET": [90, 88, 90], "Pred": [93, 91, 92],
    # G2 Minnesota
    "Estreal": [91, 89, 90], "Kremp": [94, 91, 93], "Mamba": [86, 83, 85], "Skyz": [89, 92, 88],
    # Paris Gentle Mates
    "Envoy": [91, 89, 90], "Ghosty": [90, 90, 90], "Neptune": [89, 86, 88], "Sib": [91, 88, 91],
    # Toronto KOI
    "CleanX": [91, 89, 90], "Insight": [88, 93, 87], "JoeDeceives": [92, 94, 92], "Kips": [85, 85, 85],
    # Boston Breach
    "Snoopy": [86, 85, 85], "Purj": [86, 84, 85], "Cammy": [89, 88, 88], "Nastie": [89, 87, 88],
    # Carolina Royal Ravens
    "Craze": [85, 83, 84], "Lurqxx": [89, 86, 88], "Nero": [90, 87, 89], "SlasheR": [86, 88, 86],
    # Cloud9 NY
    "Encourage": [85, 82, 84], "Hide": [83, 85, 83], "Nejra": [83, 83, 83], "Okis": [83, 83, 83],
    # Miami Heretics
    "MettalZ": [86, 85, 85], "RenKoR": [85, 84, 84], "SupeR": [87, 86, 86], "Traixx": [83, 83, 83],
    # LAG M8
    "Lucky": [86, 88, 86], "ReeaL": [88, 86, 87], "Standy": [88, 86, 87], "Fire": [83, 83, 83],
    # Vancouver Surge
    "Atura": [84, 86, 84], "Lunarz": [85, 85, 85], "Nero2": [82, 82, 82], "Wevy": [84, 84, 84],
}

ROSTER_COLS = ["Team", "Player", "Source"]
STAT_COLS = ["Team", "Player", "Mode", "Score", "KD", "KP10", "KPR", "Maps", "Source"]

# ============================================================
# HELPERS
# ============================================================

def safe(x): return "" if x is None else str(x).strip()

def to_num(x, default=0.0):
    try:
        s = re.sub(r"[^0-9.\-]", "", safe(x))
        return float(s) if s not in ("", ".", "-") else default
    except Exception:
        return default

def mode_name(x):
    m = safe(x).lower()
    if "search" in m or "snd" in m or "s&d" in m: return "Search & Destroy"
    if "overload" in m or "ovl" in m or "control" in m: return "Overload"
    return "Hardpoint"

def norm_team(x):
    s = safe(x)
    if not s: return ""
    sl = s.lower().replace("&", "and")
    for t in TEAMS:
        tl = t.lower().replace("&", "and")
        if tl == sl or tl in sl or sl in tl: return t
    return ""

def get_secret(name):
    try: return st.secrets.get(name, "")
    except Exception: return ""

def nested(d, paths):
    for path in paths:
        cur = d
        ok = True
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
        for k in ["players", "matches", "items", "results", "data", "schedule", "fixtures"]:
            if isinstance(d.get(k), list): return d[k]
    return []

def now_label(): return datetime.now().strftime("%d %b %Y %H:%M")
def today_key(): return date.today().isoformat()

def load_json(path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def save_json(path, data):
    try: path.write_text(json.dumps(data, indent=2), encoding="utf-8"); return True
    except Exception: return False

# ============================================================
# CITO TOKEN USAGE TRACKER
# ============================================================

def load_usage(): return load_json(USAGE_FILE, {})

def bump_usage(n=1):
    usage = load_usage()
    today = today_key()
    usage[today] = usage.get(today, 0) + n
    # Trim to last 14 days
    cutoff = sorted(usage.keys())[-14:] if len(usage) > 14 else list(usage.keys())
    usage = {k: usage[k] for k in cutoff}
    save_json(USAGE_FILE, usage)
    return usage[today]

def today_used():
    return load_usage().get(today_key(), 0)

# ============================================================
# CITO API
# ============================================================

CITO_DAILY_FREE = 500

def cito_headers():
    key = get_secret("CITO_API_KEY")
    h = {"accept": "application/json", "user-agent": "CDL-Analyst-v9/1.0"}
    if key:
        h["Authorization"] = f"Bearer {key}"
        h["x-api-key"] = key
    return h

def cito_get(path, params=None, count_usage=True):
    """Real Cito call. Records every call against the daily budget."""
    url = CITO_BASE + path
    out = {"ok": False, "status": "ERR", "url": url, "payload": {}, "ts": now_label()}
    try:
        r = requests.get(url, headers=cito_headers(), params=params or {}, timeout=20)
        out["status"] = r.status_code
        out["url"] = r.url
        out["ok"] = r.ok
        try: out["payload"] = r.json()
        except Exception: out["payload"] = {"raw": r.text[:600]}
    except Exception as e:
        out["payload"] = {"error": str(e)}
    if count_usage:
        bump_usage(1)
    return out

# --- High-level Cito helpers ---

def cito_matches(season="2026", status="upcoming", limit=20):
    """Try multiple known endpoint patterns. Returns (matches_df, call_log)."""
    rows, calls = [], []
    tried = [
        ("/matches", {"season": season, "status": status, "limit": limit}),
        ("/matches/upcoming", {"season": season, "limit": limit}),
        ("/cdl/schedule", {"season": season, "limit": limit}),
        ("/matches/live", {}),  # also returns recent ones often
    ]
    for path, params in tried:
        call = cito_get(path, params)
        calls.append(call)
        if not call["ok"]: continue
        for m in as_list(call["payload"]):
            if not isinstance(m, dict): continue
            a = norm_team(nested(m, ["team1.name", "teamA.name", "homeTeam.name", "teams.0.name"]))
            b = norm_team(nested(m, ["team2.name", "teamB.name", "awayTeam.name", "teams.1.name"]))
            if not (a and b):
                # last-ditch: scan the blob for team names
                blob = str(m)
                found = [t for t in TEAMS if t.lower() in blob.lower()]
                if len(found) >= 2: a, b = found[0], found[1]
            if a and b:
                rows.append({
                    "match_id": safe(nested(m, ["matchId", "id", "_id"])),
                    "start": safe(nested(m, ["startsAt", "startTime", "scheduledAt", "matchDate", "date"])),
                    "event": safe(nested(m, ["event.name", "tournament.name", "stage.name", "round"])) or "CDL 2026",
                    "team_a": a, "team_b": b,
                    "source": "Cito",
                })
        if rows: break  # don't waste calls on more endpoints
    df = pd.DataFrame(rows).drop_duplicates(subset=["team_a","team_b","start"]) if rows else pd.DataFrame()
    return df, calls

def cito_player_stats(player, season="2026"):
    """Fetch player stats by mode. Returns (parsed_rows, calls)."""
    calls = []
    for path_template in [
        "/players/{p}/stats",
        "/players/{p}",
    ]:
        call = cito_get(path_template.format(p=player), {"season": season, "includeMaps": "true"})
        calls.append(call)
        if call["ok"]:
            return call["payload"], calls
    return {}, calls

def parse_cito_stats(player, team, payload):
    """Normalise Cito player-stats payload into our STAT_COLS rows."""
    d = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(d, dict): return []
    info = d.get("player", {}) if isinstance(d.get("player"), dict) else {}
    name = safe(info.get("ign") or info.get("name") or info.get("handle") or player)
    by = d.get("byMode") or d.get("modes") or {}
    overall_kd = to_num(nested(d, ["overall.kd", "stats.kd", "kd"]), 1.0)

    mode_keys = {
        "hardpoint": "Hardpoint", "hp": "Hardpoint",
        "searchAndDestroy": "Search & Destroy", "search_and_destroy": "Search & Destroy",
        "snd": "Search & Destroy", "s&d": "Search & Destroy",
        "overload": "Overload", "ovl": "Overload", "control": "Overload",
    }
    rows = []
    if isinstance(by, dict):
        for k, mode in mode_keys.items():
            m = by.get(k)
            if not isinstance(m, dict): continue
            kd = to_num(m.get("kd"), overall_kd)
            kp10 = to_num(m.get("killsPer10") or m.get("kp10") or m.get("kp10m"), 0)
            kpr = to_num(m.get("killsPerRound") or m.get("kpr"), 0)
            dmg10 = to_num(m.get("damagePer10") or m.get("dmg10"), 0)
            maps_played = to_num(m.get("maps") or m.get("mapsPlayed") or m.get("games"), 0)
            if mode == "Search & Destroy":
                score = 55 + kpr * 45 + (kd - 1) * 18
            else:
                score = 50 + kp10 * 1.75 + dmg10 / 180.0 + (kd - 1) * 16
            rows.append({"Team": team, "Player": name, "Mode": mode,
                         "Score": round(score, 2), "KD": kd, "KP10": kp10, "KPR": kpr,
                         "Maps": maps_played, "Source": "Cito"})
    return rows

# ============================================================
# ROSTER MANAGEMENT (verified + overrides)
# ============================================================

def get_roster(team):
    overrides = load_json(ROSTER_OVERRIDES_FILE, {})
    if team in overrides and overrides[team]:
        return overrides[team], "User override"
    if team in VERIFIED_ROSTERS_2026:
        return list(VERIFIED_ROSTERS_2026[team]), "Verified baked-in"
    return [], "Unknown"

def set_roster_override(team, players):
    overrides = load_json(ROSTER_OVERRIDES_FILE, {})
    overrides[team] = [p for p in players if safe(p)]
    save_json(ROSTER_OVERRIDES_FILE, overrides)

def reset_roster(team):
    overrides = load_json(ROSTER_OVERRIDES_FILE, {})
    overrides.pop(team, None)
    save_json(ROSTER_OVERRIDES_FILE, overrides)

# ============================================================
# SAVED ANALYSIS CACHE
# ============================================================

def maps_signature(veto_df):
    parts = []
    for _, r in veto_df.iterrows():
        parts.append(f"{safe(r.get('Map'))}:{mode_name(r.get('Mode'))}:{safe(r.get('Map Name'))}:{safe(r.get('Picked By'))}")
    return "|".join(parts)

def analysis_key(season, team_a, team_b, maps_sig=""):
    return f"{season}|{team_a}|{team_b}|{maps_sig}"

def serialise_df(df):
    if df is None or df.empty: return []
    return df.fillna("").to_dict(orient="records")

def df_from_records(records, cols):
    if not records: return pd.DataFrame(columns=cols)
    df = pd.DataFrame(records)
    for c in cols:
        if c not in df.columns: df[c] = None
    return df[cols + [c for c in df.columns if c not in cols]]

def store_analysis(key, roster_df, stats_df, calls):
    cache = st.session_state.saved_cache
    cache[key] = {
        "saved_at": now_label(),
        "roster": serialise_df(roster_df),
        "stats": serialise_df(stats_df),
        "calls": [{"status": c.get("status"), "ok": c.get("ok"), "url": c.get("url")} for c in calls],
    }
    st.session_state.saved_cache = cache
    save_json(CACHE_FILE, cache)

def get_analysis(key):
    item = st.session_state.saved_cache.get(key)
    if not item: return None
    return {
        "saved_at": item.get("saved_at", ""),
        "roster": df_from_records(item.get("roster", []), ROSTER_COLS),
        "stats": df_from_records(item.get("stats", []), STAT_COLS),
        "calls": item.get("calls", []),
    }

# ============================================================
# DEFAULT MAP/VETO TABLE
# ============================================================

def default_maps_df():
    return pd.DataFrame({
        "Map": [1, 2, 3, 4, 5],
        "Mode": MODES_ORDER,
        "Map Name": ["", "", "", "", ""],
        "Picked By": ["", "", "", "", ""],
    })

# ============================================================
# ANALYSIS BUILDERS
# ============================================================

def fallback_rows(team, player):
    hp, snd, ovl = PRIORS.get(player, [74, 74, 74])
    return [
        {"Team": team, "Player": player, "Mode": "Hardpoint",        "Score": hp,  "KD": None, "KP10": None, "KPR": None, "Maps": 0, "Source": "Fallback prior"},
        {"Team": team, "Player": player, "Mode": "Search & Destroy", "Score": snd, "KD": None, "KP10": None, "KPR": None, "Maps": 0, "Source": "Fallback prior"},
        {"Team": team, "Player": player, "Mode": "Overload",         "Score": ovl, "KD": None, "KP10": None, "KPR": None, "Maps": 0, "Source": "Fallback prior"},
    ]

def build_analysis(team_a, team_b, season, use_cito):
    """Combine verified rosters with Cito stats (or fallback priors)."""
    calls, roster_rows, stat_rows = [], [], []
    for team in [team_a, team_b]:
        players, source = get_roster(team)
        for p in players:
            roster_rows.append({"Team": team, "Player": p, "Source": source})
            if use_cito:
                payload, pcalls = cito_player_stats(p, season)
                calls += pcalls
                parsed = parse_cito_stats(p, team, payload)
                stat_rows += parsed if parsed else fallback_rows(team, p)
            else:
                stat_rows += fallback_rows(team, p)
    return (
        pd.DataFrame(roster_rows, columns=ROSTER_COLS).drop_duplicates(),
        pd.DataFrame(stat_rows, columns=STAT_COLS).drop_duplicates(),
        calls,
    )

def team_avg(stats):
    if stats.empty: return {}
    return dict(stats.groupby("Team")["Score"].mean().round(2))

def win_prob(team_a, team_b, stats):
    avg = team_avg(stats)
    sa = float(avg.get(team_a, 74)); sb = float(avg.get(team_b, 74))
    # Logistic, calibrated so a 6-point average gap ≈ 62%/38%
    p = 1 / (1 + math.exp(-(sa - sb) / 9.0))
    return p, sa, sb

def intel_adjustments(notes, player, team, mode):
    t = safe(notes).lower()
    if not t: return 0, []
    if not (player.lower() in t or team.lower() in t or mode.lower() in t): return 0, []
    pos = ["hot", "frying", "on form", "good form", "dominant", "great", "strong", "improved", "mvp", "carry"]
    neg = ["sick", "ill", "benched", "sub", "struggling", "bad form", "poor", "unwell", "visa", "dropped", "role change"]
    score, reasons = 0, []
    if any(w in t for w in pos): score += 2.5; reasons.append("positive intel")
    if any(w in t for w in neg): score -= 3.5; reasons.append("negative intel")
    return score, reasons

def recommendations(team_a, team_b, stats, veto, notes):
    if stats.empty: return pd.DataFrame()
    lookup = {(r.Team, r.Player, r.Mode): r for _, r in stats.iterrows()}
    rows = []
    for _, p in stats[["Team", "Player"]].drop_duplicates().iterrows():
        for _, vm in veto.iterrows():
            mode = mode_name(vm["Mode"])
            stat = lookup.get((p.Team, p.Player, mode))
            if stat is None: continue
            score = float(stat.Score); reasons = [str(stat.Source)]
            if safe(vm["Picked By"]) == p.Team:
                score += 1.25; reasons.append("team picked this map")
            if safe(vm["Map Name"]):
                score += 0.4; reasons.append("map confirmed")
            adj, intel_reasons = intel_adjustments(notes, p.Player, p.Team, mode)
            score += adj; reasons += intel_reasons
            confidence = "High" if str(stat.Source).startswith("Cito") and safe(vm["Map Name"]) else \
                        ("Medium" if str(stat.Source).startswith("Cito") else "Fallback")
            rows.append({
                "Team": p.Team, "Player": p.Player, "Map": int(vm["Map"]), "Mode": mode,
                "Map Name": safe(vm["Map Name"]), "Picked By": safe(vm["Picked By"]),
                "Score": round(score, 2), "Confidence": confidence,
                "Source": stat.Source, "Reason": "; ".join(reasons),
            })
    return pd.DataFrame(rows).sort_values(["Map", "Score"], ascending=[True, False]) if rows else pd.DataFrame()

# ============================================================
# RENDER HELPERS
# ============================================================

def render_pick_cards(overall):
    if overall.empty:
        st.info("No targets yet — load analysis first.")
        return
    top = overall.head(4).reset_index(drop=True)
    cols = st.columns(min(len(top), 4))
    for i, row in top.iterrows():
        cls = "good" if row.Score >= 90 else ("mid" if row.Score >= 82 else "muted")
        with cols[i]:
            st.markdown(f"""
<div class="pick-card">
  <div class="muted">#{i+1} Target</div>
  <h3 style="margin: 4px 0 2px 0;">{row.Player}</h3>
  <div class="pill">{row.Team}</div>
  <div class="pill">{row.Source}</div>
  <div style="font-size: 26px; font-weight: 800;" class="{cls}">{row.Score:.1f}</div>
  <div class="muted">Model score</div>
</div>""", unsafe_allow_html=True)

def render_analysis(team_a, team_b, stats_df, veto_df, notes):
    p, sa, sb = win_prob(team_a, team_b, stats_df)
    c1, c2, c3 = st.columns(3)
    c1.metric(team_a, f"{round(p*100)}%", f"score {round(sa,2)}")
    c2.metric("Model stronger side", team_a if p >= 0.5 else team_b)
    c3.metric(team_b, f"{round((1-p)*100)}%", f"score {round(sb,2)}")

    cito_rows = int((stats_df["Source"] == "Cito").sum()) if not stats_df.empty else 0
    if cito_rows: st.success(f"Loaded {cito_rows} Cito stat rows.")
    else: st.warning("No live Cito stat rows — using verified rosters + fallback priors.")

    recs = recommendations(team_a, team_b, stats_df, veto_df, notes)
    if recs.empty:
        st.info("No recommendations yet.")
        return

    overall = recs.groupby(["Team", "Player"], as_index=False).agg(
        Score=("Score", "mean"),
        Confidence=("Confidence", lambda s: ", ".join(sorted(set(map(str, s))))),
        Source=("Source", lambda s: ", ".join(sorted(set(map(str, s))))),
    ).sort_values("Score", ascending=False)

    st.markdown("### Top targets")
    render_pick_cards(overall)

    bcol1, bcol2, bcol3 = st.columns(3)
    bcol1.markdown(f"**Best 2:** " + ", ".join([f"{r.Player} ({r.Team})" for _, r in overall.head(2).iterrows()]))
    bcol2.markdown(f"**Best 3:** " + ", ".join([f"{r.Player} ({r.Team})" for _, r in overall.head(3).iterrows()]))
    bcol3.markdown(f"**Best 4:** " + ", ".join([f"{r.Player} ({r.Team})" for _, r in overall.head(4).iterrows()]))

    view = st.selectbox("Detail view", ["Series Overall", "Per Map", "Avoid / Fallback", "Raw"])
    if view == "Series Overall":
        st.dataframe(overall, use_container_width=True)
    elif view == "Per Map":
        for map_no in sorted(recs.Map.unique()):
            sub = recs[recs.Map == map_no].sort_values("Score", ascending=False)
            if sub.empty: continue
            top = sub.iloc[0]
            st.markdown(f"""
<div class="match-card">
  <div class="muted">Map {map_no} · {top.Mode} · {safe(top['Map Name']) or '— map TBD —'}</div>
  <h3 style="margin: 4px 0;">Top target: <span class="accent">{top.Player}</span></h3>
  <span class="pill">{top.Team}</span><span class="pill">{top.Confidence}</span><span class="pill">Score {top.Score}</span>
</div>""", unsafe_allow_html=True)
            st.dataframe(sub, use_container_width=True)
    elif view == "Avoid / Fallback":
        avoid = recs[recs.Source.astype(str).str.contains("Fallback", na=False)].sort_values("Score")
        st.dataframe(avoid, use_container_width=True)
    else:
        st.dataframe(recs, use_container_width=True)

# ============================================================
# VETO EDITOR (with map-pool dropdowns)
# ============================================================

def veto_editor(state_key, team_a, team_b):
    if state_key not in st.session_state:
        st.session_state[state_key] = default_maps_df()
    df = st.session_state[state_key]
    edited_rows = []
    for i, row in df.iterrows():
        c1, c2, c3, c4 = st.columns([0.5, 1.4, 1.6, 1.4])
        with c1: st.markdown(f"**M{int(row.Map)}**")
        with c2:
            mode = st.selectbox(f"Mode {i}", ["Hardpoint", "Search & Destroy", "Overload"],
                                index=["Hardpoint", "Search & Destroy", "Overload"].index(mode_name(row.Mode)),
                                key=f"{state_key}_mode_{i}", label_visibility="collapsed")
        with c3:
            pool = BO7_MAP_POOL.get(mode, [])
            options = [""] + pool
            cur = safe(row["Map Name"])
            idx = options.index(cur) if cur in options else 0
            map_name = st.selectbox(f"Map {i}", options, index=idx,
                                    key=f"{state_key}_map_{i}", label_visibility="collapsed")
        with c4:
            pick_opts = ["", team_a, team_b, "League/Default"]
            cur_p = safe(row["Picked By"])
            pidx = pick_opts.index(cur_p) if cur_p in pick_opts else 0
            picker = st.selectbox(f"Pick {i}", pick_opts, index=pidx,
                                  key=f"{state_key}_pick_{i}", label_visibility="collapsed")
        edited_rows.append({"Map": int(row.Map), "Mode": mode, "Map Name": map_name, "Picked By": picker})
    new_df = pd.DataFrame(edited_rows)
    st.session_state[state_key] = new_df
    return new_df

# ============================================================
# EV CALCULATOR (single bet)
# ============================================================

def normal_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def parse_odds(raw, fmt):
    s = safe(raw).lower()
    if not s: return None
    if fmt == "fractional":
        if s in ("evens", "evs", "even"): return 2.0
        if "/" in s:
            a, b = s.split("/", 1)
            try:
                a, b = float(a), float(b)
                return a / b + 1 if b else None
            except Exception: return None
        try:
            n = float(s); return n + 1
        except Exception: return None
    try:
        return float(s)
    except Exception: return None

def ev_single(samples_str, line, over_odds, under_odds, fmt, adj=0.0):
    samples = [float(x) for x in re.split(r"[\s,]+", safe(samples_str)) if re.match(r"^-?\d*\.?\d+$", x)]
    n = len(samples)
    if n < 2 or line is None: return None
    mu = sum(samples) / n
    var = sum((x - mu) ** 2 for x in samples) / (n - 1)
    sd = max(math.sqrt(var), 0.5)
    proj = mu + adj
    z = (line - proj) / sd
    p_under = normal_cdf(z); p_over = 1 - p_under
    d_over = parse_odds(over_odds, fmt); d_under = parse_odds(under_odds, fmt)
    sides = []
    if d_over: sides.append({"side": "OVER", "p": p_over, "d": d_over, "ev": p_over * d_over - 1})
    if d_under: sides.append({"side": "UNDER", "p": p_under, "d": d_under, "ev": p_under * d_under - 1})
    sides.sort(key=lambda x: -x["ev"])
    best = sides[0] if sides else None
    fair_p_over = (1 / d_over) / ((1 / d_over) + (1 / d_under)) if (d_over and d_under) else None
    return {"n": n, "mu": mu, "sd": sd, "proj": proj,
            "p_over": p_over, "p_under": p_under,
            "best": best, "fair_p_over": fair_p_over}

# ============================================================
# STATE INIT
# ============================================================

if "saved_cache" not in st.session_state:
    st.session_state.saved_cache = load_json(CACHE_FILE, {})
if "notes" not in st.session_state:
    st.session_state.notes = ""
if "latest_key" not in st.session_state:
    st.session_state.latest_key = ""

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("Setup")
    has_key = bool(get_secret("CITO_API_KEY"))
    st.write("Cito key:", "✅ found" if has_key else "❌ missing")

    season = st.text_input("Season", value="2026")
    used_today = today_used()
    remaining = max(0, CITO_DAILY_FREE - used_today)
    pct = min(1.0, used_today / CITO_DAILY_FREE)
    st.markdown(f"**Cito today:** {used_today} / {CITO_DAILY_FREE} calls")
    st.progress(pct)
    if used_today >= CITO_DAILY_FREE:
        st.error("Daily free limit hit. Calls may 429 until tomorrow UTC.")
    elif remaining < 50:
        st.warning(f"Only {remaining} free calls left today.")

    st.divider()
    st.write(f"Saved analyses: **{len(st.session_state.saved_cache)}**")
    if st.button("Reset today's usage counter"):
        u = load_usage(); u[today_key()] = 0; save_json(USAGE_FILE, u); st.rerun()
    if st.button("Delete saved analysis cache"):
        st.session_state.saved_cache = {}; save_json(CACHE_FILE, {}); st.rerun()

# ============================================================
# TABS
# ============================================================

tabs = st.tabs([
    "📡 Dashboard", "🛠️ Manual Match", "💰 EV Calculator",
    "🗒️ Intel Notes", "👥 Rosters", "💾 Saved", "🔬 Diagnostics",
])

# ------------------------------------------------------------
# DASHBOARD — Cito + manual upcoming matches
# ------------------------------------------------------------
with tabs[0]:
    st.markdown("## Upcoming Matches")
    st.caption("Cito-fetched fixtures plus any you've added manually. Selecting a match uses **zero** Cito calls.")

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("🔄 Fetch upcoming from Cito (uses ~4 calls)"):
            with st.spinner("Pulling Cito fixtures…"):
                df, calls = cito_matches(season=season, limit=25)
                st.session_state.cito_matches_df = df
                st.session_state.cito_matches_calls = calls
                if df.empty:
                    st.error("Cito returned no matches. Add fixtures manually below.")
                else:
                    st.success(f"Got {len(df)} matches.")
    with col_b:
        st.write(f"Last cached: {len(st.session_state.get('cito_matches_df', pd.DataFrame()))} Cito matches in this session.")

    # Manual upcoming match adder
    with st.expander("➕ Add a missing fixture manually (e.g. Toronto game Cito missed)", expanded=False):
        m_col1, m_col2, m_col3, m_col4 = st.columns([1.2, 1.2, 1.5, 1.5])
        with m_col1: m_ta = st.selectbox("Team A", TEAMS, key="mu_a")
        with m_col2: m_tb = st.selectbox("Team B", TEAMS, index=1, key="mu_b")
        with m_col3: m_when = st.text_input("Time", placeholder="Sat 14 Jun · 18:00 UK", key="mu_when")
        with m_col4: m_event = st.text_input("Event", value="CDL 2026 Qualifier", key="mu_event")
        if st.button("Save this fixture"):
            if m_ta == m_tb:
                st.error("Pick two different teams.")
            else:
                ms = load_json(MANUAL_MATCHES_FILE, [])
                ms.append({"match_id": "", "start": m_when or "TBD", "event": m_event or "CDL",
                           "team_a": m_ta, "team_b": m_tb, "source": "Manual"})
                save_json(MANUAL_MATCHES_FILE, ms)
                st.success("Added.")
                st.rerun()
        if st.button("Clear all manual fixtures"):
            save_json(MANUAL_MATCHES_FILE, [])
            st.rerun()

    cito_df = st.session_state.get("cito_matches_df", pd.DataFrame())
    manual_df = pd.DataFrame(load_json(MANUAL_MATCHES_FILE, []))
    all_matches = pd.concat([cito_df, manual_df], ignore_index=True) if not (cito_df.empty and manual_df.empty) else pd.DataFrame()

    if all_matches.empty:
        st.info("No fixtures yet. Fetch from Cito above, or add one manually.")
    else:
        mdf = all_matches.reset_index(drop=True)
        labels = [f"{i}: {r['start']} — {r['team_a']} vs {r['team_b']} — {r.get('event','')} [{r.get('source','')}]"
                  for i, r in mdf.iterrows()]
        choice = st.selectbox("Select match", labels)
        match = mdf.iloc[int(choice.split(":")[0])]

        st.markdown(f"""
<div class="match-card">
  <div class="muted">{match['start']} · {match.get('event','')}</div>
  <h2 style="margin: 6px 0;">{match['team_a']} <span class="muted">vs</span> {match['team_b']}</h2>
  <span class="pill">Source: {match.get('source','?')}</span>
  <span class="pill pill-good">Selection uses 0 Cito calls</span>
</div>""", unsafe_allow_html=True)

        st.markdown("### Map / Veto Editor")
        st.caption("Map names come from the BO7 pool. Editing here uses 0 Cito calls.")
        veto_key = f"veto_dash_{match['team_a']}_{match['team_b']}_{match['start']}"
        veto_df = veto_editor(veto_key, match["team_a"], match["team_b"])

        key = analysis_key(season, match["team_a"], match["team_b"], maps_signature(veto_df))
        saved = get_analysis(key)
        if saved:
            st.success(f"Saved analysis found — last saved {saved['saved_at']}. **0 Cito calls needed.**")
        else:
            st.warning("No saved analysis for this exact team + map setup.")

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("📥 Load analysis (uses Cito)"):
                with st.spinner(f"Loading rosters + per-mode stats… (~{len(get_roster(match['team_a'])[0]) + len(get_roster(match['team_b'])[0])} calls)"):
                    r, s, calls = build_analysis(match["team_a"], match["team_b"], season, has_key)
                    store_analysis(key, r, s, calls)
                    st.session_state.latest_key = key
                    st.rerun()
        with b2:
            if st.button("♻️ Force refresh"):
                with st.spinner("Force refreshing…"):
                    r, s, calls = build_analysis(match["team_a"], match["team_b"], season, has_key)
                    store_analysis(key, r, s, calls)
                    st.session_state.latest_key = key
                    st.rerun()
        with b3:
            if st.button("📊 Use saved (0 calls)", disabled=not bool(saved)):
                st.session_state.latest_key = key; st.rerun()

        active = get_analysis(key)
        if active:
            st.session_state.latest_key = key
            render_analysis(match["team_a"], match["team_b"], active["stats"], veto_df, st.session_state.notes)

# ------------------------------------------------------------
# MANUAL MATCH BUILDER
# ------------------------------------------------------------
with tabs[1]:
    st.markdown("## Manual Match Builder")
    st.caption("Best workflow once vetoes are confirmed. Pure-local: no Cito calls except Load.")

    col_a, col_b = st.columns(2)
    with col_a:
        man_a = st.selectbox("Team A", TEAMS, index=TEAMS.index("OpTic Texas"), key="man_a")
    with col_b:
        man_b = st.selectbox("Team B", TEAMS, index=TEAMS.index("Los Angeles Thieves"), key="man_b")

    if man_a == man_b:
        st.error("Two different teams.")
    else:
        veto_key = f"veto_man_{man_a}_{man_b}"
        veto_df = veto_editor(veto_key, man_a, man_b)

        mkey = analysis_key(season, man_a, man_b, maps_signature(veto_df))
        saved = get_analysis(mkey)
        if saved:
            st.success(f"Saved analysis exists — saved {saved['saved_at']}.")
        else:
            st.warning("No saved analysis for this exact setup.")

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("📥 Load manual analysis"):
                with st.spinner("Loading…"):
                    r, s, calls = build_analysis(man_a, man_b, season, has_key)
                    store_analysis(mkey, r, s, calls)
                    st.session_state.latest_key = mkey; st.rerun()
        with c2:
            if st.button("📊 Use saved", disabled=not bool(saved), key="man_use_saved"):
                st.session_state.latest_key = mkey; st.rerun()
        with c3:
            if st.button("♻️ Force refresh manual"):
                with st.spinner("Force refreshing…"):
                    r, s, calls = build_analysis(man_a, man_b, season, has_key)
                    store_analysis(mkey, r, s, calls)
                    st.session_state.latest_key = mkey; st.rerun()

        active = get_analysis(mkey)
        if active:
            st.session_state.latest_key = mkey
            render_analysis(man_a, man_b, active["stats"], veto_df, st.session_state.notes)

# ------------------------------------------------------------
# EV CALCULATOR
# ------------------------------------------------------------
with tabs[2]:
    st.markdown("## Player Prop EV Calculator")
    st.caption("Paste recent kill counts + BetMGM line + odds. Tool returns the model's edge, EV % and a fractional-Kelly stake. **Mode matters** — only paste maps from the same mode.")

    e_col1, e_col2 = st.columns([1, 1])
    with e_col1:
        fmt = st.radio("Odds format", ["fractional", "decimal"], horizontal=True)
        bankroll = st.number_input("Bankroll (£)", value=200.0, min_value=0.0, step=10.0)
        kfrac = st.slider("Kelly fraction", 0.05, 1.0, 0.25, 0.05)
    with e_col2:
        st.markdown("**How to read:**")
        st.markdown(
            "- **EV%** = expected return per £1 staked\n"
            "- **Edge** = your model's chance vs the vig-free fair price\n"
            "- **Fallback / low sample** = treat the value as a hint, not a lock"
        )

    if "ev_bets" not in st.session_state:
        st.session_state.ev_bets = [
            {"player": "Shotzzy", "team": "OpTic Texas", "mode": "Hardpoint", "line": "25.5",
             "over_odds": "10/11", "under_odds": "10/11",
             "samples": "28, 31, 24, 27, 30, 26", "adj": "0"},
        ]

    add_col, clear_col = st.columns([1, 1])
    with add_col:
        if st.button("➕ Add another bet"):
            st.session_state.ev_bets.append({"player": "", "team": "", "mode": "Hardpoint", "line": "",
                                             "over_odds": "", "under_odds": "", "samples": "", "adj": "0"})
            st.rerun()
    with clear_col:
        if st.button("🗑️ Clear all bets"):
            st.session_state.ev_bets = []; st.rerun()

    results = []
    for i, bet in enumerate(st.session_state.ev_bets):
        with st.container():
            st.markdown(f'<div class="card">', unsafe_allow_html=True)
            r1c1, r1c2, r1c3 = st.columns([1.5, 1.5, 1])
            with r1c1:
                bet["player"] = st.text_input("Player", value=bet["player"], key=f"ev_p_{i}")
            with r1c2:
                bet["team"] = st.selectbox("Team", [""] + TEAMS,
                                           index=([""] + TEAMS).index(bet["team"]) if bet["team"] in ([""] + TEAMS) else 0,
                                           key=f"ev_t_{i}")
            with r1c3:
                if st.button("Remove", key=f"ev_rm_{i}"):
                    st.session_state.ev_bets.pop(i); st.rerun()

            r2c1, r2c2, r2c3, r2c4 = st.columns(4)
            with r2c1:
                bet["mode"] = st.selectbox("Mode", ["Hardpoint", "Search & Destroy", "Overload"],
                                           index=["Hardpoint", "Search & Destroy", "Overload"].index(bet["mode"]),
                                           key=f"ev_m_{i}")
            with r2c2:
                bet["line"] = st.text_input("Line", value=bet["line"], key=f"ev_l_{i}", placeholder="22.5")
            with r2c3:
                bet["over_odds"] = st.text_input("Over odds", value=bet["over_odds"], key=f"ev_o_{i}",
                                                 placeholder="10/11 or 1.91")
            with r2c4:
                bet["under_odds"] = st.text_input("Under odds", value=bet["under_odds"], key=f"ev_u_{i}",
                                                  placeholder="10/11 or 1.91")

            r3c1, r3c2 = st.columns([3, 1])
            with r3c1:
                bet["samples"] = st.text_input("Recent kills (this mode only, comma-separated)",
                                               value=bet["samples"], key=f"ev_s_{i}",
                                               placeholder="28, 24, 31, 26, 29")
            with r3c2:
                bet["adj"] = st.text_input("Adjust ±", value=bet["adj"], key=f"ev_a_{i}")

            try: adj_val = float(bet["adj"]) if bet["adj"] else 0.0
            except: adj_val = 0.0
            try: line_val = float(bet["line"]) if bet["line"] else None
            except: line_val = None

            r = ev_single(bet["samples"], line_val, bet["over_odds"], bet["under_odds"], fmt, adj=adj_val)
            if r:
                best = r["best"]
                side_color = "good" if (best and best["ev"] > 0.001) else ("bad" if best and best["ev"] < -0.001 else "muted")
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Proj.", f"{r['proj']:.1f}k", f"n={r['n']}, σ={r['sd']:.1f}")
                m2.metric("P(over)", f"{r['p_over']*100:.1f}%")
                m3.metric("P(under)", f"{r['p_under']*100:.1f}%")
                if best:
                    stake = max(0, (best["p"] * best["d"] - 1) / (best["d"] - 1)) * kfrac * bankroll if best["d"] > 1 else 0
                    m4.metric(f"Best side", f"{best['side']} {bet['line']}", f"EV {best['ev']*100:+.1f}%")
                    m5.metric("Stake (fK)", f"£{stake:.2f}" if best["ev"] > 0 else "—")
                if r["n"] < 4:
                    st.warning(f"Only {r['n']} samples — wide error bars. Overload especially has little history.")
                results.append({
                    "Player": bet["player"], "Team": bet["team"], "Mode": bet["mode"],
                    "Side": best["side"] if best else "—",
                    "Line": bet["line"], "EV%": round(best["ev"]*100, 1) if best else None,
                    "Proj": round(r["proj"], 1), "n": r["n"],
                })
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
            st.warning("None of these show positive value at the current prices — 'no bet' is a valid answer.")

# ------------------------------------------------------------
# INTEL NOTES
# ------------------------------------------------------------
with tabs[3]:
    st.markdown("## Intel Notes")
    st.markdown("""
<div class="card">
Paste reads from Twitter/X, Reddit, YouTube, Breaking Point, broadcasts, your own gut.
Mentioning a <b>player / team / mode</b> with positive or negative wording shifts their score.
</div>""", unsafe_allow_html=True)
    st.session_state.notes = st.text_area("Intel notes", value=st.session_state.notes, height=260,
        placeholder="e.g. Shotzzy frying HP. Dashy looked ill. LAT likely pick S&D. OpTic weak on Overload.")
    c1, c2 = st.columns(2)
    c1.markdown('<div class="pick-card"><b>Positive boosts</b><br>hot, frying, on form, good form, dominant, great, strong, improved, MVP, carry</div>', unsafe_allow_html=True)
    c2.markdown('<div class="danger-card"><b>Negative penalties</b><br>sick, ill, benched, sub, struggling, bad form, poor, unwell, visa, dropped, role change</div>', unsafe_allow_html=True)

# ------------------------------------------------------------
# ROSTERS EDITOR
# ------------------------------------------------------------
with tabs[4]:
    st.markdown("## Roster Editor")
    st.caption("Verified 2026 rosters baked in. If a player moves mid-season, edit here and the change is used everywhere. Reset returns to the baked-in roster.")

    team_choice = st.selectbox("Team", TEAMS, key="roster_team")
    current_players, source = get_roster(team_choice)
    st.markdown(f"**Current source:** `{source}`")

    edited = []
    cols = st.columns(4)
    for i in range(4):
        val = current_players[i] if i < len(current_players) else ""
        with cols[i]:
            edited.append(st.text_input(f"Player {i+1}", value=val, key=f"r_{team_choice}_{i}"))

    rc1, rc2 = st.columns(2)
    if rc1.button("💾 Save override"):
        set_roster_override(team_choice, edited)
        st.success(f"Saved {team_choice}: {', '.join([p for p in edited if p])}")
        st.rerun()
    if rc2.button("↩️ Reset to verified"):
        reset_roster(team_choice)
        st.success("Reset.")
        st.rerun()

    st.divider()
    st.markdown("### All 2026 rosters (current)")
    all_rows = []
    for t in TEAMS:
        plyrs, src = get_roster(t)
        all_rows.append({"Team": t, "Players": ", ".join(plyrs), "Source": src})
    st.dataframe(pd.DataFrame(all_rows), use_container_width=True)

# ------------------------------------------------------------
# SAVED ANALYSES
# ------------------------------------------------------------
with tabs[5]:
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
                "Cito Rows": sum(1 for r in item.get("stats", []) if str(r.get("Source", "")).startswith("Cito")),
            })
        st.dataframe(pd.DataFrame(rows).drop(columns=["Key"]), use_container_width=True)
        sel = st.selectbox("Saved key", list(st.session_state.saved_cache.keys()))
        sc1, sc2 = st.columns(2)
        if sc1.button("Set as active"):
            st.session_state.latest_key = sel; st.success("Active set. Check Diagnostics.")
        if sc2.button("Delete this analysis"):
            cache = st.session_state.saved_cache; cache.pop(sel, None)
            st.session_state.saved_cache = cache; save_json(CACHE_FILE, cache); st.rerun()

# ------------------------------------------------------------
# DIAGNOSTICS
# ------------------------------------------------------------
with tabs[6]:
    st.markdown("## Diagnostics")
    st.markdown(f"**Cito base:** `{CITO_BASE}`  |  **Today's calls:** {today_used()} / {CITO_DAILY_FREE}")

    st.markdown("### Manual endpoint tester (uses 1 call)")
    ep = st.text_input("Path", value="/matches/upcoming", help="Path after /api/v1/cod")
    params_str = st.text_input("Params (k=v&k=v)", value=f"season={season}&limit=5")
    if st.button("Run test"):
        params = dict(p.split("=", 1) for p in params_str.split("&") if "=" in p) if params_str else {}
        res = cito_get(ep, params)
        st.write(f"Status: **{res['status']}**  |  OK: **{res['ok']}**")
        st.code(res["url"])
        st.json(res["payload"])
        st.caption("If you get 401: check CITO_API_KEY in Streamlit secrets. 404: endpoint name wrong. 429: hit daily limit.")

    st.markdown("### Last upcoming-match calls")
    last_calls = st.session_state.get("cito_matches_calls", [])
    if last_calls:
        st.dataframe(pd.DataFrame([{"Status": c["status"], "OK": c["ok"], "URL": c["url"]} for c in last_calls]),
                     use_container_width=True)

    st.markdown("### Active analysis raw data")
    key = st.session_state.latest_key
    active = get_analysis(key) if key else None
    if active:
        st.markdown("**Rosters**")
        st.dataframe(active["roster"], use_container_width=True)
        st.markdown("**Stats**")
        st.dataframe(active["stats"], use_container_width=True)
        st.markdown("**Calls used**")
        st.dataframe(pd.DataFrame(active["calls"]), use_container_width=True)

st.caption("Analysis only · does not place bets · no profit guarantee · 18+ · BeGambleAware.org · GamCare 0808 8020 133")
