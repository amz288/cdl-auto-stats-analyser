# CDL Match-Day Analyst — FINAL

Black Ops 7 / CDL 2026. No Cito. Built around the sources that actually work.

## Setup (Streamlit Cloud)

1. Replace `app.py` and `requirements.txt` in your repo with these.
2. Settings → Secrets, set just:
   ```toml
   OPENAI_API_KEY = "sk-..."
   ```
   (Polymarket and Breaking Point need no key.)
3. Reboot the app.

## Data sources

- **OpenAI web search** — live + upcoming matches, current form, per-mode player stats, full analysis. Reads breakingpoint.gg, callofdutyleague.com, cod-esports.fandom.com, news, X.
- **Breaking Point** — scraped directly from your Streamlit server for the match list (works there even though it's bot-blocked elsewhere).
- **Polymarket Gamma API** — free, no key, crowd win probabilities as a cross-check.
- **Verified 2026 rosters + priors** — baked in, so the player list and projections never go blank.

## Workflow

1. **Refresh matches** — live games shown first, then the next ~10 days.
2. **Select a match.**
3. **Pick the 5 maps** — modes are fixed (HP / SnD / OVL / HP / SnD); map names are dropdowns from the **current** BO7 pool taken from the official @intelCDL maps & modes graphic:
   - **Hardpoint:** Sake, Colossus, Den, Scar, Gridlock, Hacienda
   - **Search & Destroy:** Den, Gridlock, Raid, Fringe, Sake, Hacienda
   - **Overload:** Den, Exposure, Scar, Gridlock
   Fill them in as vetoes drop on Twitter/X.
4. **Analyse** — pulls per-mode stats, blends Polymarket odds, returns: series pick + win %, full 8-player kill ranking, per-map top targets, map-winner leans, best bets, avoid list. Auto-saves so re-viewing costs 0 calls.
5. **EV Calculator tab** — paste recent kills + BetMGM line + odds → projection, edge, EV %, fractional-Kelly stake, best 2/3/4.

## Honest limits

- Public sites publish per-**mode** player stats, not per-**map**. When you pick a map, the tool shows that player's stats for that **mode** (e.g. Map 1 Hardpoint → their Hardpoint average), adjusted for who picked the map and form. It does **not** fabricate map-specific kill numbers.
- Stat conversions: Hardpoint projected kills ≈ kills-per-10-min × 2.5; S&D ≈ kills-per-round × 11. Rough but reasonable.
- Predictions are estimates. No bets placed. Odds can be unavailable or move. 18+ · BeGambleAware.org · GamCare 0808 8020 133.

## If something breaks

- **No matches found:** OpenAI search occasionally returns nothing — hit Refresh again. Breaking Point scrape is best-effort.
- **Polymarket shows nothing:** there may be no live CDL market for that exact fixture; that's normal.
- **Stats look like priors only:** the web stat fetch didn't find numbers; the analysis still runs on baked-in priors.
