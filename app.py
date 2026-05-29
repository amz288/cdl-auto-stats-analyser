import re
import math
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


BP_BASE = "https://breakingpoint.gg"

TEAM_INDEX_URL = "https://breakingpoint.gg/cdl/teams-and-players"
MATCHES_URL = "https://breakingpoint.gg/matches"
STATS_URL = "https://breakingpoint.gg/stats"
ADVANCED_STATS_URL = "https://breakingpoint.gg/stats/advanced"
TEAM_STATS_URL = "https://breakingpoint.gg/stats/teams"

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


st.set_page_config(page_title="CDL Auto Stats Analyser", layout="wide")


def get_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 CDL Auto Stats Analyser",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    response = requests.get(url, headers=headers, timeout=25)
    response.raise_for_status()
    return response.text


def get_soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(get_html(url), "html.parser")


def page_text_from_soup(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    lines = [x.strip() for x in soup.get_text("\n").splitlines() if x.strip()]
    return "\n".join(lines)


@st.cache_data(ttl=900)
def get_team_links():
    """
    Pull team page links from Breaking Point rather than hard-coding every team ID.
    """
    soup = get_soup(TEAM_INDEX_URL)

    links = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/teams/" not in href:
            continue

        url = urljoin(BP_BASE, href)
        text = " ".join(a.get_text(" ", strip=True).split())

        # The anchor text is sometimes short, so fall back to the slug.
        slug = href.rstrip("/").split("/")[-1].replace("-", " ")
        name = text if len(text) > 2 else slug.title()

        # Keep only likely CDL teams.
        for team in KNOWN_TEAMS:
            if team.lower() in name.lower() or team.lower().replace(" ", "-") in href.lower():
                links[team] = url

    # If the team index page layout changes, this fallback keeps the app useful for common pages.
    if not links:
        links = {
            "Los Angeles Thieves": "https://breakingpoint.gg/teams/2/Los-Angeles-Thieves",
        }

    return links


def extract_player_rows_from_team_page(team_name: str, url: str):
    soup = get_soup(url)
    text = page_text_from_soup(soup)

    # Extract player links from the team page.
    player_names = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/players/" not in href:
            continue

        name = " ".join(a.get_text(" ", strip=True).split())
        slug = href.rstrip("/").split("/")[-1]

        if not name or len(name) < 2:
            name = slug

        # Remove repeated junk.
        name = name.replace("’s headshot", "").replace("'s headshot", "").strip()

        if name and name not in player_names:
            player_names.append(name)

    rows = []

    for player in player_names:
        # Look for nearby stat patterns such as: HyDra 1.05 93.26
        escaped = re.escape(player)
        patterns = [
            rf"{escaped}\s+([0-9]\.\d{{2}})\s+([0-9]{{2,3}}\.\d{{1,2}})",
            rf"{escaped}.*?([0-9]\.\d{{2}}).*?([0-9]{{2,3}}\.\d{{1,2}})",
        ]

        kd = None
        bp_rating = None

        compact = re.sub(r"\s+", " ", text)

        for pattern in patterns:
            match = re.search(pattern, compact, flags=re.IGNORECASE)
            if match:
                kd = float(match.group(1))
                bp_rating = float(match.group(2))
                break

        score = None
        if kd is not None and bp_rating is not None:
            score = round((kd * 35) + (bp_rating * 0.65), 2)

        rows.append({
            "Team": team_name,
            "Player": player,
            "K/D": kd,
            "BP Rating": bp_rating,
            "Model Score": score,
            "Source": url,
        })

    return rows, text


@st.cache_data(ttl=900)
def build_player_database():
    team_links = get_team_links()
    all_rows = []
    debug_pages = {}

    for team, url in team_links.items():
        try:
            rows, text = extract_player_rows_from_team_page(team, url)
            all_rows.extend(rows)
            debug_pages[team] = {
                "url": url,
                "text_preview": text[:12000],
                "rows_found": len(rows),
            }
        except Exception as e:
            debug_pages[team] = {
                "url": url,
                "error": str(e),
                "rows_found": 0,
            }

    df = pd.DataFrame(all_rows)

    if not df.empty:
        # De-dupe player/team pairs.
        df = df.drop_duplicates(subset=["Team", "Player"], keep="first")

        # If a player has no parsed stat, keep them but score them lower.
        df["Model Score"] = pd.to_numeric(df["Model Score"], errors="coerce")

        # Rank with available stats first.
        df["Stats Parsed"] = df["Model Score"].notna()
        df = df.sort_values(["Stats Parsed", "Model Score"], ascending=[False, False])

        # Confidence labels.
        def confidence(row):
            if not row["Stats Parsed"]:
                return "Roster only"
            if row["Model Score"] >= 95:
                return "Strong"
            if row["Model Score"] >= 90:
                return "Good"
            if row["Model Score"] >= 84:
                return "Medium"
            return "Low"

        df["Confidence"] = df.apply(confidence, axis=1)

    return df, debug_pages, team_links


@st.cache_data(ttl=900)
def get_stats_page_texts():
    output = {}

    for name, url in {
        "Player Stats": STATS_URL,
        "Advanced Stats": ADVANCED_STATS_URL,
        "Team Stats": TEAM_STATS_URL,
        "Matches": MATCHES_URL,
    }.items():
        try:
            soup = get_soup(url)
            output[name] = {
                "url": url,
                "text": page_text_from_soup(soup)[:15000],
            }
        except Exception as e:
            output[name] = {
                "url": url,
                "error": str(e),
            }

    return output


def parse_upcoming_matches(text: str):
    compact = re.sub(r"\s+", " ", text)

    rows = []

    # Breaking Point often exposes upcoming rows like:
    # ~3 hours CDL Major 4 Qualifier Toronto KOI 0 Carolina Royal Ravens 0
    pattern = r"(~\d+\s+(?:hours?|days?))\s+(CDL\s+[^~]+?)\s+(" + "|".join(map(re.escape, KNOWN_TEAMS)) + r")\s+0\s+(" + "|".join(map(re.escape, KNOWN_TEAMS)) + r")\s+0"

    for match in re.finditer(pattern, compact):
        eta = match.group(1)
        event_blob = match.group(2).strip()
        team_a = match.group(3)
        team_b = match.group(4)

        # Clean event text if it swallowed too much.
        event_blob = re.sub(r"\s+", " ", event_blob)
        event_blob = event_blob.replace(team_a, "").replace(team_b, "").strip()

        rows.append({
            "ETA": eta,
            "Event": event_blob,
            "Team A": team_a,
            "Team B": team_b,
            "Source": MATCHES_URL,
        })

    return pd.DataFrame(rows).drop_duplicates()


def team_strength_from_players(players_df: pd.DataFrame):
    if players_df.empty:
        return pd.DataFrame()

    usable = players_df.copy()
    usable["Model Score"] = pd.to_numeric(usable["Model Score"], errors="coerce")

    team_df = usable.groupby("Team", as_index=False).agg(
        Players=("Player", "count"),
        Parsed_Stats=("Stats Parsed", "sum"),
        Avg_Player_Score=("Model Score", "mean"),
        Avg_KD=("K/D", "mean"),
        Avg_BP_Rating=("BP Rating", "mean"),
    )

    team_df["Team Score"] = (
        team_df["Avg_Player_Score"].fillna(0) * 0.75
        + team_df["Parsed_Stats"].fillna(0) * 2
        + team_df["Players"].fillna(0) * 0.5
    ).round(2)

    return team_df.sort_values("Team Score", ascending=False)


def predict_matches(matches: pd.DataFrame, teams: pd.DataFrame):
    if matches.empty or teams.empty:
        return matches

    scores = dict(zip(teams["Team"], teams["Team Score"]))
    rows = []

    for _, row in matches.iterrows():
        a = row["Team A"]
        b = row["Team B"]

        sa = float(scores.get(a, 0))
        sb = float(scores.get(b, 0))

        # Soft model probability, not betting probability.
        diff = sa - sb
        p_a = 1 / (1 + math.exp(-diff / 12))

        rows.append({
            **row.to_dict(),
            "Predicted Stronger Team": a if p_a >= 0.5 else b,
            "Team A Model Chance": round(p_a, 3),
            "Team B Model Chance": round(1 - p_a, 3),
            "Confidence": "High" if abs(p_a - 0.5) > 0.25 else "Medium" if abs(p_a - 0.5) > 0.12 else "Low",
            "Reason": f"{a} score {sa:.2f} vs {b} score {sb:.2f}",
        })

    return pd.DataFrame(rows)


st.title("CDL Auto Stats Analyser")
st.caption("Pulls public Breaking Point CDL pages and ranks teams/players. Analysis only, not financial advice.")

with st.sidebar:
    st.header("Controls")
    if st.button("Refresh public stats"):
        st.cache_data.clear()
        st.rerun()

    top_n = st.slider("Top players to show", 5, 40, 20)

players_df, debug_pages, team_links = build_player_database()
stats_texts = get_stats_page_texts()
matches_raw_text = stats_texts.get("Matches", {}).get("text", "")
matches_df = parse_upcoming_matches(matches_raw_text)
teams_df = team_strength_from_players(players_df)
predictions_df = predict_matches(matches_df, teams_df)

tabs = st.tabs([
    "Best Players",
    "Team Strength",
    "Upcoming Matches",
    "Sources",
    "Debug",
])

with tabs[0]:
    st.subheader("Best player targets")

    if players_df.empty:
        st.error("No player data found. Breaking Point may have blocked the request or changed the page layout.")
    else:
        display = players_df.head(top_n).copy()
        st.dataframe(display, use_container_width=True)

        st.markdown("### Quick read")
        for _, r in display.head(10).iterrows():
            stat_text = ""
            if pd.notna(r["K/D"]) and pd.notna(r["BP Rating"]):
                stat_text = f"K/D {r['K/D']:.2f}, BP Rating {r['BP Rating']:.2f}"
            else:
                stat_text = "roster found, detailed stats not parsed"

            st.write(f"**{r['Player']}** ({r['Team']}) — **{r['Confidence']}** — {stat_text}")

with tabs[1]:
    st.subheader("Team strength from parsed roster/player stats")

    if teams_df.empty:
        st.warning("No team strength data found yet.")
    else:
        st.dataframe(teams_df, use_container_width=True)

with tabs[2]:
    st.subheader("Upcoming matches")

    if predictions_df.empty:
        st.warning("Could not parse upcoming matches from the matches page.")
    else:
        st.dataframe(predictions_df, use_container_width=True)

        st.markdown("### Match read")
        for _, r in predictions_df.head(12).iterrows():
            st.markdown(
                f"**{r['Team A']} vs {r['Team B']}** — {r['ETA']} — "
                f"model favours **{r['Predicted Stronger Team']}** "
                f"({r['Confidence']} confidence). {r['Reason']}."
            )

with tabs[3]:
    st.subheader("Source links")
    st.write("Team links found:")
    st.json(team_links)

    st.write("Main source pages:")
    st.write({
        "Teams and Players": TEAM_INDEX_URL,
        "Matches": MATCHES_URL,
        "Player Stats": STATS_URL,
        "Advanced Stats": ADVANCED_STATS_URL,
        "Team Stats": TEAM_STATS_URL,
    })

with tabs[4]:
    st.subheader("Debug")

    st.write("If a page layout changes, this tab shows what was pulled.")

    with st.expander("Team page debug"):
        st.json(debug_pages)

    for name, payload in stats_texts.items():
        with st.expander(name):
            st.write(payload.get("url"))
            if "error" in payload:
                st.error(payload["error"])
            else:
                st.text(payload.get("text", ""))
