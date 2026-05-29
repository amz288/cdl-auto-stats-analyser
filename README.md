# CDL One-Click Analyst v13

This version is simplified for match day.

## Workflow

1. Click `Refresh match list`
   - Gets current/live/upcoming matches from Cito, Breaking Point and OpenAI web search.

2. Select a match.

3. Click `Refresh maps/vetoes` when maps become available.
   - Tries Cito first.
   - Then uses OpenAI web search.
   - Keeps default CDL map format if maps are not found.

4. Click `Analyse this match`
   - Pulls Cito rosters/player stats.
   - Uses Breaking Point roster fallback.
   - Uses OpenAI web research for current form, live context, maps/vetoes and BetMGM odds discovery.
   - Shows best players, player kill targets, map winner leans, best bets and avoid/risk.

## Streamlit Secrets

```toml
CITO_API_KEY = "your_cito_key_here"
OPENAI_API_KEY = "your_openai_key_here"
```

## Upload

Upload these files to the root of your GitHub repo:

- app.py
- requirements.txt
- README.md

Then reboot Streamlit.


## v13 changes

- Stronger live/in-play match search.
- Adds Force live match search button.
- Adds full 8-player ranking, rank 1 best to rank 8 worst.
- Adds saved-analysis quick loader so you can reload without spending more OpenAI/Cito calls.
- Adds Cito health check diagnostics so you can see whether Cito returns 200, 401/403, 404 or 0 rows.
- Analysis still auto-saves after it runs once.
