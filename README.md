# CDL Cito Hybrid v4

This is the Cito-powered version of the CDL analyser.

## What it does

- Reads `CITO_API_KEY` securely from Streamlit Secrets.
- Pulls Cito schedule/live/team/player endpoints where available.
- Falls back to Breaking Point fixtures and rosters if Cito is missing or incomplete.
- Lets you select a match.
- Lets you enter/update map vetoes and map picks.
- Ranks players by match, mode and map.
- Shows best 2 / 3 / 4 player targets.
- Shows avoid / low confidence list.
- Has an API explorer tab so endpoint responses can be inspected.
- Has a social/intel notes box for Twitter, Reddit, YouTube, analyst notes or roster news.

## Streamlit Secrets

Do **not** put the API key in GitHub.

In Streamlit:

`Manage app -> Settings -> Secrets`

Add:

```toml
CITO_API_KEY = "your_new_cito_key_here"
```

Then reboot the app.

## GitHub files

Upload/replace these files:

- `app.py`
- `requirements.txt`
- `README.md`

## Important

This app does not place bets and does not guarantee profit. It is an analysis dashboard.

For best results:
1. Use Cito stats where available.
2. Refresh data only when needed to avoid wasting API calls.
3. Enter map vetoes when they are announced.
4. Paste relevant social/news notes into the Intel tab.
