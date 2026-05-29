import re
import math
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


BP_BASE = "https://breakingpoint.gg"
URLS = {
    "player_stats": "https://breakingpoint.gg/stats",
    "advanced_stats": "https://breakingpoint.gg/stats/advanced",
    "team_stats": "https://breakingpoint.gg/stats/teams",
    "teams_players": "https://breakingpoint.gg/cdl/teams-and-players",
    "matches": "https://breakingpoint.gg/matches",
    "official_cdl_stats": "https://callofdutyleague.com/en-us/stats",
    "official_cdl_schedule": "https://callofdutyleague.com/en-us/schedule",
}

TEAM_NAMES = [
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


st.set_page_config(page_title="CDL Auto Stats Analyser", layout="wide")


def http_get(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 CDL stats analyser; contact: personal local analysis",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=25)
    r.raise_for_status()
    return r.text


@st.cache_data(ttl=900)
def read_tables(url: str) -> List[pd.DataFrame]:
    try:
        return pd.read_html(url)
    except Exception:
        return []


@st.cache_data(ttl=900)
def read_text(url: str) -> str:
    html = http_get(url)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return "\n".join([x.strip() for x in soup.get_text("\n").splitlines() if x.strip()])


def clean_col(c: str) -> str:
    c = str(c).strip().lower()
    c = re.sub(r"[^a-z0-9%/ ]+", "", c)
    c = re.sub(r"\s+", " ", c).strip()
    return c


def normalise_table(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [clean_col(c) for c in df.columns]
    return df


def try_float_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str)
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.extract(r"([-+]?\d*\.?\d+)", expand=False),
        errors="coerce"
    )


def find_name_column(df: pd.DataFrame, expected: str) -> Optional[str]:
    candidates = list(df.columns)
    if expected in candidates:
        return expected
    for c in candidates:
        if expected in c:
            return c
    for c in candidates:
        if c in ["name", "player", "team", "players", "teams"]:
            return c
    return None


@st.cache_data(ttl=900)
def get_all_data():
    data = {}

    for key, url in URLS.items():
        data[key] = {
            "url": url,
            "tables": [normalise_table(t) for t in read_tables(url)],
        }

    for key in ["matches", "teams_players", "player_stats", "advanced_stats", "team_stats"]:
        try:
            data[key]["text"] = read_text(URLS[key])
        except Exception as e:
            data[key]["text"] = f"ERROR: {e}"

    return data


def pick_best_player_table(tables: List[pd.DataFrame]) -> pd.DataFrame:
    best = pd.DataFrame()
    best_score = -1

    for t in tables:
        if t.empty:
            continue

        cols = set(t.columns)
        has_player = any("player" in c or "name" == c for c in cols)
        numeric_cols = 0

        for c in t.columns:
            if try_float_series(t[c]).notna().sum() >= max(3, len(t) * 0.25):
                numeric_cols += 1

        score = (10 if has_player else 0) + numeric_cols + min(len(t), 100) / 100

        if score > best_score:
            best = t
            best_score = score

    return best


def pick_best_team_table(tables: List[pd.DataFrame]) -> pd.DataFrame:
    best = pd.DataFrame()
    best_score = -1

    for t in tables:
        if t.empty:
            continue

        cols = set(t.columns)
        has_team = any("team" in c or "name" == c for c in cols)
        numeric_cols = 0

        for c in t.columns:
            if try_float_series(t[c]).notna().sum() >= max(3, len(t) * 0.25):
                numeric_cols += 1

        score = (10 if has_team else 0) + numeric_cols + min(len(t), 100) / 100

        if score > best_score:
            best = t
            best_score = score

    return best


def score_players(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    name_col = find_name_column(df, "player")

    if name_col is None:
        name_col = find_name_column(df, "name")

    if name_col is None:
        return pd.DataFrame()

    # Remove empty/duplicate rows
    df = df[df[name_col].astype(str).str.len() > 1].copy()

    metric_hints = [
        "bp rating", "slayer rating", "kd", "k/d",
        "hardpoint kp10m", "hp kp10m", "snd kpr", "search kpr",
        "ovl kp10m", "damage", "dmg/10m", "kills"
    ]

    metric_cols = []

    for c in df.columns:
        if c == name_col:
            continue

        numeric = try_float_series(df[c])
        enough_numeric = numeric.notna().sum() >= max(5, len(df) * 0.25)
        hinted = any(h in c for h in metric_hints)

        if enough_numeric and (hinted or len(metric_cols) < 8):
            metric_cols.append(c)
            df[c + "_num"] = numeric

    if not metric_cols:
        return df[[name_col]].rename(columns={name_col: "Player"})

    score = pd.Series(0.0, index=df.index)
    used = []

    weights = {
        "bp rating": 1.4,
        "slayer rating": 1.3,
        "hardpoint kp10m": 1.25,
        "hp kp10m": 1.25,
        "snd kpr": 1.2,
        "kd": 1.15,
        "k/d": 1.15,
        "damage": 1.0,
        "dmg/10m": 1.0,
        "kills": 0.9,
    }

    for c in metric_cols:
        s = df[c + "_num"]
        if s.std(skipna=True) == 0 or s.notna().sum() < 3:
            continue

        z = (s - s.mean(skipna=True)) / s.std(skipna=True)
        w = 0.8
        for hint, weight in weights.items():
            if hint in c:
                w = weight
                break

        score += z.fillna(0) * w
        used.append(c)

    df["Model Score"] = score
    df["Confidence"] = pd.qcut(
        df["Model Score"].rank(method="first"),
        q=4,
        labels=["Low", "Medium", "Good", "Strong"]
    ).astype(str)

    keep = [name_col]
    for c in used[:10]:
        keep.append(c)
    keep += ["Model Score", "Confidence"]

    out = df[keep].copy()
    out = out.rename(columns={name_col: "Player"})
    out["Model Score"] = out["Model Score"].round(2)
    return out.sort_values("Model Score", ascending=False)


def score_teams(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    team_col = find_name_column(df, "team")

    if team_col is None:
        return pd.DataFrame()

    df = df[df[team_col].astype(str).str.len() > 1].copy()

    metric_cols = []

    for c in df.columns:
        if c == team_col:
            continue

        numeric = try_float_series(df[c])
        enough_numeric = numeric.notna().sum() >= max(3, len(df) * 0.25)

        if enough_numeric:
            metric_cols.append(c)
            df[c + "_num"] = numeric

    if not metric_cols:
        return df[[team_col]].rename(columns={team_col: "Team"})

    score = pd.Series(0.0, index=df.index)

    for c in metric_cols:
        s = df[c + "_num"]
        if s.std(skipna=True) == 0 or s.notna().sum() < 3:
            continue

        # Most team stats are positive-high-is-good, but losses/deaths would need inverse handling.
        inverse = any(x in c for x in ["loss", "deaths", "death"])
        z = (s - s.mean(skipna=True)) / s.std(skipna=True)

        if inverse:
            z = -z

        weight = 1.0
        if "win" in c or "%" in c:
            weight = 1.25
        if "hardpoint" in c or "snd" in c or "search" in c or "control" in c or "overload" in c:
            weight = 1.1

        score += z.fillna(0) * weight

    df["Team Score"] = score.round(2)

    keep = [team_col] + metric_cols[:10] + ["Team Score"]
    out = df[keep].copy().rename(columns={team_col: "Team"})
    return out.sort_values("Team Score", ascending=False)


def parse_matches_from_text(text: str) -> pd.DataFrame:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    rows = []
    current_date = None

    for i, line in enumerate(lines):
        # Date line example: Friday - May 29, 2026
        if re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+-\s+", line):
            current_date = line
            continue

        # Time/event line example: 7:00 PM | BO 5 | MQ Major 4 Q CDL 2026
        if re.search(r"\d{1,2}:\d{2}\s*(AM|PM)", line) and "|" in line:
            time_line = line
            # Look ahead for first line containing a known team name pairing
            chunk = " ".join(lines[i+1:i+8])
            found = [t for t in TEAM_NAMES if t in chunk]

            if len(found) >= 2:
                rows.append({
                    "Date": current_date,
                    "Time/Event": time_line,
                    "Team A": found[0],
                    "Team B": found[1],
                    "Source": "Breaking Point text parse"
                })

    return pd.DataFrame(rows).drop_duplicates()


def predict_matches(matches: pd.DataFrame, teams_ranked: pd.DataFrame) -> pd.DataFrame:
    if matches.empty or teams_ranked.empty or "Team" not in teams_ranked.columns or "Team Score" not in teams_ranked.columns:
        return matches

    scores = dict(zip(teams_ranked["Team"], teams_ranked["Team Score"]))

    rows = []

    for _, r in matches.iterrows():
        a, b = r["Team A"], r["Team B"]
        sa = float(scores.get(a, 0))
        sb = float(scores.get(b, 0))
        diff = sa - sb

        # Soft probability, not a true betting probability.
        p_a = 1 / (1 + math.exp(-diff / 3))
        winner = a if p_a >= 0.5 else b
        confidence = abs(p_a - 0.5) * 2

        rows.append({
            **r.to_dict(),
            "Predicted Stronger Team": winner,
            "Team A Model Chance": round(p_a, 3),
            "Team B Model Chance": round(1 - p_a, 3),
            "Confidence": "High" if confidence > 0.35 else "Medium" if confidence > 0.18 else "Low",
            "Reason": f"{a} score {sa:.2f} vs {b} score {sb:.2f}"
        })

    return pd.DataFrame(rows)


st.title("CDL Auto Stats Analyser")
st.caption("Automatically pulls public CDL/Breaking Point pages and ranks teams/players. This is analysis only, not financial advice.")

with st.sidebar:
    st.header("Controls")
    refresh = st.button("Refresh public stats")
    top_n = st.slider("Top players to show", 5, 30, 12)
    st.markdown("Sources used:")
    for label, url in URLS.items():
        st.write(f"- {label}: {url}")

if refresh:
    st.cache_data.clear()
    st.rerun()

data = get_all_data()

player_tables = data["player_stats"]["tables"] + data["advanced_stats"]["tables"] + data["official_cdl_stats"]["tables"]
team_tables = data["team_stats"]["tables"]
matches_text = data["matches"].get("text", "")

player_raw = pick_best_player_table(player_tables)
team_raw = pick_best_team_table(team_tables)
players_ranked = score_players(player_raw)
teams_ranked = score_teams(team_raw)

matches = parse_matches_from_text(matches_text)
match_predictions = predict_matches(matches, teams_ranked)

tabs = st.tabs([
    "Best Players",
    "Team Strength",
    "Upcoming Matches",
    "Raw Player Data",
    "Raw Team Data",
    "Debug / Source Text"
])

with tabs[0]:
    st.subheader("Best player targets from current public stats")

    if players_ranked.empty:
        st.warning("Could not extract a clean player stats table. Try Refresh or check Debug.")
    else:
        st.dataframe(players_ranked.head(top_n), use_container_width=True)

        st.markdown("### Simple reading")
        for _, r in players_ranked.head(min(8, top_n)).iterrows():
            st.write(f"**{r['Player']}** — score **{r['Model Score']}**, confidence **{r['Confidence']}**")

with tabs[1]:
    st.subheader("Team strength ranking")

    if teams_ranked.empty:
        st.warning("Could not extract a clean team stats table. Try Refresh or check Debug.")
    else:
        st.dataframe(teams_ranked, use_container_width=True)

with tabs[2]:
    st.subheader("Upcoming CDL matches and stronger side")

    if match_predictions.empty:
        st.warning("Could not parse upcoming matches from the public page.")
    else:
        st.dataframe(match_predictions, use_container_width=True)

        st.markdown("### Match view")
        for _, r in match_predictions.iterrows():
            st.markdown(
                f"**{r['Team A']} vs {r['Team B']}** — {r['Date']} / {r['Time/Event']}  \n"
                f"Model favours: **{r['Predicted Stronger Team']}** "
                f"({r['Confidence']} confidence). {r['Reason']}."
            )

with tabs[3]:
    st.subheader("Raw detected player table")
    st.dataframe(player_raw, use_container_width=True)

with tabs[4]:
    st.subheader("Raw detected team table")
    st.dataframe(team_raw, use_container_width=True)

with tabs[5]:
    st.subheader("Debug data")
    st.write("If parsing breaks, check whether the source page layout changed.")
    with st.expander("Breaking Point matches text"):
        st.text(matches_text[:15000])

    with st.expander("Available player tables"):
        for i, t in enumerate(player_tables):
            st.write(f"Table {i}: shape {t.shape}")
            st.dataframe(t.head(20), use_container_width=True)

    with st.expander("Available team tables"):
        for i, t in enumerate(team_tables):
            st.write(f"Table {i}: shape {t.shape}")
            st.dataframe(t.head(20), use_container_width=True)
