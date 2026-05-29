import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

st.set_page_config(page_title="CDL AI Analyst v9", layout="wide")

st.markdown("""
<style>
.stApp {
    background: radial-gradient(circle at top left, #121827 0, #080B12 38%, #03050A 100%);
    color: #F8FAFC;
}
h1, h2, h3 { letter-spacing: -0.02em; }
.hero {
    padding: 26px;
    border-radius: 26px;
    border: 1px solid rgba(255,91,4,.34);
    background: linear-gradient(135deg, rgba(255,91,4,.15), rgba(15,23,42,.88));
    box-shadow: 0 24px 70px rgba(0,0,0,.38);
    margin-bottom: 18px;
}
.hero-title {
    font-size: 46px;
    font-weight: 950;
    line-height: 1;
    margin-bottom: 10px;
}
.hero-sub {
    color: #CBD5E1;
    font-size: 16px;
    line-height: 1.55;
}
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
.pick-card {
    border: 1px solid rgba(34,197,94,.28);
    border-radius: 20px;
    padding: 16px;
    background: linear-gradient(135deg, rgba(34,197,94,.11), rgba(15,23,42,.82));
    min-height: 170px;
}
.risk-card {
    border: 1px solid rgba(239,68,68,.25);
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
    color: #CBD5E1;
    font-size: 12px;
    margin-right: 6px;
    margin-bottom: 6px;
}
.good { color:#22C55E; }
.mid { color:#F59E0B; }
.bad { color:#EF4444; }
.muted { color:#94A3B8; }
.big-score { font-size:34px; font-weight:900; }
div[data-testid="stMetric"] {
    background: rgba(15,23,42,.72);
    border: 1px solid rgba(148,163,184,.16);
    padding: 16px;
    border-radius: 18px;
}
textarea, input {
    border-radius: 12px !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="hero-title">CDL <span class="accent">AI Analyst v9</span></div>
  <div class="hero-sub">
    Claude-style workflow: build the match, enter maps, press one button, then OpenAI searches the web and returns a match-centre style analysis.
    Nothing expensive runs unless you press <b>Run AI Analysis</b> or <b>Force Refresh</b>.
  </div>
</div>
""", unsafe_allow_html=True)

CACHE_FILE = Path("ai_analysis_cache.json")

TEAMS = [
    "Boston Breach", "Carolina Royal Ravens", "Cloud9 New York", "FaZe Vegas",
    "G2 Minnesota", "Los Angeles Thieves", "Miami Heretics", "OpTic Texas",
    "Paris Gentle Mates", "Riyadh Falcons", "Toronto KOI", "Vancouver Surge",
]

MODES = ["Hardpoint", "Search & Destroy", "Overload", "Hardpoint", "Search & Destroy"]

def default_maps():
    return pd.DataFrame({
        "Map": [1, 2, 3, 4, 5],
        "Mode": MODES,
        "Map Name": ["", "", "", "", ""],
        "Picked By": ["", "", "", "", ""],
    })

def safe(x):
    return "" if x is None else str(x).strip()

def short_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def now():
    return datetime.now().strftime("%d %b %Y %H:%M")

def load_cache():
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")

def get_secret(name):
    try:
        return st.secrets.get(name, "")
    except Exception:
        return ""

def maps_to_text(df):
    lines = []
    for _, r in df.iterrows():
        lines.append(f"Map {int(r['Map'])}: {safe(r['Mode'])} | Map name: {safe(r['Map Name']) or 'unknown'} | Picked by: {safe(r['Picked By']) or 'unknown'}")
    return "\n".join(lines)

def make_cache_key(team_a, team_b, maps_df, notes, model):
    raw = f"{team_a}|{team_b}|{maps_to_text(maps_df)}|{notes}|{model}"
    return short_hash(raw)

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
            return None
    return None

def build_prompt(team_a, team_b, maps_df, notes):
    return f"""
You are a Call of Duty League analyst. Produce a practical match analysis for the upcoming or current CDL matchup below.

MATCH:
{team_a} vs {team_b}

MAPS / VETO INFO:
{maps_to_text(maps_df)}

USER INTEL NOTES:
{notes or "No extra user notes supplied."}

Use web search to look for current CDL information, including:
- official CDL or event schedule pages
- Breaking Point
- recent match results
- roster status
- team form
- player form
- map/mode tendencies
- public social/news context where accessible
- YouTube/Reddit/X context only if accessible via public web results

Important:
- Do not invent unavailable facts.
- If map data is missing, explain confidence is lower.
- Treat this as analysis only, not guaranteed betting advice.
- Prefer practical recommendations: best 2, best 3, best 4 player targets, map-by-map picks, avoid/risk players.
- If evidence is weak, say that.
- Do not over-focus on odds unless the user supplied odds.
- Use citations/source names in reasoning if available.

Return ONLY valid JSON in this schema:

{{
  "match_title": "{team_a} vs {team_b}",
  "summary": "short summary",
  "team_a_win_probability": 0.00,
  "team_b_win_probability": 0.00,
  "model_pick": "team name",
  "confidence": "High/Medium/Low",
  "key_context": [
    "fact/context 1",
    "fact/context 2",
    "fact/context 3"
  ],
  "best_2": [
    {{"player":"", "team":"", "reason":"", "confidence":"High/Medium/Low"}}
  ],
  "best_3": [
    {{"player":"", "team":"", "reason":"", "confidence":"High/Medium/Low"}}
  ],
  "best_4": [
    {{"player":"", "team":"", "reason":"", "confidence":"High/Medium/Low"}}
  ],
  "per_map": [
    {{"map":1, "mode":"", "map_name":"", "favoured_team":"", "top_player":"", "reason":"", "confidence":"High/Medium/Low"}}
  ],
  "avoid_or_risk": [
    {{"player":"", "team":"", "reason":"", "risk":"High/Medium/Low"}}
  ],
  "sources_used": [
    "source/site name or search result used"
  ],
  "final_note": "short responsible note"
}}
"""

def run_openai_analysis(api_key, model, team_a, team_b, maps_df, notes, require_search=True):
    if OpenAI is None:
        raise RuntimeError("The openai package is not installed. Add openai to requirements.txt.")
    client = OpenAI(api_key=api_key)
    prompt = build_prompt(team_a, team_b, maps_df, notes)

    # New Responses API hosted web search. If web_search is not available on the account/model,
    # fall back to web_search_preview, then finally text-only.
    tool_choice = "required" if require_search else "auto"
    attempts = [
        {"tools": [{"type": "web_search"}], "tool_choice": tool_choice},
        {"tools": [{"type": "web_search_preview"}], "tool_choice": tool_choice},
        {"tools": [], "tool_choice": "none"},
    ]

    last_error = None
    for a in attempts:
        try:
            kwargs = {
                "model": model,
                "input": prompt,
                "temperature": 0.2,
            }
            if a["tools"]:
                kwargs["tools"] = a["tools"]
                kwargs["tool_choice"] = a["tool_choice"]
            resp = client.responses.create(**kwargs)
            return resp.output_text, {"attempt": a, "model": model}
        except Exception as e:
            last_error = str(e)
    raise RuntimeError(last_error or "OpenAI analysis failed.")

def conf_class(conf):
    c = safe(conf).lower()
    if "high" in c:
        return "good"
    if "low" in c:
        return "bad"
    return "mid"

def render_pick_list(title, picks):
    st.markdown(f"### {title}")
    if not picks:
        st.info("No picks returned.")
        return
    cols = st.columns(min(len(picks), 4))
    for i, p in enumerate(picks[:4]):
        with cols[i]:
            cls = conf_class(p.get("confidence"))
            st.markdown(f"""
<div class="pick-card">
  <div class="muted">#{i+1} Target</div>
  <h3 style="margin: 6px 0;">{safe(p.get("player")) or "Unknown"}</h3>
  <span class="pill">{safe(p.get("team")) or "Unknown team"}</span>
  <span class="pill {cls}">{safe(p.get("confidence")) or "Medium"}</span>
  <p style="margin-top:10px; color:#CBD5E1;">{safe(p.get("reason"))}</p>
</div>
""", unsafe_allow_html=True)

def render_analysis(data, raw_text=""):
    if not data:
        st.error("AI returned text, but it was not valid JSON. Raw output below.")
        st.code(raw_text[:5000])
        return

    title = safe(data.get("match_title")) or "Match Analysis"
    summary = safe(data.get("summary"))
    confidence = safe(data.get("confidence")) or "Medium"
    model_pick = safe(data.get("model_pick"))

    st.markdown(f"""
<div class="match-card">
  <div class="muted">AI Match Centre</div>
  <h2 style="margin: 6px 0;">{title}</h2>
  <span class="pill">Model pick: {model_pick or "Unknown"}</span>
  <span class="pill {conf_class(confidence)}">Confidence: {confidence}</span>
  <p style="margin-top:12px;color:#CBD5E1;">{summary}</p>
</div>
""", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    ta = data.get("team_a_win_probability", 0)
    tb = data.get("team_b_win_probability", 0)
    try: ta_pct = round(float(ta) * 100)
    except Exception: ta_pct = 0
    try: tb_pct = round(float(tb) * 100)
    except Exception: tb_pct = 0
    c1.metric("Team A win probability", f"{ta_pct}%")
    c2.metric("Model pick", model_pick or "Unknown")
    c3.metric("Team B win probability", f"{tb_pct}%")

    ctx = data.get("key_context", [])
    if ctx:
        st.markdown("### Key context")
        for item in ctx[:6]:
            st.markdown(f"- {safe(item)}")

    render_pick_list("Best 2", data.get("best_2", []))
    render_pick_list("Best 3", data.get("best_3", []))
    render_pick_list("Best 4", data.get("best_4", []))

    per_map = data.get("per_map", [])
    st.markdown("### Per-map recommendations")
    if per_map:
        for m in per_map:
            st.markdown(f"""
<div class="card">
  <div class="muted">Map {safe(m.get("map"))} · {safe(m.get("mode"))} · {safe(m.get("map_name")) or "unknown map"}</div>
  <h3 style="margin: 6px 0;">Top player: <span class="accent">{safe(m.get("top_player")) or "Unknown"}</span></h3>
  <span class="pill">Favoured team: {safe(m.get("favoured_team")) or "Unknown"}</span>
  <span class="pill {conf_class(m.get("confidence"))}">Confidence: {safe(m.get("confidence")) or "Medium"}</span>
  <p style="margin-top:10px;color:#CBD5E1;">{safe(m.get("reason"))}</p>
</div>
""", unsafe_allow_html=True)
    else:
        st.info("No per-map output returned.")

    risks = data.get("avoid_or_risk", [])
    st.markdown("### Avoid / risk")
    if risks:
        for r in risks:
            st.markdown(f"""
<div class="risk-card">
  <b>{safe(r.get("player")) or "Unknown"}</b> <span class="muted">({safe(r.get("team"))})</span>
  <span class="pill bad">Risk: {safe(r.get("risk")) or "Medium"}</span>
  <p style="margin-top:8px;color:#CBD5E1;">{safe(r.get("reason"))}</p>
</div>
""", unsafe_allow_html=True)
    else:
        st.info("No avoid/risk list returned.")

    sources = data.get("sources_used", [])
    if sources:
        st.markdown("### Sources / context used")
        for s in sources:
            st.markdown(f"- {safe(s)}")

    if data.get("final_note"):
        st.caption(safe(data.get("final_note")))

if "cache" not in st.session_state:
    st.session_state.cache = load_cache()
if "notes" not in st.session_state:
    st.session_state.notes = ""
if "active_key" not in st.session_state:
    st.session_state.active_key = ""

with st.sidebar:
    st.header("Setup")
    api_key = get_secret("OPENAI_API_KEY")
    st.write("OpenAI key:", "✅ found" if api_key else "❌ missing")
    model = st.text_input("OpenAI model", value="gpt-5.5")
    require_search = st.checkbox("Require web search", value=True)
    st.write(f"Saved AI analyses: **{len(st.session_state.cache)}**")
    st.info("AI calls only run when you press Run AI Analysis or Force Refresh.")
    if st.button("Delete saved AI cache"):
        st.session_state.cache = {}
        save_cache({})
        st.rerun()

tabs = st.tabs(["AI Match Centre", "Manual Match Builder", "Saved Analyses", "Intel Notes", "Raw Output / Debug"])

with tabs[0]:
    st.markdown("## AI Match Centre")
    c1, c2 = st.columns(2)
    with c1:
        team_a = st.selectbox("Team A", TEAMS, index=TEAMS.index("OpTic Texas") if "OpTic Texas" in TEAMS else 0, key="team_a_main")
    with c2:
        team_b = st.selectbox("Team B", TEAMS, index=TEAMS.index("Los Angeles Thieves") if "Los Angeles Thieves" in TEAMS else 1, key="team_b_main")

    if team_a == team_b:
        st.error("Choose two different teams.")
    else:
        if "maps_main" not in st.session_state:
            st.session_state.maps_main = default_maps()

        st.markdown("### Maps / vetoes")
        maps_df = st.data_editor(
            st.session_state.maps_main,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "Mode": st.column_config.SelectboxColumn("Mode", options=MODES),
                "Picked By": st.column_config.SelectboxColumn("Picked By", options=["", team_a, team_b, "League/Default"]),
            },
            key="maps_editor_main",
        )
        st.session_state.maps_main = maps_df

        key = make_cache_key(team_a, team_b, maps_df, st.session_state.notes, model)
        saved = st.session_state.cache.get(key)

        st.markdown(f"""
<div class="card">
  <b>{team_a}</b> vs <b>{team_b}</b><br>
  <span class="muted">Cache key: {key}</span>
</div>
""", unsafe_allow_html=True)

        if saved:
            st.success(f"Saved AI analysis found — saved {saved.get('saved_at')}. Cost to view: 0 API calls.")
        else:
            st.warning("No saved AI analysis for this exact teams/maps/notes setup.")

        b1, b2, b3 = st.columns(3)
        with b1:
            run = st.button("Run AI Analysis", disabled=not bool(api_key))
        with b2:
            use_saved = st.button("Use Saved Analysis", disabled=not bool(saved))
        with b3:
            force = st.button("Force Refresh AI", disabled=not bool(api_key))

        if run or force:
            with st.spinner("Running OpenAI web-search analysis..."):
                try:
                    raw, meta = run_openai_analysis(api_key, model, team_a, team_b, maps_df, st.session_state.notes, require_search)
                    parsed = extract_json(raw)
                    st.session_state.cache[key] = {
                        "saved_at": datetime.now().strftime("%d %b %Y %H:%M"),
                        "team_a": team_a,
                        "team_b": team_b,
                        "maps": maps_df.fillna("").to_dict(orient="records"),
                        "notes": st.session_state.notes,
                        "model": model,
                        "raw": raw,
                        "parsed": parsed,
                        "meta": meta,
                    }
                    save_cache(st.session_state.cache)
                    st.session_state.active_key = key
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        if use_saved:
            st.session_state.active_key = key

        active = st.session_state.cache.get(key)
        if active:
            render_analysis(active.get("parsed"), active.get("raw",""))

with tabs[1]:
    st.markdown("## Manual Match Builder")
    st.markdown('<div class="card">Same engine, just framed for match-day. Enter the teams, maps and notes, then run the AI once.</div>', unsafe_allow_html=True)
    st.info("Use the AI Match Centre tab above for the actual run. This tab exists as a reminder/workflow: set teams, fill maps, paste notes, run once, then use saved output.")

with tabs[2]:
    st.markdown("## Saved Analyses")
    if not st.session_state.cache:
        st.info("No saved AI analyses yet.")
    else:
        rows = []
        for k, v in st.session_state.cache.items():
            rows.append({
                "Key": k,
                "Saved": v.get("saved_at",""),
                "Team A": v.get("team_a",""),
                "Team B": v.get("team_b",""),
                "Model": v.get("model",""),
                "Has JSON": bool(v.get("parsed")),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df.drop(columns=["Key"]), use_container_width=True)
        selected = st.selectbox("Select saved analysis", [r["Key"] for r in rows])
        c1, c2 = st.columns(2)
        with c1:
            if st.button("View selected saved analysis"):
                st.session_state.active_key = selected
        with c2:
            if st.button("Delete selected saved analysis"):
                st.session_state.cache.pop(selected, None)
                save_cache(st.session_state.cache)
                st.rerun()

        active = st.session_state.cache.get(st.session_state.active_key)
        if active:
            st.markdown("### Active saved analysis")
            render_analysis(active.get("parsed"), active.get("raw",""))

with tabs[3]:
    st.markdown("## Intel Notes")
    st.markdown("""
<div class="card">
Paste anything useful before running the AI. Examples: X/Twitter comments, Reddit threads, YouTube transcript snippets,
Breaking Point notes, CDL broadcast comments, roster rumours, map veto info, illness/sub news.
</div>
""", unsafe_allow_html=True)
    st.session_state.notes = st.text_area(
        "Intel notes",
        value=st.session_state.notes,
        height=280,
        placeholder="Example: Shotzzy frying in HP. LAT likely pick S&D. Dashy looked ill. OpTic struggled on Overload last series.",
    )
    st.warning("Changing notes changes the saved-analysis key. To avoid extra API use, only edit notes before pressing Run AI Analysis.")

with tabs[4]:
    st.markdown("## Raw Output / Debug")
    active = st.session_state.cache.get(st.session_state.active_key)
    if not active:
        st.info("No active AI analysis yet.")
    else:
        st.markdown("### Parsed JSON")
        st.json(active.get("parsed"))
        st.markdown("### Raw AI output")
        st.code(active.get("raw","")[:12000])
        st.markdown("### Metadata")
        st.json(active.get("meta", {}))

st.caption("Analysis only. The app does not place bets and cannot guarantee profit.")
