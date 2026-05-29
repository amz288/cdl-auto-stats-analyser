import re, math
from typing import Any, Dict, List, Tuple
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

CITO_BASE = "https://api.citoapi.com/api/v1/cod"
BP_MATCHES_URL = "https://breakingpoint.gg/matches"
MODE_ORDER = ["Hardpoint", "Search & Destroy", "Overload", "Hardpoint", "Search & Destroy"]
KNOWN_TEAMS = {
    "boston-breach": "Boston Breach",
    "carolina-royal-ravens": "Carolina Royal Ravens",
    "cloud9-new-york": "Cloud9 New York",
    "faze-vegas": "FaZe Vegas",
    "g2-minnesota": "G2 Minnesota",
    "los-angeles-thieves": "Los Angeles Thieves",
    "miami-heretics": "Miami Heretics",
    "optic-texas": "OpTic Texas",
    "paris-gentle-mates": "Paris Gentle Mates",
    "riyadh-falcons": "Riyadh Falcons",
    "toronto-koi": "Toronto KOI",
    "vancouver-surge": "Vancouver Surge",
}
TEAM_NAMES = list(KNOWN_TEAMS.values())

st.set_page_config(page_title="CDL Cito Hybrid v5", layout="wide")
st.title("CDL Cito Hybrid v5")
st.caption("Recent completed Cito map/player stats → upcoming match recommendations → manual veto updater.")

def key():
    try: return st.secrets.get("CITO_API_KEY","")
    except Exception: return ""

def safe(x): return "" if x is None else str(x).strip()

def num(x):
    try:
        s = re.sub(r"[^0-9.\-]", "", safe(x))
        return float(s) if s not in ["",".","-"] else None
    except Exception: return None

def norm_team(x):
    s = safe(x)
    if not s: return ""
    slug = re.sub(r"[^a-z0-9-]", "", s.lower().replace("_","-").replace(" ","-"))
    if slug in KNOWN_TEAMS: return KNOWN_TEAMS[slug]
    for name in TEAM_NAMES:
        if s.lower() == name.lower() or name.lower() in s.lower() or s.lower() in name.lower():
            return name
    return ""

def norm_mode(x):
    s = safe(x).lower()
    if "search" in s or "snd" in s or "s&d" in s: return "Search & Destroy"
    if "overload" in s or "ovl" in s: return "Overload"
    if "hardpoint" in s or "hp" in s: return "Hardpoint"
    return safe(x)

def get_nested(d, paths):
    for p in paths:
        cur = d
        ok = True
        for part in p.split("."):
            if isinstance(cur, dict) and part in cur: cur = cur[part]
            else: ok = False; break
        if ok and safe(cur): return cur
    return ""

def headers():
    return {"x-api-key": key(), "accept": "application/json", "user-agent": "CDL-Cito-Hybrid-v5"}

@st.cache_data(ttl=900, show_spinner=False)
def cito_get(path, params=None):
    url = path if path.startswith("http") else f"{CITO_BASE}{path}"
    try:
        r = requests.get(url, headers=headers(), params=params or {}, timeout=25)
        try: payload = r.json()
        except Exception: payload = {"raw_text": r.text[:1200]}
        return {"ok": r.ok, "status": r.status_code, "url": r.url, "payload": payload}
    except Exception as e:
        return {"ok": False, "status": "ERR", "url": url, "payload": {"error": str(e)}}

def data_part(payload):
    if isinstance(payload, dict) and "data" in payload: return payload["data"]
    return payload

def as_list(payload):
    x = data_part(payload)
    if isinstance(x, list): return x
    if isinstance(x, dict):
        for k in ["matches","items","results","data"]:
            if isinstance(x.get(k), list): return x[k]
    return []

def match_id_from(x):
    mid = safe(x)
    if not mid: return ""
    return mid if mid.startswith("bp-match") else (f"bp-match-{mid}" if mid.isdigit() else mid)

def parse_match_rows(payload, source):
    rows = []
    for m in as_list(payload):
        if not isinstance(m, dict): continue
        mid = match_id_from(get_nested(m, ["matchId","id","bpMatchId"]))
        a = norm_team(get_nested(m, ["teams.team1.name","team1.name","homeTeam.name","teamA.name","team1","homeTeam","teams.team1.slug","team1.slug"]))
        b = norm_team(get_nested(m, ["teams.team2.name","team2.name","awayTeam.name","teamB.name","team2","awayTeam","teams.team2.slug","team2.slug"]))
        blob = str(m)
        found = [t for t in TEAM_NAMES if t.lower() in blob.lower()]
        if not a and len(found)>=1: a=found[0]
        if not b and len(found)>=2: b=found[1]
        if not a or not b: continue
        rows.append({
            "match_id": mid,
            "start": safe(get_nested(m, ["startsAt","startTime","scheduledAt","matchDate","date"])),
            "event": safe(get_nested(m, ["tournament.name","event.name","event","round","stage.name"])) or "CDL",
            "team_a": a, "team_b": b,
            "status": safe(get_nested(m, ["status","state"])),
            "source": source
        })
    return rows

@st.cache_data(ttl=900, show_spinner=True)
def load_schedule():
    calls = [cito_get("/cdl/schedule"), cito_get("/matches/upcoming")]
    rows = []
    for c in calls:
        if c["ok"]: rows += parse_match_rows(c["payload"], c["url"])
    return (pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()), calls

@st.cache_data(ttl=900, show_spinner=True)
def load_recent(limit, season):
    calls = [cito_get("/matches", {"limit": limit, "season": season}), cito_get("/matches/recent", {"limit": limit})]
    rows = []
    for c in calls:
        if c["ok"]: rows += parse_match_rows(c["payload"], c["url"])
    df = pd.DataFrame(rows).drop_duplicates(subset=["match_id"]) if rows else pd.DataFrame()
    return df, calls

@st.cache_data(ttl=900, show_spinner=True)
def load_stats(match_ids):
    rows, calls = [], []
    for mid in match_ids:
        c = cito_get(f"/matches/{mid}/player-stats", {"includeMaps": "true"})
        calls.append(c)
        if not c["ok"]: continue
        d = data_part(c["payload"])
        if not isinstance(d, dict): continue
        match = d.get("match", {}) if isinstance(d.get("match"), dict) else {}
        slug_map = {}
        teams = d.get("teams", {}) if isinstance(d.get("teams"), dict) else {}
        for tv in teams.values():
            if isinstance(tv, dict):
                slug = safe(tv.get("slug"))
                name = norm_team(tv.get("name")) or norm_team(slug)
                if slug and name: slug_map[slug] = name
        for p in d.get("players", []) if isinstance(d.get("players"), list) else []:
            if not isinstance(p, dict): continue
            player = safe(p.get("playerName") or p.get("name") or p.get("ign") or p.get("gamertag"))
            team = norm_team(p.get("team") or p.get("teamName") or p.get("teamSlug"))
            if not team and safe(p.get("teamSlug")) in slug_map: team = slug_map[safe(p.get("teamSlug"))]
            if not player or not team: continue
            maps = p.get("maps", [])
            if isinstance(maps, list) and maps:
                for mp in maps:
                    if not isinstance(mp, dict): continue
                    rows.append({
                        "match_id": mid, "match_date": safe(match.get("matchDate") or match.get("startsAt")),
                        "Team": team, "Player": player, "Map": safe(mp.get("mapNumber")),
                        "Map Name": safe(mp.get("mapName")), "Mode": norm_mode(mp.get("gameMode") or mp.get("mode")),
                        "Kills": num(mp.get("kills")), "Deaths": num(mp.get("deaths")),
                        "Damage": num(mp.get("damage")), "KD": num(mp.get("kd")),
                        "Source": "Cito map"
                    })
            else:
                rows.append({
                    "match_id": mid, "match_date": safe(match.get("matchDate") or match.get("startsAt")),
                    "Team": team, "Player": player, "Map": "Series", "Map Name": "", "Mode": "Series",
                    "Kills": num(p.get("kills")), "Deaths": num(p.get("deaths")),
                    "Damage": num(p.get("damage")), "KD": num(p.get("kd")), "Source": "Cito aggregate"
                })
    return (pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()), calls

@st.cache_data(ttl=900)
def bp_matches():
    try:
        r = requests.get(BP_MATCHES_URL, headers={"user-agent":"Mozilla/5.0"}, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script","style","noscript"]): tag.decompose()
        text = " ".join(x.strip() for x in soup.get_text("\n").splitlines() if x.strip())
        alt = "|".join(map(re.escape, TEAM_NAMES))
        pat = rf"(~\d+\s+(?:hours?|days?))\s+(CDL\s+(?:Major|Minor|Champs)[^~]*?)\s+({alt}|TBD)\s+0\s+({alt}|TBD)\s+0"
        rows = [{"match_id":"", "start":m.group(1), "event":m.group(2), "team_a":m.group(3), "team_b":m.group(4), "status":"upcoming", "source":"Breaking Point fallback"} for m in re.finditer(pat, text)]
        return pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def build_models(stats):
    if stats.empty: return pd.DataFrame(), pd.DataFrame(), {}, pd.DataFrame()
    maps = stats[(stats["Source"]=="Cito map") & (stats["Mode"].isin(MODE_ORDER[:3]))].copy()
    if maps.empty: return pd.DataFrame(), pd.DataFrame(), {}, pd.DataFrame()
    for c in ["Kills","Deaths","Damage","KD"]: maps[c]=pd.to_numeric(maps[c], errors="coerce")
    mode = maps.groupby(["Team","Player","Mode"], as_index=False).agg(
        Maps=("Kills","count"), Avg_Kills=("Kills","mean"), Recent_Kills=("Kills", lambda s: s.tail(5).mean()),
        Max_Kills=("Kills","max"), Avg_Deaths=("Deaths","mean"), Avg_Damage=("Damage","mean"), Avg_KD=("KD","mean")
    )
    mode["Mode Score"] = (
        mode["Avg_Kills"].fillna(0)*2.7 + mode["Recent_Kills"].fillna(mode["Avg_Kills"]).fillna(0)*1.4
        + mode["Avg_Damage"].fillna(0)/230 + mode["Avg_KD"].fillna(1)*8 + mode["Maps"].clip(upper=12)*0.7
    ).round(2)
    overall = mode.groupby(["Team","Player"], as_index=False).agg(
        Modes=("Mode","count"), Total_Maps=("Maps","sum"), Avg_Mode_Score=("Mode Score","mean"),
        Avg_Kills=("Avg_Kills","mean"), Recent_Kills=("Recent_Kills","mean")
    ).sort_values("Avg_Mode_Score", ascending=False)
    rosters = {team: list(sub.sort_values("Avg_Mode_Score", ascending=False)["Player"].head(6)) for team, sub in overall.groupby("Team")}
    team = overall.groupby("Team", as_index=False).agg(Players=("Player","count"), Player_Maps=("Total_Maps","sum"), Team_Score=("Avg_Mode_Score","mean"))
    team["Team_Score"] = team["Team_Score"].round(2)
    return mode, overall, rosters, team.sort_values("Team_Score", ascending=False)

def win_prob(a,b,team_model):
    if team_model.empty: return 0.5,0,0
    scores=dict(zip(team_model["Team"], team_model["Team_Score"]))
    sa, sb = float(scores.get(a,0)), float(scores.get(b,0))
    if sa==0 and sb==0: return 0.5,0,0
    p=1/(1+math.exp(-(sa-sb)/10))
    return round(p,3), round(sa,2), round(sb,2)

def intel_adjust(txt, player, team):
    t=safe(txt).lower()
    if not t or (player.lower() not in t and team.lower() not in t): return 0
    pos=["hot","frying","on form","good form","dominant","great","strong","improved","mvp","carry"]
    neg=["sick","ill","benched","sub","struggling","bad form","poor","unwell","visa","dropped","role change"]
    return (2.5 if any(w in t for w in pos) else 0) + (-3.5 if any(w in t for w in neg) else 0)

def recommend(match, rosters, mode_model, veto, intel):
    rows=[]
    lookup={(r.Team,r.Player,r.Mode):r for _,r in mode_model.iterrows()}
    for team in [match["team_a"], match["team_b"]]:
        for player in rosters.get(team, []):
            for _,vm in veto.iterrows():
                mode=norm_mode(vm["Mode"]); stat=lookup.get((team,player,mode))
                if stat is not None:
                    score=float(stat["Mode Score"]); maps=int(stat["Maps"]); avg=float(stat["Avg_Kills"]); recent=float(stat["Recent_Kills"]); conf="High" if safe(vm["Map Name"]) else "Medium/High"
                    reason=f"{maps} {mode} maps; avg {avg:.1f} kills; recent {recent:.1f}"
                else:
                    score=0; maps=0; avg=None; recent=None; conf="No Data"; reason="no recent Cito mode sample"
                if safe(vm["Picked By"])==team: score+=1.5; reason += "; team picked map"
                if safe(vm["Map Name"]): score+=0.5
                adj=intel_adjust(intel, player, team); score+=adj
                if adj: reason += f"; intel {adj:+.1f}"
                rows.append({"Team":team,"Player":player,"Map":int(vm["Map"]),"Mode":mode,"Map Name":safe(vm["Map Name"]),"Picked By":safe(vm["Picked By"]),"Score":round(score,2),"Avg Kills":round(avg,2) if avg else None,"Recent Kills":round(recent,2) if recent else None,"Sample Maps":maps,"Confidence":conf,"Reason":reason})
    df=pd.DataFrame(rows)
    return df.sort_values(["Map","Score"], ascending=[True,False]) if not df.empty else df

with st.sidebar:
    st.header("Data")
    st.write("Cito key:", "✅ found" if key() else "❌ missing")
    season=st.text_input("Season", "2026")
    recent_limit=st.slider("Recent completed matches to analyse", 5, 30, 12)
    if st.button("Clear cache / refresh"): st.cache_data.clear(); st.rerun()
    st.caption("Uses 1–2 calls for matches + one call per recent match for player map stats.")

if "intel" not in st.session_state: st.session_state["intel"]=""

schedule, schedule_calls = load_schedule() if key() else (pd.DataFrame(), [])
recent, recent_calls = load_recent(recent_limit, season) if key() else (pd.DataFrame(), [])
matches = schedule if not schedule.empty else bp_matches()
ids = list(recent["match_id"].dropna().astype(str).unique())[:recent_limit] if not recent.empty else []
stats, stat_calls = load_stats(ids) if ids and key() else (pd.DataFrame(), [])
mode_model, overall_model, rosters, team_model = build_models(stats)

tabs=st.tabs(["Match Centre","Player Form","Team Model","Cito Checks","Intel Notes","Debug"])

with tabs[0]:
    st.subheader("Match Centre")
    if matches.empty: st.error("No upcoming matches found.")
    elif mode_model.empty: st.error("No usable recent Cito player/map stats loaded. Check Cito Checks tab.")
    else:
        mm=matches.reset_index(drop=True)
        labels=[f"{i}: {r.start} — {r.team_a} vs {r.team_b} — {r.event}" for i,r in mm.iterrows()]
        sel=st.selectbox("Select match", labels)
        idx=int(sel.split(":")[0]); match=mm.iloc[idx]
        st.write(f"### {match.team_a} vs {match.team_b}")
        p,sa,sb=win_prob(match.team_a, match.team_b, team_model)
        c1,c2,c3=st.columns(3)
        c1.metric(match.team_a, f"{round(p*100)}%", f"score {sa}")
        c2.metric("Model stronger side", match.team_a if p>=0.5 else match.team_b)
        c3.metric(match.team_b, f"{round((1-p)*100)}%", f"score {sb}")
        missing=[t for t in [match.team_a, match.team_b] if t not in rosters]
        if missing: st.warning("No recent samples for: " + ", ".join(missing))
        st.markdown("### Veto / map picks")
        default=pd.DataFrame({"Map":[1,2,3,4,5], "Mode":MODE_ORDER, "Map Name":["","","","",""], "Picked By":["","","","",""]})
        veto=st.data_editor(default,use_container_width=True,num_rows="fixed",column_config={"Mode":st.column_config.SelectboxColumn("Mode", options=MODE_ORDER),"Picked By":st.column_config.SelectboxColumn("Picked By", options=["",match.team_a,match.team_b,"League/Default"])},key=f"veto_{idx}")
        recs=recommend(match, rosters, mode_model, veto, st.session_state["intel"])
        st.markdown("### Recommended player targets")
        if recs.empty: st.error("No recommendation rows.")
        else:
            view=st.selectbox("View", ["Best 2 / 3 / 4","Series Overall","Avoid / No Data"]+[f"Map {i} - {m}" for i,m in enumerate(MODE_ORDER,1)])
            if view=="Best 2 / 3 / 4":
                overall=recs[recs["Score"]>0].groupby(["Team","Player"],as_index=False).agg(Score=("Score","mean"),Avg_Kills=("Avg Kills","mean"),Recent_Kills=("Recent Kills","mean"),Sample_Maps=("Sample Maps","sum")).sort_values("Score",ascending=False)
                st.markdown("#### Best 2"); st.write(", ".join([f"**{r.Player}** ({r.Team})" for _,r in overall.head(2).iterrows()]) or "No data")
                st.markdown("#### Best 3"); st.write(", ".join([f"**{r.Player}** ({r.Team})" for _,r in overall.head(3).iterrows()]) or "No data")
                st.markdown("#### Best 4"); st.write(", ".join([f"**{r.Player}** ({r.Team})" for _,r in overall.head(4).iterrows()]) or "No data")
                st.dataframe(overall, use_container_width=True)
            elif view=="Series Overall":
                overall=recs.groupby(["Team","Player"],as_index=False).agg(Score=("Score","mean"),Avg_Kills=("Avg Kills","mean"),Recent_Kills=("Recent Kills","mean"),Sample_Maps=("Sample Maps","sum"),Reason=("Reason",lambda x:"; ".join(sorted(set(x)))[:300])).sort_values("Score",ascending=False)
                st.dataframe(overall,use_container_width=True)
            elif view=="Avoid / No Data":
                st.dataframe(recs[(recs["Confidence"]=="No Data") | (recs["Sample Maps"]<2)].sort_values("Score"),use_container_width=True)
            else:
                m=int(view.split()[1]); st.dataframe(recs[recs["Map"]==m].sort_values("Score",ascending=False),use_container_width=True)

with tabs[1]:
    st.subheader("Player Form Model")
    st.dataframe(mode_model.sort_values("Mode Score", ascending=False) if not mode_model.empty else mode_model, use_container_width=True)
    st.subheader("Overall")
    st.dataframe(overall_model, use_container_width=True)

with tabs[2]:
    st.subheader("Team Model")
    st.dataframe(team_model, use_container_width=True)

with tabs[3]:
    st.subheader("Cito Checks")
    st.write("Schedule rows:", len(schedule)); st.dataframe(schedule, use_container_width=True)
    st.write("Recent match rows:", len(recent)); st.dataframe(recent, use_container_width=True)
    st.write("Player/map stat rows:", len(stats)); st.dataframe(stats.head(500), use_container_width=True)
    calls=[]
    for c in schedule_calls: calls.append({"Type":"schedule","URL":c["url"],"Status":c["status"],"OK":c["ok"]})
    for c in recent_calls: calls.append({"Type":"recent","URL":c["url"],"Status":c["status"],"OK":c["ok"]})
    for c in stat_calls: calls.append({"Type":"player-stats","URL":c["url"],"Status":c["status"],"OK":c["ok"]})
    st.dataframe(pd.DataFrame(calls), use_container_width=True)
    ep=st.text_input("Test Cito path", "/matches?limit=5&season=2026")
    if st.button("Test path"):
        path, params = (ep.split("?",1)+[""])[:2] if "?" in ep else (ep,"")
        paramdict=dict([p.split("=",1) for p in params.split("&") if "=" in p])
        res=cito_get(path,paramdict); st.write(res["status"],res["ok"],res["url"]); st.json(res["payload"])

with tabs[4]:
    st.subheader("Intel Notes")
    st.session_state["intel"]=st.text_area("Paste Twitter/Reddit/YouTube/analyst notes here", value=st.session_state["intel"], height=260)
    st.info("This applies small adjustments when a player/team is mentioned with obvious positive/negative wording. It does not scrape social media live.")

with tabs[5]:
    st.subheader("Debug")
    with st.expander("Schedule call payloads"):
        for c in schedule_calls: st.write(c["url"], c["status"], c["ok"]); st.json(c["payload"])
    with st.expander("Recent call payloads"):
        for c in recent_calls: st.write(c["url"], c["status"], c["ok"]); st.json(c["payload"])
    with st.expander("First stat call samples"):
        for c in stat_calls[:3]: st.write(c["url"], c["status"], c["ok"]); st.json(c["payload"])

st.caption("Important: this ranks player targets from recent completed Cito map stats. It is analysis, not guaranteed profit.")
