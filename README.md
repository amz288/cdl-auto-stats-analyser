# CDL One-Click Analyst v14

Drop-in replacement for [amz288/cdl-auto-stats-analyser](https://github.com/amz288/cdl-auto-stats-analyser) v13.

## Upload

Replace `app.py` and `requirements.txt` in the repo root with the files in this bundle. Keep your existing Streamlit secrets:

```
CITO_API_KEY   = "..."
OPENAI_API_KEY = "..."
```

Reboot the Streamlit app. Saved analyses from v13 won't carry over (new cache filenames), but new ones will start saving immediately.

## What v14 fixes

1. **LA Guerrillas M8 added** — was completely missing from `TEAMS` in v13, so the team and its players never appeared anywhere.
2. **Verified 2026 rosters baked in** as ground truth. Cito stats *augment* the player list rather than *replace* it, so the roster is never blank even when Cito returns nothing.
3. **BO7 map pool baked in.** The maps editor uses dropdowns from the real Black Ops 7 pool (Protocol / Cortex / Skyline / Toshin / Exposure / Imprint per mode). The AI and Cito are validated against the pool, so stale BO6 map names are rejected.
4. **Full PRIORS table** — every verified player has Hardpoint / SnD / Overload prior scores. Fallback profiles no longer blank out for unfamiliar names.
5. **Manual map veto picker** — when both Cito and the AI fail (vetoes drop ~10 min before start), you can pick the 5 maps yourself from the pool in 5 clicks.
6. **EV Calculator tab** — paste BetMGM line + odds + recent kills, get fair price, edge, EV %, fractional-Kelly stake. Best 2 / 3 / 4 ranking.
7. **Roster correction pass on AI output** — if the AI says "aBeZy on FaZe", the app silently moves him to LA Thieves before rendering. Cards show "· corrected" when this happens.
8. **AI prompt now includes verified rosters as ground truth** so it stops hallucinating moved players in the first place.

## Tabs

- **🎯 Match Day** — main workflow (refresh → select → maps → analyse).
- **💰 EV Calculator** — prop edge maths.
- **👥 Rosters** — view and override verified rosters.
- **🔬 Diagnostics** — Cito health check, recent API calls.

## Honest limits

- The AI reads public sources. Live BetMGM odds and live in-play state are best-effort, often partial.
- Breaking Point is bot-blocked from this kind of fetch — it sometimes returns nothing and that is normal.
- Predictions are estimates. No bet placed, no profit guarantee. 18+ · BeGambleAware.org · GamCare 0808 8020 133.
