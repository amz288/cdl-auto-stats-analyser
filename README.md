# CDL Analyst v8 - Match Builder + Cache

This is the cleaner v8 version.

## Main features

- Better dark esports-style design.
- Dashboard for upcoming matches.
- Manual Match Builder for team vs team and 5 maps.
- Manual map/veto table.
- Try auto-load maps/vetoes if available from Cito.
- Saved analysis cache using `saved_analysis_cache.json`.
- Uses saved analysis without spending Cito calls.
- Force refresh button only when you want to spend API calls.
- Best 2 / 3 / 4 player target cards.
- Per-map recommendations.
- Intel Notes tab for Twitter/X, Reddit, YouTube, Breaking Point or personal notes.
- Diagnostics tab for Cito calls.

## Low-usage design

These actions do **not** call Cito player stats:

- Selecting a match
- Changing tabs
- Editing maps
- Editing picked-by teams
- Viewing Best 2 / 3 / 4
- Editing Intel Notes

These actions can call Cito:

- Load analysis
- Force refresh analysis
- Try auto-load maps/vetoes
- Manual endpoint tester

## Streamlit Secret

Add this in Streamlit secrets:

```toml
CITO_API_KEY = "your_key_here"
```

## Upload

Upload these files to the root of your GitHub repo:

- app.py
- requirements.txt
- README.md

Then reboot Streamlit.
