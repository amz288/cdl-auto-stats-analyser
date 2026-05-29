# CDL Hybrid Betting Analyst v11

Final hybrid version.

## What it does

- Pulls CDL matches from Cito, Breaking Point and OpenAI web search.
- Pulls Cito rosters/player stats where available.
- Uses Breaking Point as fallback context/roster/match discovery.
- Uses OpenAI web search for current form, roster news, map context and BetMGM odds discovery.
- Focuses on:
  - player kills per map
  - team to win a map
- Uses decimal odds.
- Saves completed bundles so viewing saved analysis costs 0 extra API calls.
- Only refreshes when you press a refresh button.

## Streamlit secrets

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
