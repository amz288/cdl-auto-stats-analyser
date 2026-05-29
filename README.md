# CDL Analyst v9 — Black Ops 7 / CDL 2026

A genuine upgrade over the v8 ChatGPT build. Same Streamlit foundation, but with the bugs that were biting you fixed.

## What's new vs v8

| Issue in v8 | Fix in v9 |
|---|---|
| Wrong rosters (aBeZy still on FaZe etc.) | **All 12 CDL 2026 rosters verified and baked in as ground truth.** Source: 100thieves.com, esportsinsider, esportsbets, prismnews (Nov 2025). Editable from the new **Rosters** tab and saved to `roster_overrides.json`. |
| Map names typed by hand | **Full BO7 map pool dropdown** for HP / S&D / Overload. |
| Today's matches sometimes missing | **Manual fixture adder** on the Dashboard — type the teams, time, event, save. Persisted to `manual_matches.json`. |
| Endpoints were partly guessed | **Rewritten against the real Cito spec** (`api.citoapi.com/api/v1/cod`, `x-api-key` header, `matches/{id}/player-stats?includeMaps=true`, etc.). |
| 500-token paranoia | **500 is daily, not lifetime.** Added a usage tracker in the sidebar (`cito_usage.json`). |
| No EV calc despite being the point | **EV Calculator tab** with kill samples → projection → fair price vs offered odds → Kelly stake. |
| Reliance on Breaking Point scrape | Removed — BP is bot-protected and was silently failing. |

## Files

- `app.py` — main Streamlit app (~1100 lines)
- `requirements.txt` — `streamlit`, `pandas`, `requests`
- `saved_analysis_cache.json` — auto-created
- `roster_overrides.json` — auto-created
- `manual_matches.json` — auto-created
- `cito_usage.json` — auto-created

## Streamlit Cloud setup

1. Upload `app.py` + `requirements.txt` to your GitHub repo (replacing v8).
2. In Streamlit Cloud → App settings → Secrets, set:
   ```toml
   CITO_API_KEY = "your_key_here"
   ```
3. Reboot the app.

## Tabs

1. **Dashboard** — Cito fixtures + manual fixtures, map editor, load/save analysis
2. **Manual Match** — Pure offline workflow when vetoes are known
3. **EV Calculator** — Per-bet edge & stake, ranking, Best 2/3/4
4. **Intel Notes** — Pasted reads, sentiment-adjusted scores
5. **Rosters** — Edit verified rosters when players move mid-season
6. **Saved** — Browse cached analyses (0-call reuse)
7. **Diagnostics** — Endpoint tester, call logs, raw data

## Honest limits

- **No live BetMGM scrape.** Their site is auth+geo-locked. You paste odds and lines into the EV tab; the tool does the maths.
- **No Breaking Point scrape.** They block bots. Use the baked-in rosters and override if needed.
- **Cito endpoints can drift.** If Diagnostics shows 404s, the endpoint name may have changed. Use the manual tester to find what works and tell me.
- **Predictions are model estimates, not certainties.** Even +EV bets lose plenty.

18+ · BeGambleAware.org · GamCare 0808 8020 133
