# CDL Cito Hybrid v5

This version fixes the v4 issue.

v4 used selected upcoming match stats, but upcoming matches usually have no stat rows yet. v5 instead builds a model from recent completed Cito map/player stats and applies it to upcoming matches.

## Upload to GitHub

Replace:

- app.py
- requirements.txt
- README.md

Then reboot Streamlit.

## Streamlit secret

Do not put the API key in GitHub. Add it in Streamlit Secrets:

```toml
CITO_API_KEY = "your_key_here"
```
