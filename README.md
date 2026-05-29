# CDL AI Analyst v9

AI-first version designed to feel closer to Claude's app.

## What changed

- Uses `OPENAI_API_KEY` from Streamlit Secrets.
- Uses OpenAI Responses API with web search.
- Manual teams + 5-map table.
- AI Match Centre generates match analysis, best 2/3/4, per-map picks and avoid/risk list.
- Saves AI output in `ai_analysis_cache.json`.
- Viewing saved analysis costs 0 API calls.
- AI only runs when you press `Run AI Analysis` or `Force Refresh AI`.

## Streamlit Secrets

```toml
OPENAI_API_KEY = "your_openai_api_key_here"
CITO_API_KEY = "optional_cito_key_here"
```

Cito is not required for this v9 AI-first version.

## Upload

Upload these files to the root of your GitHub repo:

- app.py
- requirements.txt
- README.md

Then reboot Streamlit.
