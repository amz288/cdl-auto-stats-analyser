import re
import math
from typing import Any, Dict, List, Tuple

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="CDL Analyst v6", layout="wide")
st.title("CDL Analyst v6")
st.caption("Cito + Breaking Point fallback + map veto updater. Analysis only, not guaranteed profit.")

CITO_ROOTS = ["https://api.citoapi.com/api/v1/cod", "https://api.citoapi.com/v1/cod"]
BP_MATCHES_URL = "https://breakingpoint.gg/matches"
BP_TEAMS_URL = "https://breakingpoint.gg/cdl/teams-and-players"
MODES = ["Hardpoint", "Search & Destroy", "Overload", "Hardpoint", "Search & Destroy"]

TEAMS = [
    "Boston Breach", "Carolina Royal Ravens", "Cloud9 New York", "FaZe Vegas",
    "G2 Minnesota", "Los Angeles Thieves", "Miami Heretics", "OpTic Texas",
    "Paris Gentle Mates", "Riyadh Falcons", "Toronto KOI", "Vancouver Surge",
]
SLUGS = {t: re.sub(r"[^a-z0-9-]", "", t.lower().replace("&", "and").replace(" ", "-")) for t in TEAMS}
SLUGS["FaZe Vegas"] = "faze-vegas"
SLUGS["OpTic Texas"] = "optic-texas"
SLUG_TO_TEAM = {v: k for k, v in SLUGS.items()}

PRIORS = {
    "Simp": [96, 97, 94], "Cellium": [94, 98, 93], "Scrap": [96, 92, 95],
    "HyDra": [96, 93, 95], "aBeZy": [95, 94, 93], "Shotzzy": [95, 93, 94],
    "Dashy": [92, 95, 91], "Kremp": [94, 91, 93], "JoeDeceives": [92, 94, 92],
    "Pred": [93, 91, 92], "Drazah": [91, 92, 90], "Abuzah": [90, 92, 90],
    "CleanX": [91, 89, 90], "Insight": [88, 93, 87], "Envoy": [91, 89, 90],
    "Skyz": [89, 92, 88], "Sib": [91, 88, 91], "Ghosty": [90, 90, 90],
    "KiSMET": [90, 88, 90], "Nero": [90, 87, 89], "Nastie": [89, 87, 88],
    "Huke": [89, 87, 88], "Neptune": [89, 86, 88], "Lurqxx": [89, 86, 88],
    "Standy": [88, 86, 87], "ReeaL": [88, 86, 87], "Lucky": [86, 88, 86],
    "Afro": [88, 85, 87], "Spart": [86, 86, 86], "Purj": [86, 84, 85],
    "Mamba": [86, 83, 85], "Lunarz": [85, 85, 85], "Atura": [84, 86, 84],
    "Craze": [85, 83, 84], "Wevy": [84, 84, 84], "Hide": [83, 85, 83],
    "Encourage": [85, 82, 84], "Nejra": [83, 83, 83], "Exceed": [84, 82, 83],
    "Fire": [83, 83, 83], "04": [84, 82, 83],
}

def safe(x: Any) -> str:
    return "" if x is None else str(x).strip()

def n(x: Any, default: float = 0.0) -> float:
    try:
        s = re.sub(r"[^0-9.\-]", "", safe(x))
        return float(s) if s not in ["", ".", "-"] else default
    except Exception:
        return default

def slug(x: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", safe(x).lower().replace("&", "and").replace(" ", "-"))

def norm_team(x: Any) -> str:
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

def mode_key(x: Any) -> str:
    m = safe(x).lower()
    if "search" in m or "snd" in m or "s&d" in m:
        return "snd"
    if "overload" in m or "ovl" in m:
        return "ovl"
    return "hp"

def pretty_mode(x: Any) -> str:
    return {"hp": "Hardpoint", "snd": "Search & Destroy", "ovl": "Overload"}[mode_key(x)]

def secret(name: str) -> str:
    try:
        return st.secrets.get(name, "")
    except Exception:
        return ""

def nested(d: Dict[str, Any], paths: List[str]) -> Any:
    for path in paths:
        cur = d
        ok = True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and safe(cur):
            return cur
    return ""

def data(payload: Any) -> Any:
    return payload.get("data", payload) if isinstance(payload, dict) else payload

def as_list(payload: Any) -> List[Any]:
    d = data(payload)
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ["players", "matches", "items", "results", "data"]:
            if isinstance(d.get(k), list):
                return d[k]
    return []

def cito_headers() -> Dict[str, str]:
    key = secret("CITO_API_KEY")
    h = {"accept": "application/json", "user-agent": "CDL-Analyst-v6"}
    if key:
        h["Authorization"] = f"Bearer {key}"
        h["x-api-key"] = key
    return h

@st.cache_data(ttl=900, show_spinner=False)
def cito_get(path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    attempts = []
    for root in CITO_ROOTS:
        url = root + path
        try:
            r = requests.get(url, headers=cito_headers(), params=params or {}, timeout=25)
            try:
                payload = r.json()
            except Exception:
                payload = {"raw_text": r.text[:1000]}
            res = {"ok": r.ok, "status": r.status_code, "url": r.url, "payload": payload}
            attempts.append(res)
            if r.ok:
                return res
        except Exception as e:
            attempts.append({"ok": False, "status": "ERR", "url": url, "payload": {"error": str(e)}})
    res = attempts[-1]
    res["attempts"] = attempts
    return res

@st.cache_data(ttl=900, show_spinner=True)
def load_cito_matches(season: str, limit: int) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    calls = [
        cito_get("/matches/upcoming", {"season": season, "limit": limit}),
        cito_get("/cdl/schedule", {"season": season, "limit": limit}),
    ]
    rows = []
    for call in calls:
        if not call["ok"]:
            continue
        for m in as_list(call["payload"]):
            if not isinstance(m, dict):
                continue
            a = norm_team(nested(m, ["team1.name", "teams.team1.name", "homeTeam.name", "teamA.name", "team1", "homeTeam", "team1.slug", "teams.team1.slug"]))
            b = norm_team(nested(m, ["team2.name", "teams.team2.name", "awayTeam.name", "teamB.name", "team2", "awayTeam", "team2.slug", "teams.team2.slug"]))
            blob = str(m)
            found = [t for t in TEAMS if t.lower() in blob.lower()]
            if not a and len(found) >= 1:
                a = found[0]
            if not b and len(found) >= 2:
                b = found[1]
            if not a or not b:
                continue
            rows.append({
                "match_id": safe(nested(m, ["matchId", "id", "bpMatchId"])),
                "start": safe(nested(m, ["startsAt", "startTime", "scheduledAt", "matchDate", "date"])),
                "event": safe(nested(m, ["event.name", "tournament.name", "event", "round", "stage.name"])) or "CDL",
                "team_a": a,
                "team_b": b,
                "status": safe(nested(m, ["status", "state"])),
                "source": call["url"],
            })
    return (pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()), calls

@st.cache_data(ttl=900, show_spinner=False)
def bp_text(url: str) -> str:
    r = requests.get(url, headers={"user-agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return "\n".join(x.strip() for x in soup.get_text("\n").splitlines() if x.strip())

@st.cache_data(ttl=900, show_spinner=False)
def load_bp_rosters() -> Dict[str, List[str]]:
    try:
        lines = bp_text(BP_TEAMS_URL).splitlines()
    except Exception:
        return {}
    rosters = {t: [] for t in TEAMS}
    active, current, collecting = False, "", False
    for line in lines:
        if line == "# CDL Teams":
            active = True
            continue
        if line == "# Players":
            break
        if not active:
            continue
        if line in TEAMS:
            current, collecting = line, False
            continue
        if current and line == "Players":
            collecting = True
            continue
        if current and collecting and 1 < len(line) < 26 and line.lower() not in ["players", "coach", "team stats", "matches", "news"]:
            if line not in rosters[current]:
                rosters[current].append(line)
    return {k: v for k, v in rosters.items() if v}

@st.cache_data(ttl=900, show_spinner=False)
def load_bp_matches() -> pd.DataFrame:
    try:
        text = " ".join(bp_text(BP_MATCHES_URL).splitlines())
    except Exception:
        return pd.DataFrame()
    alt = "|".join(map(re.escape, TEAMS))
    pat = rf"(~\d+\s+(?:hours?|days?))\s+(CDL\s+(?:Major|Minor|Champs)[^~]*?)\s+({alt}|TBD)\s+0\s+({alt}|TBD)\s+0"
    rows = [{"match_id": "", "start": m.group(1), "event": m.group(2), "team_a": m.group(3), "team_b": m.group(4), "status": "upcoming", "source": "Breaking Point fallback"} for m in re.finditer(pat, text)]
    return pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()

@st.cache_data(ttl=900, show_spinner=True)
def load_cito_roster(team: str) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    team_slug = SLUGS.get(team, slug(team))
    calls = [
        cito_get("/players", {"team": team_slug, "activeOnly": "true", "limit": 12}),
        cito_get("/players", {"team": team, "activeOnly": "true", "limit": 12}),
    ]
    rows = []
    for call in calls:
        if not call["ok"]:
            continue
        for p in as_list(call["payload"]):
            if not isinstance(p, dict):
                continue
            name = safe(nested(p, ["ign", "playerName", "gamertag", "handle", "name"]))
            pteam = norm_team(nested(p, ["currentTeam.name", "team.name", "teamName", "team", "currentTeam.slug", "team.slug"])) or team
            if name and norm_team(pteam) == team:
                rows.append({"Team": team, "Player": name, "Role": safe(nested(p, ["role", "position"])) or "Player", "Source": "Cito roster"})
        if rows:
            break
    return (pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()), calls

@st.cache_data(ttl=900, show_spinner=True)
def load_cito_player_stats(player: str, season: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    calls, tried = [], set()
    for candidate in [player, slug(player), player.lower()]:
        if not candidate or candidate in tried:
            continue
        tried.add(candidate)
        call = cito_get(f"/players/{candidate}/stats", {"season": season})
        calls.append(call)
        if call["ok"]:
            return call["payload"], calls
    return {}, calls

def fallback_rows(team: str, player: str) -> List[Dict[str, Any]]:
    hp, snd, ovl = PRIORS.get(player, [74, 74, 74])
    return [
        {"Team": team, "Player": player, "Mode": "Hardpoint", "Score": hp, "K/D": None, "KP10": None, "KPR": None, "Sample": 0, "Source": "Fallback profile"},
        {"Team": team, "Player": player, "Mode": "Search & Destroy", "Score": snd, "K/D": None, "KP10": None, "KPR": None, "Sample": 0, "Source": "Fallback profile"},
        {"Team": team, "Player": player, "Mode": "Overload", "Score": ovl, "K/D": None, "KP10": None, "KPR": None, "Sample": 0, "Source": "Fallback profile"},
    ]

def score_mode(mode: str, kd: float, kp10: float, dmg10: float, kpr: float, sample: int) -> float:
    if mode == "Search & Destroy":
        return 55 + kpr * 45 + (kd - 1) * 18 + min(sample, 30) * 0.15
    return 50 + kp10 * 1.75 + dmg10 / 180 + (kd - 1) * 16 + min(sample, 30) * 0.12

def parse_player_stats(player: str, team: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    d = data(payload)
    if not isinstance(d, dict):
        return []
    info = d.get("player", {}) if isinstance(d.get("player"), dict) else {}
    ign = safe(info.get("ign") or info.get("name") or player)
    by_mode = d.get("byMode", {}) if isinstance(d.get("byMode"), dict) else {}
    overall = d.get("overall", {}) if isinstance(d.get("overall"), dict) else {}
    keys = {
        "hardpoint": "Hardpoint", "hp": "Hardpoint",
        "searchAndDestroy": "Search & Destroy", "search_and_destroy": "Search & Destroy", "snd": "Search & Destroy",
        "overload": "Overload", "ovl": "Overload", "control": "Overload",
    }
    rows = []
    for raw, mode in keys.items():
        m = by_mode.get(raw)
        if not isinstance(m, dict):
            continue
        kd = n(m.get("kd"), n(overall.get("kd"), 1.0))
        kp10 = n(m.get("killsPer10"), 0)
        dmg10 = n(m.get("damagePer10"), 0)
        kpr = n(m.get("killsPerRound"), 0)
        sample = int(n(m.get("mapsPlayed") or m.get("matchesPlayed") or overall.get("matchesPlayed"), 0))
        rows.append({"Team": team, "Player": ign, "Mode": mode, "Score": round(score_mode(mode, kd, kp10, dmg10, kpr, sample), 2), "K/D": kd, "KP10": kp10, "KPR": kpr, "Sample": sample, "Source": "Cito player stats"})
    return rows

def intel(notes: str, player: str, team: str) -> float:
    t = safe(notes).lower()
    if not t or (player.lower() not in t and team.lower() not in t):
        return 0.0
    pos = ["hot", "frying", "on form", "good form", "dominant", "great", "strong", "improved", "mvp", "carry"]
    neg = ["sick", "ill", "benched", "sub", "struggling", "bad form", "poor", "unwell", "visa", "dropped", "role change"]
    return (2.5 if any(x in t for x in pos) else 0.0) - (3.5 if any(x in t for x in neg) else 0.0)

def team_model(stats: pd.DataFrame) -> pd.DataFrame:
    if stats.empty:
        return pd.DataFrame()
    out = stats.groupby("Team", as_index=False).agg(Players=("Player", "nunique"), AvgScore=("Score", "mean"), CitoRows=("Source", lambda s: int(sum(str(x).startswith("Cito") for x in s))))
    out["AvgScore"] = out["AvgScore"].round(2)
    return out.sort_values("AvgScore", ascending=False)

def winprob(a: str, b: str, model: pd.DataFrame) -> Tuple[float, float, float]:
    scores = dict(zip(model["Team"], model["AvgScore"])) if not model.empty else {}
    sa, sb = float(scores.get(a, 74)), float(scores.get(b, 74))
    p = 1 / (1 + math.exp(-(sa - sb) / 12))
    return round(p, 3), round(sa, 2), round(sb, 2)

def recs_for(match: pd.Series, stats: pd.DataFrame, veto: pd.DataFrame, notes: str) -> pd.DataFrame:
    lookup = {(r.Team, r.Player, r.Mode): r for _, r in stats.iterrows()}
    rows = []
    for _, p in stats[["Team", "Player"]].drop_duplicates().iterrows():
        team, player = p["Team"], p["Player"]
        if team not in [match["team_a"], match["team_b"]]:
            continue
        for _, vm in veto.iterrows():
            mode = pretty_mode(vm["Mode"])
            stat = lookup.get((team, player, mode))
            if stat is None:
                continue
            score = float(stat["Score"])
            if safe(vm["Picked By"]) == team:
                score += 1.25
            if safe(vm["Map Name"]):
                score += 0.4
            score += intel(notes, player, team)
            conf = "Medium/High" if str(stat["Source"]).startswith("Cito") else "Fallback"
            rows.append({"Team": team, "Player": player, "Map": int(vm["Map"]), "Mode": mode, "Map Name": safe(vm["Map Name"]), "Picked By": safe(vm["Picked By"]), "Score": round(score, 2), "Confidence": conf, "Source": stat["Source"], "Reason": f"{stat['Source']}; base {stat['Score']}; KD {stat['K/D']}; KP10 {stat['KP10']}; KPR {stat['KPR']}"})
    return pd.DataFrame(rows).sort_values(["Map", "Score"], ascending=[True, False]) if rows else pd.DataFrame()

with st.sidebar:
    st.header("Setup")
    has_key = bool(secret("CITO_API_KEY"))
    st.write("Cito key:", "✅ found" if has_key else "❌ missing")
    season = st.text_input("Season", value="2026")
    limit = st.slider("Upcoming match limit", 5, 30, 15)
    use_bp = st.checkbox("Use Breaking Point fallback", value=True)
    if st.button("Clear cache / refresh"):
        st.cache_data.clear()
        st.rerun()

if "notes" not in st.session_state:
    st.session_state["notes"] = ""

upcoming, match_calls = load_cito_matches(season, limit) if has_key else (pd.DataFrame(), [])
if upcoming.empty and use_bp:
    upcoming = load_bp_matches()
rosters_bp = load_bp_rosters() if use_bp else {}

tab1, tab2, tab3, tab4 = st.tabs(["Match Centre", "Loaded Data", "Intel Notes", "Diagnostics"])

with tab1:
    st.subheader("Match Centre")
    if upcoming.empty:
        st.error("No upcoming matches found.")
    else:
        dfm = upcoming.reset_index(drop=True)
        choice = st.selectbox("Select match", [f"{i}: {r.start} — {r.team_a} vs {r.team_b} — {r.event}" for i, r in dfm.iterrows()])
        idx = int(choice.split(":")[0])
        match = dfm.iloc[idx]
        a, b = match["team_a"], match["team_b"]
        st.markdown(f"### {a} vs {b}")
        roster_calls, stat_calls, stat_rows, roster_frames = [], [], [], []
        for team in [a, b]:
            roster, rcalls = load_cito_roster(team) if has_key else (pd.DataFrame(), [])
            roster_calls += rcalls
            if roster.empty and team in rosters_bp:
                roster = pd.DataFrame([{"Team": team, "Player": p, "Role": "Player", "Source": "Breaking Point fallback"} for p in rosters_bp[team]])
            roster_frames.append(roster)
            for _, rp in roster.iterrows():
                payload, pcalls = load_cito_player_stats(rp["Player"], season) if has_key else ({}, [])
                stat_calls += pcalls
                parsed = parse_player_stats(rp["Player"], team, payload)
                stat_rows += parsed if parsed else fallback_rows(team, rp["Player"])
        roster_df = pd.concat(roster_frames, ignore_index=True).drop_duplicates() if roster_frames else pd.DataFrame()
        stats_df = pd.DataFrame(stat_rows).drop_duplicates() if stat_rows else pd.DataFrame()
        model = team_model(stats_df)
        p, sa, sb = winprob(a, b, model)
        c1, c2, c3 = st.columns(3)
        c1.metric(a, f"{round(p*100)}%", f"score {sa}")
        c2.metric("Model stronger side", a if p >= 0.5 else b)
        c3.metric(b, f"{round((1-p)*100)}%", f"score {sb}")
        cito_rows = int(sum(str(x).startswith("Cito") for x in stats_df["Source"])) if not stats_df.empty else 0
        if cito_rows:
            st.success(f"Loaded {cito_rows} Cito stat rows.")
        else:
            st.warning("No Cito stat rows loaded for selected players. Using fallback profiles only. Check Diagnostics.")
        veto = st.data_editor(pd.DataFrame({"Map": [1,2,3,4,5], "Mode": MODES, "Map Name": ["","","","",""], "Picked By": ["","","","",""]}), use_container_width=True, num_rows="fixed", column_config={"Mode": st.column_config.SelectboxColumn("Mode", options=MODES), "Picked By": st.column_config.SelectboxColumn("Picked By", options=["", a, b, "League/Default"]),}, key=f"veto_{idx}")
        recs = recs_for(match, stats_df, veto, st.session_state["notes"])
        st.markdown("### Recommended player targets")
        if recs.empty:
            st.error("No recommendation rows built.")
        else:
            view = st.selectbox("View", ["Best 2 / 3 / 4", "Series Overall", "Avoid / Fallback"] + [f"Map {i} - {m}" for i, m in enumerate(MODES, start=1)])
            if view == "Best 2 / 3 / 4":
                overall = recs.groupby(["Team", "Player"], as_index=False).agg(Score=("Score", "mean"), BestMap=("Score", "max"), Source=("Source", lambda s: ", ".join(sorted(set(map(str, s))))))
                overall = overall.sort_values("Score", ascending=False)
                for nval in [2,3,4]:
                    st.markdown(f"#### Best {nval}")
                    st.write(", ".join([f"**{r.Player}** ({r.Team})" for _, r in overall.head(nval).iterrows()]))
                st.dataframe(overall, use_container_width=True)
            elif view == "Series Overall":
                overall = recs.groupby(["Team", "Player"], as_index=False).agg(Score=("Score", "mean"), Reason=("Reason", lambda x: "; ".join(sorted(set(x)))[:350]))
                st.dataframe(overall.sort_values("Score", ascending=False), use_container_width=True)
            elif view == "Avoid / Fallback":
                st.dataframe(recs[recs["Source"].astype(str).str.contains("Fallback", na=False)].sort_values("Score"), use_container_width=True)
            else:
                map_no = int(view.split()[1])
                st.dataframe(recs[recs["Map"] == map_no].sort_values("Score", ascending=False), use_container_width=True)
        st.session_state["roster_df"] = roster_df
        st.session_state["stats_df"] = stats_df
        st.session_state["calls"] = match_calls + roster_calls + stat_calls

with tab2:
    st.subheader("Loaded Data")
    st.markdown("### Rosters")
    st.dataframe(st.session_state.get("roster_df", pd.DataFrame()), use_container_width=True)
    st.markdown("### Player stats")
    st.dataframe(st.session_state.get("stats_df", pd.DataFrame()), use_container_width=True)

with tab3:
    st.subheader("Intel Notes")
    st.session_state["notes"] = st.text_area("Paste notes from Twitter/X, Reddit, YouTube, Breaking Point, analyst comments etc.", value=st.session_state["notes"], height=260)

with tab4:
    st.subheader("Diagnostics")
    st.write("v6 sends Cito auth as `Authorization: Bearer <key>` and also includes `x-api-key` as fallback.")
    rows = [{"Status": c.get("status"), "OK": c.get("ok"), "URL": c.get("url")} for c in st.session_state.get("calls", match_calls)]
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    endpoint = st.text_input("Manual Cito endpoint", value="/matches/upcoming")
    if st.button("Test endpoint"):
        res = cito_get(endpoint, {"season": season, "limit": 5} if "upcoming" in endpoint else {})
        st.write(f"Status: {res['status']} | OK: {res['ok']} | URL: {res['url']}")
        st.json(res["payload"])

st.caption("Use the Diagnostics tab if Cito rows do not load. If statuses are 401/403, regenerate the Cito key and update Streamlit Secrets.")
