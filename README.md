# CDL Analyst v6

Manual upload version.

## Key fixes

- Uses `Authorization: Bearer <CITO_API_KEY>` for Cito, plus `x-api-key` as fallback.
- Filters to known CDL teams.
- Uses Cito `/players` and `/players/{player}/stats` where available.
- Falls back to Breaking Point rosters/matches if Cito does not return clean rows.
- Includes map/veto updater and Best 2 / 3 / 4 output.
- Includes diagnostics so failed Cito calls are visible.

## Streamlit Secret

In Streamlit:

```toml
CITO_API_KEY = "your_key_here"
```

## Upload

Replace these files in GitHub:

- `app.py`
- `requirements.txt`
- `README.md`

Then reboot Streamlit.
