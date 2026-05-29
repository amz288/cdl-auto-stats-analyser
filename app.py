import re
import math
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

CITO_BASE = "https://api.citoapi.com"
BP_BASE = "https://breakingpoint.gg"

BP_TEAMS_URL = "https://breakingpoint.gg/cdl/teams-and-players"
BP_MATCHES_URL = "https://breakingpoint.gg/matches"

MODE_ORDER = ["Hardpoint", "Search & Destroy", "Overload", "Hardpoint", "Search & Destroy"]

KNOWN_TEAMS = [
    "Boston Breach",
    "Carolina Royal Ravens",
    "Cloud9 New York",
    "FaZe Vegas",
    "G2 Minnesota",
    "Los Angeles Thieves",
    "Miami Heretics",
    "OpTic Texas",
    "Paris Gentle Mates",
    "Riyadh Falcons",
    "Toronto KOI",
    "Vancouver Surge",
]

# Fallback priors only used when Cito does not return enough player/map history.
# They stop the app being blank, but the app clearly marks this as lower-quality.
PLAYER_PRIORS = {
    "Simp": {"role": "SMG", "overall": 96, "hp": 96, "snd": 97, "ovl": 94},
    "Cellium": {"role": "AR", "overall": 96, "hp": 94, "snd": 98, "ovl": 93},
    "Scrap": {"role": "Flex", "overall": 95, "hp": 96, "snd": 92, "ovl": 95},
    "HyDra": {"role": "SMG", "overall": 95, "hp": 96, "snd": 93, "ovl": 95},
    "aBeZy": {"role": "SMG", "overall": 94, "hp": 95, "snd": 94, "ovl": 93},
    "Shotzzy": {"role": "SMG", "overall": 94, "hp": 95, "snd": 93, "ovl": 94},
    "Dashy": {"role": "AR", "overall": 93, "hp": 92, "snd": 95, "ovl": 91},
    "Kremp": {"role": "SMG", "overall": 93, "hp": 94, "snd": 91, "ovl": 93},
    "JoeDeceives": {"role": "SMG", "overall": 93, "hp": 92, "snd": 94, "ovl": 92},
    "Pred": {"role": "SMG", "overall": 92, "hp": 93, "snd": 91, "ovl": 92},
    "Drazah": {"role": "Flex", "overall": 91, "hp": 91, "snd": 92, "ovl": 90},
    "Abuzah": {"role": "AR", "overall": 91, "hp": 90, "snd": 92, "ovl": 90},
    "CleanX": {"role": "SMG", "overall": 90, "hp": 91, "snd": 89, "ovl": 90},
    "Insight": {"role": "AR", "overall": 90, "hp": 88, "snd": 93, "ovl": 87},
    "Envoy": {"role": "SMG", "overall": 90, "hp": 91, "snd": 89, "ovl": 90},
    "Skyz": {"role": "AR", "overall": 90, "hp": 89, "snd": 92, "ovl": 88},
    "Sib": {"role": "AR/Flex", "overall": 90, "hp": 91, "snd": 88, "ovl": 91},
    "Ghosty": {"role": "AR/Flex", "overall": 90, "hp": 90, "snd": 90, "ovl": 90},
    "KiSMET": {"role": "SMG", "overall": 89, "hp": 90, "snd": 88, "ovl": 90},
    "Nero": {"role": "SMG", "overall": 89, "hp": 90, "snd": 87, "ovl": 89},
    "Nastie": {"role": "Flex", "overall": 88, "hp": 89, "snd": 87, "ovl": 88},
    "Huke": {"role": "SMG", "overall": 88, "hp": 89, "snd": 87, "ovl": 88},
    "Neptune": {"role": "SMG", "overall": 88, "hp": 89, "snd": 86, "ovl": 88},
    "Lurqxx": {"role": "SMG", "overall": 88, "hp": 89, "snd": 86, "ovl": 88},
    "Standy": {"role": "SMG", "overall": 87, "hp": 88, "snd": 86, "ovl": 87},
    "ReeaL": {"role": "SMG", "overall": 87, "hp": 88, "snd": 86, "ovl": 87},
    "Lucky": {"role": "AR", "overall": 87, "hp": 86, "snd": 88, "ovl": 86},
    "Afro": {"role": "SMG", "overall": 87, "hp": 88, "snd": 85, "ovl": 87},
    "Spart": {"role": "AR/Flex", "overall": 86, "hp": 86, "snd": 86, "ovl": 86},
    "Purj": {"role": "SMG", "overall": 85, "hp": 86, "snd": 84, "ovl": 85},
    "Mamba": {"role": "SMG", "overall": 85, "hp": 86, "snd": 83, "ovl": 85},
    "Lunarz": {"role": "Flex", "overall": 85, "hp": 85, "snd": 85, "ovl": 85},
    "Atura": {"role": "AR", "overall": 85, "hp": 84, "snd": 86, "ovl": 84},
    "Craze": {"role": "SMG", "overall": 84, "hp": 85, "snd": 83, "ovl": 84},
    "Wevy": {"role": "Flex", "overall": 84, "hp": 84, "snd": 84, "ovl": 84},
    "Hide": {"role": "AR", "overall": 84, "hp": 83, "snd": 85, "ovl": 83},
    "Encourage": {"role": "SMG", "overall": 84, "hp": 85, "snd": 82, "ovl": 84},
    "Nejra": {"role": "Flex", "overall": 83, "hp": 83, "snd": 83, "ovl": 83},
    "Exceed": {"role": "SMG", "overall": 83, "hp": 84, "snd": 82, "ovl": 83},
    "Fire": {"role": "AR/Flex", "overall": 83, "hp": 83, "snd": 83, "ovl": 83},
    "04": {"role": "SMG", "overall": 83, "hp": 84, "snd": 82, "ovl": 83},
    "Kips": {"role": "Flex", "overall": 82, "hp": 82, "snd": 82, "ovl": 82},
    "Nium": {"role": "Flex", "overall": 82, "hp": 82, "snd": 82, "ovl": 82},
}


# ============================================================
# STREAMLIT SETUP
# ============================================================

st.set_page_config(page_title="CDL Cito Hybrid v4", layout="wide")
st.title("CDL Cito Hybrid v4")
st.caption("Cito stats + Breaking Point fallback + manual veto updater + optional social/news intel. Analysis only — no guaranteed profit.")


# ============================================================
# GENERIC HELPERS
# ============================================================

def get_secret_key() -> str:
    try:
        return st.secrets.get("CITO_API_KEY", "")
    except Exception:
        return ""


def safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def as_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        cleaned = re.sub(r"[^0-9.\-]", "", str(x))
        if cleaned in ["", ".", "-"]:
            return None
        return float(cleaned)
    except Exception:
        return None


def flatten_dict(d: Dict[str, Any], parent: str = "", sep: str = ".") -> Dict[str, Any]:
    items = {}
    for k, v in d.items():
        nk = f"{parent}{sep}{k}" if parent else str(k)
        if isinstance(v, dict):
            items.update(flatten_dict(v, nk, sep=sep))
        else:
            items[nk] = v
    return items


def find_lists_of_dicts(obj: Any, path: str = "") -> List[Tuple[str, List[Dict[str, Any]]]]:
    found = []
    if isinstance(obj, list):
        dicts = [x for x in obj if isinstance(x, dict)]
        if dicts:
            found.append((path or "root", dicts))
        for i, x in enumerate(obj[:20]):
            found.extend(find_lists_of_dicts(x, f"{path}[{i}]"))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            found.extend(find_lists_of_dicts(v, f"{path}.{k}" if path else str(k)))
    return found


def records_to_df(records: List[Dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame([flatten_dict(r) for r in records])


def first_existing(row: pd.Series, names: List[str]) -> Any:
    for name in names:
        if name in row and pd.notna(row[name]) and safe_str(row[name]) != "":
            return row[name]
    # Fuzzy fallback
    lower_map = {str(c).lower(): c for c in row.index}
    for name in names:
        n = name.lower()
        for lc, original in lower_map.items():
            if lc.endswith(n) or n in lc:
                val = row[original]
                if pd.notna(val) and safe_str(val) != "":
                    return val
    return ""


def normalise_team_name(name: Any) -> str:
    s = safe_str(name)
    if not s:
        return ""
    for team in KNOWN_TEAMS:
        if s.lower() == team.lower() or team.lower() in s.lower() or s.lower() in team.lower():
            return team
    return s


def mode_key(mode: str) -> str:
    m = safe_str(mode).lower()
    if "search" in m or "snd" in m or "s&d" in m:
        return "snd"
    if "overload" in m or "ovl" in m:
        return "ovl"
    return "hp"


def pretty_mode(mode: str) -> str:
    mk = mode_key(mode)
    return {"hp": "Hardpoint", "snd": "Search & Destroy", "ovl": "Overload"}[mk]


# ============================================================
# CITO CLIENT
# ============================================================

def cito_headers() -> Dict[str, str]:
    key = get_secret_key()
    headers = {
        "accept": "application/json",
        "user-agent": "CDL-Cito-Hybrid-v4",
    }
    if key:
        headers["x-api-key"] = key
    return headers


@st.cache_data(ttl=900, show_spinner=False)
def cito_get(endpoint: str) -> Dict[str, Any]:
    url = endpoint if endpoint.startswith("http") else f"{CITO_BASE}{endpoint}"
    r = requests.get(url, headers=cito_headers(), timeout=25)
    payload = None
    try:
        payload = r.json()
    except Exception:
        payload = {"raw_text": r.text[:1000]}
    return {
        "ok": r.ok,
        "status": r.status_code,
        "url": url,
        "payload": payload,
    }


def cito_endpoint_candidates() -> Dict[str, List[str]]:
    return {
        "schedule": [
            "/api/v1/cod/cdl/schedule",
            "/api/v1/cod/matches/upcoming",
            "/api/v1/cod/matches/schedule",
        ],
        "live": [
            "/api/v1/cod/matches/live",
            "/api/v1/cod/cdl/live",
        ],
        "standings": [
            "/api/v1/cod/cdl/standings",
        ],
        "teams": [
            "/api/v1/cod/teams",
            "/api/v1/cod/cdl/teams",
        ],
        "players": [
            "/api/v1/cod/players",
            "/api/v1/cod/cdl/players",
        ],
    }


@st.cache_data(ttl=900, show_spinner=True)
def load_cito_bundle() -> Dict[str, Any]:
    out = {}
    for group, endpoints in cito_endpoint_candidates().items():
        group_results = []
        for ep in endpoints:
            res = cito_get(ep)
            group_results.append(res)
            if res["ok"]:
                # Stop after first working endpoint per group to save calls.
                break
        out[group] = group_results
    return out


def best_payload(bundle: Dict[str, Any], group: str) -> Any:
    for res in bundle.get(group, []):
        if res.get("ok"):
            return res.get("payload")
    return None


def extract_match_records(payload: Any) -> pd.DataFrame:
    lists = find_lists_of_dicts(payload)
    best_df = pd.DataFrame()
    best_score = -1

    for path, records in lists:
        df = records_to_df(records)
        if df.empty:
            continue
        cols = " ".join(df.columns).lower()
        score = 0
        if "match" in cols or "fixture" in cols:
            score += 5
        if "team" in cols:
            score += 5
        if "start" in cols or "date" in cols or "time" in cols:
            score += 3
        if "status" in cols:
            score += 2
        score += min(len(df), 50) / 10

        if score > best_score:
            best_score = score
            best_df = df.copy()

    if best_df.empty:
        return pd.DataFrame()

    rows = []
    for _, r in best_df.iterrows():
        match_id = first_existing(r, ["id", "matchId", "match_id", "match.id", "slug"])
        team_a = first_existing(r, [
            "teamA.name", "team1.name", "homeTeam.name", "home.name",
            "teams.0.name", "teamA", "team1", "homeTeam"
        ])
        team_b = first_existing(r, [
            "teamB.name", "team2.name", "awayTeam.name", "away.name",
            "teams.1.name", "teamB", "team2", "awayTeam"
        ])
        # If team fields are awkward, try to scan all values.
        joined_vals = " | ".join([safe_str(v) for v in r.values])
        found_teams = []
        for t in KNOWN_TEAMS:
            if t.lower() in joined_vals.lower():
                found_teams.append(t)
        if not team_a and len(found_teams) >= 1:
            team_a = found_teams[0]
        if not team_b and len(found_teams) >= 2:
            team_b = found_teams[1]

        status = first_existing(r, ["status", "state", "matchStatus"])
        start = first_existing(r, ["startTime", "start_time", "date", "scheduledAt", "scheduled_at", "time"])
        event = first_existing(r, ["event.name", "tournament.name", "stage.name", "event", "tournament"])

        if team_a or team_b or match_id:
            rows.append({
                "match_id": safe_str(match_id),
                "start": safe_str(start),
                "event": safe_str(event),
                "team_a": normalise_team_name(team_a),
                "team_b": normalise_team_name(team_b),
                "status": safe_str(status),
                "raw": dict(r),
            })

    out = pd.DataFrame(rows).drop_duplicates(subset=["match_id", "team_a", "team_b", "start"])
    return out


def extract_roster_records(payload: Any) -> pd.DataFrame:
    lists = find_lists_of_dicts(payload)
    rows = []

    for path, records in lists:
        df = records_to_df(records)
        if df.empty:
            continue
        cols = " ".join(df.columns).lower()
        if "player" not in cols and "team" not in cols and "roster" not in cols:
            continue

        for _, r in df.iterrows():
            player = first_existing(r, ["player.name", "name", "gamertag", "handle", "player"])
            team = first_existing(r, ["team.name", "currentTeam.name", "team", "organization.name"])
            role = first_existing(r, ["role", "position"])
            if player and team:
                rows.append({
                    "Team": normalise_team_name(team),
                    "Player": safe_str(player),
                    "Role": safe_str(role) or profile_for(player)["role"],
                    "Source": "Cito",
                })

    return pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()


def cito_match_stat_endpoints(match_id: str) -> List[str]:
    return [
        f"/api/v1/cod/matches/{match_id}/player-stats?includeMaps=true",
        f"/api/v1/cod/matches/{match_id}/maps",
    ]


@st.cache_data(ttl=900, show_spinner=False)
def load_match_deep_stats(match_id: str) -> Dict[str, Any]:
    out = {}
    if not match_id:
        return out
    for ep in cito_match_stat_endpoints(match_id):
        out[ep] = cito_get(ep)
    return out


def extract_player_stats_from_payloads(payloads: List[Any]) -> pd.DataFrame:
    rows = []

    for payload in payloads:
        for path, records in find_lists_of_dicts(payload):
            df = records_to_df(records)
            if df.empty:
                continue

            cols = " ".join(df.columns).lower()
            if not any(x in cols for x in ["player", "kills", "damage", "deaths", "kd", "k/d"]):
                continue

            for _, r in df.iterrows():
                player = first_existing(r, ["player.name", "player", "name", "gamertag", "handle"])
                team = first_existing(r, ["team.name", "team", "teamName"])
                mode = first_existing(r, ["mode", "gameMode", "map.mode", "mapMode"])
                map_no = first_existing(r, ["mapNumber", "map_number", "gameNumber", "game", "map"])
                map_name = first_existing(r, ["mapName", "map.name", "map_name"])

                kills = first_existing(r, ["kills", "stat.kills", "stats.kills", "k"])
                deaths = first_existing(r, ["deaths", "stat.deaths", "stats.deaths", "d"])
                damage = first_existing(r, ["damage", "dmg", "stat.damage", "stats.damage"])

                if player or kills or damage:
                    rows.append({
                        "Team": normalise_team_name(team),
                        "Player": safe_str(player),
                        "Mode": pretty_mode(mode) if mode else "",
                        "Map": safe_str(map_no),
                        "Map Name": safe_str(map_name),
                        "Kills": as_float(kills),
                        "Deaths": as_float(deaths),
                        "Damage": as_float(damage),
                        "Source Path": path,
                    })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.drop_duplicates()
    return out


# ============================================================
# BREAKING POINT FALLBACK
# ============================================================

@st.cache_data(ttl=900, show_spinner=False)
def fetch_bp_text(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 CDL analyser",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return "\n".join([x.strip() for x in soup.get_text("\n").splitlines() if x.strip()])


def parse_bp_rosters(text: str) -> Dict[str, List[str]]:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    rosters = {t: [] for t in KNOWN_TEAMS}

    in_team_section = False
    current = None
    collecting_players = False

    for line in lines:
        if line == "# CDL Teams":
            in_team_section = True
            continue
        if line == "# Players":
            break
        if not in_team_section:
            continue
        if line in KNOWN_TEAMS:
            current = line
            collecting_players = False
            continue
        if current and line == "Players":
            collecting_players = True
            continue
        if current and collecting_players:
            if line in KNOWN_TEAMS:
                current = line
                collecting_players = False
                continue
            if len(line) > 24 or line.lower() in ["players", "coach", "team stats", "matches", "cards", "events", "news"]:
                continue
            if re.search(r"[A-Za-z0-9]", line) and line not in rosters[current]:
                rosters[current].append(line)

    return {k: v for k, v in rosters.items() if v}


def parse_bp_matches(text: str) -> pd.DataFrame:
    compact = re.sub(r"\s+", " ", text)
    team_alt = "|".join(map(re.escape, KNOWN_TEAMS))
    pattern = rf"(~\d+\s+(?:hours?|days?))\s+(CDL\s+(?:Major|Minor|Champs)[^~]*?)\s+({team_alt}|TBD)\s+0\s+({team_alt}|TBD)\s+0"

    rows = []
    seen = set()
    for m in re.finditer(pattern, compact):
        eta, event, a, b = m.groups()
        event = re.sub(r"\s+", " ", event).strip()
        for team in KNOWN_TEAMS + ["TBD"]:
            event = event.replace(team, "").strip()
        key = (eta, event, a, b)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "match_id": "",
            "start": eta,
            "event": event or "CDL Match",
            "team_a": a,
            "team_b": b,
            "status": "upcoming",
            "raw": {},
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=900, show_spinner=True)
def load_breakingpoint_bundle() -> Dict[str, Any]:
    out = {}
    try:
        teams_text = fetch_bp_text(BP_TEAMS_URL)
        out["rosters"] = parse_bp_rosters(teams_text)
        out["teams_text"] = teams_text
    except Exception as e:
        out["rosters"] = {}
        out["teams_error"] = str(e)

    try:
        matches_text = fetch_bp_text(BP_MATCHES_URL)
        out["matches"] = parse_bp_matches(matches_text)
        out["matches_text"] = matches_text
    except Exception as e:
        out["matches"] = pd.DataFrame()
        out["matches_error"] = str(e)

    return out


# ============================================================
# MODEL ENGINE
# ============================================================

def profile_for(player: str) -> dict:
    p = safe_str(player)
    if p in PLAYER_PRIORS:
        return PLAYER_PRIORS[p]
    # Loose case-insensitive match
    for k, v in PLAYER_PRIORS.items():
        if k.lower() == p.lower():
            return v
    return {"role": "Unknown", "overall": 76, "hp": 76, "snd": 76, "ovl": 76}


def build_roster_map(cito_rosters: pd.DataFrame, bp_rosters: Dict[str, List[str]]) -> Dict[str, List[str]]:
    roster_map = {}
    if not cito_rosters.empty:
        for team, sub in cito_rosters.groupby("Team"):
            roster_map[team] = sorted([p for p in sub["Player"].dropna().astype(str).unique() if p])
    for team, players in bp_rosters.items():
        if team not in roster_map or len(roster_map.get(team, [])) < 4:
            roster_map[team] = players
    return roster_map


def build_team_strength(roster_map: Dict[str, List[str]], stat_summary: pd.DataFrame = pd.DataFrame()) -> pd.DataFrame:
    rows = []
    stat_scores = {}
    if not stat_summary.empty:
        for _, r in stat_summary.iterrows():
            key = (r["Team"], r["Player"])
            stat_scores[key] = r.get("Stat Score", None)

    for team, players in roster_map.items():
        scores = []
        data_points = 0
        for p in players:
            s = stat_scores.get((team, p))
            if s is not None and pd.notna(s):
                scores.append(float(s))
                data_points += 1
            else:
                scores.append(float(profile_for(p)["overall"]))
        if not scores:
            continue
        rows.append({
            "Team": team,
            "Players": len(players),
            "Cito Stat Players": data_points,
            "Team Score": round(sum(scores) / len(scores), 2),
            "Data Quality": "High" if data_points >= 3 else "Medium" if data_points >= 1 else "Fallback",
        })
    return pd.DataFrame(rows).sort_values("Team Score", ascending=False)


def summarise_player_stats(stats: pd.DataFrame) -> pd.DataFrame:
    if stats.empty or "Player" not in stats.columns:
        return pd.DataFrame()

    df = stats.copy()
    df["Kills"] = pd.to_numeric(df["Kills"], errors="coerce")
    df["Damage"] = pd.to_numeric(df["Damage"], errors="coerce")
    df["Deaths"] = pd.to_numeric(df["Deaths"], errors="coerce")
    df["Mode"] = df["Mode"].replace("", "Unknown")

    grouped = df.groupby(["Team", "Player", "Mode"], dropna=False).agg(
        Maps=("Kills", "count"),
        Avg_Kills=("Kills", "mean"),
        Max_Kills=("Kills", "max"),
        Avg_Damage=("Damage", "mean"),
        Avg_Deaths=("Deaths", "mean"),
    ).reset_index()

    # Create mode-normalised score. Kill sample is more important than generic seeded prior.
    grouped["Mode Score"] = (
        grouped["Avg_Kills"].fillna(0) * 3.2
        + grouped["Avg_Damage"].fillna(0) / 250
        - grouped["Avg_Deaths"].fillna(0) * 0.7
        + grouped["Maps"].clip(upper=10) * 0.6
    ).round(2)

    overall = grouped.groupby(["Team", "Player"], as_index=False).agg(
        Stat_Maps=("Maps", "sum"),
        Avg_Kills=("Avg_Kills", "mean"),
        Stat_Score=("Mode Score", "mean"),
    )
    overall = overall.rename(columns={"Stat_Score": "Stat Score"})
    return grouped, overall


def intel_adjustments(text: str, players: List[str], teams: List[str]) -> Dict[str, float]:
    """
    Lightweight deterministic notes engine.
    User can paste tweets/reddit/youtube notes. This is not web scraping.
    """
    txt = safe_str(text).lower()
    adjustments = {}

    positive_words = ["hot", "frying", "on form", "good form", "dominant", "great", "strong", "mvp", "carry", "improved", "role suits"]
    negative_words = ["sick", "ill", "benched", "sub", "struggling", "bad form", "poor", "role change", "unwell", "visa", "dropped", "weak"]

    for entity in players + teams:
        if not entity:
            continue
        e = entity.lower()
        if e not in txt:
            continue
        adj = 0.0
        window = txt[max(0, txt.find(e)-160): txt.find(e)+220]
        if any(w in window for w in positive_words):
            adj += 2.5
        if any(w in window for w in negative_words):
            adj -= 3.5
        if "snd" in window or "search" in window:
            adj += 0.4
        if "hardpoint" in window or "hp" in window:
            adj += 0.4
        if "overload" in window or "ovl" in window:
            adj += 0.4
        if adj:
            adjustments[entity] = adj
    return adjustments


def recommend_players(match: pd.Series, roster_map: Dict[str, List[str]], veto_df: pd.DataFrame, stat_mode_summary: pd.DataFrame, intel_text: str) -> pd.DataFrame:
    team_a = match["team_a"]
    team_b = match["team_b"]
    teams = [team_a, team_b]
    all_players = []
    for t in teams:
        all_players.extend(roster_map.get(t, []))

    adjs = intel_adjustments(intel_text, all_players, teams)

    # Lookup Cito stat scores by player/team/mode if available.
    stat_lookup = {}
    if not stat_mode_summary.empty:
        for _, r in stat_mode_summary.iterrows():
            stat_lookup[(r["Team"], r["Player"], pretty_mode(r["Mode"]))] = float(r["Mode Score"])

    rows = []
    for team in teams:
        for player in roster_map.get(team, []):
            prof = profile_for(player)
            for map_no, fixed_mode in enumerate(MODE_ORDER, start=1):
                veto_row = veto_df[veto_df["Map"] == map_no].iloc[0]
                mode = pretty_mode(veto_row["Mode"] or fixed_mode)
                mk = mode_key(mode)
                cito_score = stat_lookup.get((team, player, mode))

                if cito_score is not None:
                    # Convert observed stat score into same rough rating band.
                    base = 70 + cito_score
                    source = "Cito player/map stats"
                else:
                    base = prof.get(mk, prof.get("overall", 76))
                    source = "Fallback profile + roster"

                role = prof.get("role", "Unknown")
                score = float(base)

                # Mode role adjustments
                role_l = role.lower()
                if mode == "Hardpoint" and "smg" in role_l:
                    score += 1.8
                elif mode == "Search & Destroy" and "ar" in role_l:
                    score += 1.6
                elif mode == "Overload" and ("smg" in role_l or "flex" in role_l):
                    score += 1.4

                # Map/pick adjustments
                picked_by = safe_str(veto_row["Picked By"])
                if picked_by == team:
                    score += 1.2
                if safe_str(veto_row["Map Name"]):
                    score += 0.4

                # Intel adjustments
                score += adjs.get(player, 0)
                score += adjs.get(team, 0) * 0.45

                # Confidence/data quality
                if cito_score is not None and safe_str(veto_row["Map Name"]):
                    confidence = "High"
                elif cito_score is not None:
                    confidence = "Medium/High"
                elif player in PLAYER_PRIORS and safe_str(veto_row["Map Name"]):
                    confidence = "Medium"
                elif player in PLAYER_PRIORS:
                    confidence = "Low/Medium"
                else:
                    confidence = "Low"

                rows.append({
                    "Team": team,
                    "Player": player,
                    "Role": role,
                    "Map": map_no,
                    "Mode": mode,
                    "Map Name": safe_str(veto_row["Map Name"]),
                    "Picked By": picked_by,
                    "Score": round(score, 2),
                    "Confidence": confidence,
                    "Data Source": source,
                    "Reason": build_reason(player, team, mode, source, picked_by, adjs),
                })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["Map", "Score"], ascending=[True, False])


def build_reason(player: str, team: str, mode: str, source: str, picked_by: str, adjs: Dict[str, float]) -> str:
    bits = []
    if "Cito" in source:
        bits.append("uses Cito map/player stat data")
    else:
        bits.append("uses fallback strength profile")
    bits.append(f"{mode} role fit")
    if picked_by == team:
        bits.append("team map-pick boost")
    if player in adjs:
        bits.append(f"intel adjustment {adjs[player]:+0.1f}")
    if team in adjs:
        bits.append(f"team intel adjustment {adjs[team]:+0.1f}")
    return "; ".join(bits)


def win_prob(team_a: str, team_b: str, team_df: pd.DataFrame) -> Tuple[float, float, float]:
    scores = dict(zip(team_df["Team"], team_df["Team Score"])) if not team_df.empty else {}
    a = float(scores.get(team_a, 76))
    b = float(scores.get(team_b, 76))
    p = 1 / (1 + math.exp(-(a - b) / 6))
    return round(p, 3), a, b


# ============================================================
# LOAD DATA
# ============================================================

with st.sidebar:
    st.header("Setup")
    has_key = bool(get_secret_key())
    st.write("Cito key:", "✅ Found in Streamlit Secrets" if has_key else "❌ Not found")
    if st.button("Refresh all cached data"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Refresh uses API calls. Free Cito is limited, so avoid spamming refresh.")

    st.header("Model")
    recent_match_limit = st.slider("Recent completed matches to inspect", 2, 12, 6)
    st.caption("Higher = better stats but more API calls.")

cito_bundle = load_cito_bundle() if has_key else {}
bp_bundle = load_breakingpoint_bundle()

cito_schedule = extract_match_records(best_payload(cito_bundle, "schedule")) if has_key else pd.DataFrame()
cito_live = extract_match_records(best_payload(cito_bundle, "live")) if has_key else pd.DataFrame()
cito_teams = extract_roster_records(best_payload(cito_bundle, "teams")) if has_key else pd.DataFrame()
cito_players = extract_roster_records(best_payload(cito_bundle, "players")) if has_key else pd.DataFrame()

matches = pd.concat([cito_live, cito_schedule, bp_bundle.get("matches", pd.DataFrame())], ignore_index=True)
if not matches.empty:
    matches = matches.drop_duplicates(subset=["match_id", "team_a", "team_b", "start"], keep="first")
    matches = matches[(matches["team_a"].astype(str) != "") | (matches["team_b"].astype(str) != "")]

cito_rosters = pd.concat([cito_teams, cito_players], ignore_index=True).drop_duplicates() if (not cito_teams.empty or not cito_players.empty) else pd.DataFrame()
roster_map = build_roster_map(cito_rosters, bp_bundle.get("rosters", {}))


# ============================================================
# UI TABS
# ============================================================

tabs = st.tabs(["Match Centre", "Cito API Data", "Rosters", "Social/Intel Notes", "Debug"])

if "intel_notes" not in st.session_state:
    st.session_state["intel_notes"] = ""

with tabs[0]:
    st.subheader("Match Centre")

    if matches.empty:
        st.error("No matches found from Cito or Breaking Point.")
    else:
        labels = []
        for i, r in matches.reset_index(drop=True).iterrows():
            mid = r["match_id"] or "no-id"
            labels.append(f"{i}: {r['start']} — {r['team_a']} vs {r['team_b']} — {r['event']} — {mid}")

        selected = st.selectbox("Select match", labels)
        idx = int(selected.split(":")[0])
        match = matches.reset_index(drop=True).iloc[idx]

        st.write(f"**Selected:** {match['team_a']} vs {match['team_b']}")
        st.caption(f"Match ID: `{match['match_id'] or 'No Cito match ID found — fallback mode only'}`")

        # Load selected match deep stats
        deep_stats_df = pd.DataFrame()
        map_payload_debug = {}
        if match["match_id"]:
            if st.button("Load Cito player/map stats for this match"):
                st.session_state[f"deep_{match['match_id']}"] = load_match_deep_stats(match["match_id"])

            if f"deep_{match['match_id']}" in st.session_state:
                map_payload_debug = st.session_state[f"deep_{match['match_id']}"]
                payloads = [x["payload"] for x in map_payload_debug.values() if x.get("ok")]
                deep_stats_df = extract_player_stats_from_payloads(payloads)

        if deep_stats_df.empty:
            st.info("No selected-match Cito player/map stats loaded yet, or the match is upcoming and has no stat rows. The app will use recent/API/fallback profiles.")
            stat_mode_summary = pd.DataFrame()
            stat_overall_summary = pd.DataFrame()
        else:
            stat_mode_summary, stat_overall_summary = summarise_player_stats(deep_stats_df)
            st.success(f"Cito stat rows loaded: {len(deep_stats_df)}")

        team_df = build_team_strength(roster_map, stat_overall_summary if not deep_stats_df.empty else pd.DataFrame())
        p_a, a_score, b_score = win_prob(match["team_a"], match["team_b"], team_df)

        c1, c2, c3 = st.columns(3)
        c1.metric(match["team_a"], f"{round(p_a*100)}%", f"score {a_score}")
        c2.metric("Model stronger side", match["team_a"] if p_a >= 0.5 else match["team_b"])
        c3.metric(match["team_b"], f"{round((1-p_a)*100)}%", f"score {b_score}")

        st.markdown("### Map veto / picks")
        st.write("When vetoes/maps come out, type the map names and who picked them. Recommendations update immediately.")

        default_veto = pd.DataFrame({
            "Map": [1, 2, 3, 4, 5],
            "Mode": MODE_ORDER,
            "Map Name": ["", "", "", "", ""],
            "Picked By": ["", "", "", "", ""],
            "Confidence Note": ["Unknown map", "Unknown map", "Unknown map", "If needed", "If needed"],
        })

        veto = st.data_editor(
            default_veto,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "Picked By": st.column_config.SelectboxColumn(
                    "Picked By",
                    options=["", match["team_a"], match["team_b"], "League/Default"],
                ),
                "Mode": st.column_config.SelectboxColumn(
                    "Mode",
                    options=MODE_ORDER,
                )
            },
            key=f"veto_{idx}",
        )

        recs = recommend_players(match, roster_map, veto, stat_mode_summary, st.session_state.get("intel_notes", ""))

        st.markdown("### Recommended player targets")
        if recs.empty:
            st.warning("No players found for selected teams.")
        else:
            map_choice = st.selectbox(
                "View",
                ["Series Overall", "Best 2 / 3 / 4", "Avoid / Low Confidence"] + [f"Map {i} - {m}" for i, m in enumerate(MODE_ORDER, start=1)]
            )

            if map_choice == "Series Overall":
                overall = recs.groupby(["Team", "Player", "Role", "Confidence", "Data Source"], as_index=False).agg(
                    Avg_Score=("Score", "mean"),
                    Best_Score=("Score", "max"),
                    Reasons=("Reason", lambda x: "; ".join(sorted(set(x)))[:240]),
                ).sort_values("Avg_Score", ascending=False)
                overall["Avg_Score"] = overall["Avg_Score"].round(2)
                st.dataframe(overall, use_container_width=True)
            elif map_choice == "Best 2 / 3 / 4":
                overall = recs.groupby(["Team", "Player", "Role"], as_index=False).agg(
                    Avg_Score=("Score", "mean"),
                    Confidence=("Confidence", lambda x: sorted(set(x))[0]),
                    Data_Source=("Data Source", lambda x: sorted(set(x))[0]),
                ).sort_values("Avg_Score", ascending=False)
                st.markdown("#### Best 2")
                st.write(", ".join([f"**{r.Player}** ({r.Team})" for _, r in overall.head(2).iterrows()]))
                st.markdown("#### Best 3")
                st.write(", ".join([f"**{r.Player}** ({r.Team})" for _, r in overall.head(3).iterrows()]))
                st.markdown("#### Best 4")
                st.write(", ".join([f"**{r.Player}** ({r.Team})" for _, r in overall.head(4).iterrows()]))
                st.dataframe(overall.head(12), use_container_width=True)
            elif map_choice == "Avoid / Low Confidence":
                avoid = recs[recs["Confidence"].isin(["Low", "Low/Medium"])].sort_values("Score", ascending=True)
                if avoid.empty:
                    st.success("No obvious low-confidence players from the current data.")
                else:
                    st.dataframe(avoid.head(20), use_container_width=True)
            else:
                map_no = int(map_choice.split()[1])
                view = recs[recs["Map"] == map_no].sort_values("Score", ascending=False)
                st.dataframe(view, use_container_width=True)
                st.markdown("#### Top 4 on this map")
                for _, r in view.head(4).iterrows():
                    st.write(f"**{r['Player']}** ({r['Team']}) — {r['Mode']} — score **{r['Score']}** — {r['Confidence']}")

        with st.expander("Selected-match Cito raw player/map rows"):
            if deep_stats_df.empty:
                st.write("No Cito stat rows loaded.")
            else:
                st.dataframe(deep_stats_df, use_container_width=True)

with tabs[1]:
    st.subheader("Cito API Data")
    if not has_key:
        st.error("No Cito key found in Streamlit Secrets.")
    else:
        st.success("Cito key found. Endpoint checks below show which endpoints worked.")

    endpoint_rows = []
    for group, results in cito_bundle.items():
        for res in results:
            endpoint_rows.append({
                "Group": group,
                "URL": res.get("url"),
                "Status": res.get("status"),
                "OK": res.get("ok"),
            })
    st.dataframe(pd.DataFrame(endpoint_rows), use_container_width=True)

    st.markdown("### Matches parsed")
    st.dataframe(matches.drop(columns=["raw"], errors="ignore"), use_container_width=True)

    st.markdown("### Team strength")
    team_df_current = build_team_strength(roster_map)
    st.dataframe(team_df_current, use_container_width=True)

    st.markdown("### API explorer")
    st.write("Use this to inspect Cito responses without changing the app code.")
    custom_endpoint = st.text_input("Endpoint", value="/api/v1/cod/matches/live")
    if st.button("Test endpoint"):
        res = cito_get(custom_endpoint)
        st.write(f"Status: {res['status']} | OK: {res['ok']}")
        st.json(res["payload"])

with tabs[2]:
    st.subheader("Rosters")
    rows = []
    for team, players in roster_map.items():
        for p in players:
            prof = profile_for(p)
            rows.append({
                "Team": team,
                "Player": p,
                "Role": prof["role"],
                "Overall": prof["overall"],
                "HP": prof["hp"],
                "SND": prof["snd"],
                "OVL": prof["ovl"],
                "Profile Source": "Seeded" if p in PLAYER_PRIORS else "Unknown fallback",
            })
    st.dataframe(pd.DataFrame(rows).sort_values(["Team", "Overall"], ascending=[True, False]) if rows else pd.DataFrame(), use_container_width=True)

    with st.expander("Cito roster rows"):
        st.dataframe(cito_rosters, use_container_width=True)

with tabs[3]:
    st.subheader("Social / Intel Notes")
    st.write("Paste notes from X/Twitter, Reddit, YouTube, Breaking Point articles, analyst comments, roster news, illness/sub rumours, etc.")
    st.session_state["intel_notes"] = st.text_area(
        "Intel notes",
        value=st.session_state.get("intel_notes", ""),
        height=260,
        placeholder="Example: HyDra looked hot last series. Team X struggling on Search. Player Y may be sick. Analyst said LAT likely pick HP map...",
    )

    st.info(
        "This is a lightweight notes engine, not live Twitter/Reddit scraping. "
        "It applies small confidence/score adjustments when players or teams are mentioned with positive/negative form words."
    )

    all_players = [p for players in roster_map.values() for p in players]
    adjs = intel_adjustments(st.session_state.get("intel_notes", ""), all_players, list(roster_map.keys()))
    st.markdown("### Detected adjustments")
    if adjs:
        st.json(adjs)
    else:
        st.write("No specific player/team adjustments detected yet.")

with tabs[4]:
    st.subheader("Debug")
    st.markdown("### Cito raw endpoint responses")
    for group, results in cito_bundle.items():
        with st.expander(f"Cito group: {group}"):
            for res in results:
                st.write(res["url"], res["status"], res["ok"])
                st.json(res["payload"])

    st.markdown("### Breaking Point fallback")
    with st.expander("BP rosters parsed"):
        st.json(bp_bundle.get("rosters", {}))
    with st.expander("BP teams text"):
        st.text(bp_bundle.get("teams_text", "")[:20000])
    with st.expander("BP matches text"):
        st.text(bp_bundle.get("matches_text", "")[:20000])

st.caption(
    "Data quality guide: High = Cito player/map stats + known maps. "
    "Medium = Cito stats or known map/veto. Low = fallback roster/profile only. "
    "This is an analysis tool only."
)
