# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
./run.sh          # creates .venv, installs deps, starts on http://localhost:8001
```

Or manually:
```bash
source .venv/bin/activate
uvicorn main:app --reload --port 8001
```

## Architecture

This is a single-page FastAPI app with no database. All state is fetched live from the public FIFA Fantasy API and cached in-process for 5 minutes (`CACHE_TTL_SECONDS` in `config.py`).

**Data flow:**
1. `fifa_client.fetch_all_data()` — fetches `players.json` + `rounds.json` from `play.fifa.com/json/`, enriches each player with `team_strength` (FIFA ranking proxy) and `fixture_ease` (average opponent weakness across 3 group matches), and caches the result.
2. `predictor.predict_points()` — takes an enriched player dict and computes a `predicted_points` score as a weighted sum of 4 signals (team_strength, fixture_ease, form, position_role), scaled to ~0–30 pts.
3. `optimizer.optimize_squad()` — runs a PuLP LP solver to pick the optimal 15-player squad (11 starters + 4 bench) maximising starter predicted points subject to budget, position quota, and max-3-per-national-team constraints.
4. `main.py` — FastAPI routes wire these together; the frontend in `static/app.js` + `templates/index.html` calls `/api/players`, `/api/optimize`, and `/api/fixtures`.

**Key constraints (all in `config.py`):**
- Squad: 2 GKP, 5 DEF, 5 MID, 3 FWD; budget 1000 (= $100m, stored as 10×)
- Starting XI minimums: 1 GKP, 3 DEF, 2 MID, 1 FWD
- Max 3 players from any single national team

**Cost encoding:** costs are stored internally as integers 10× the display value (e.g. `60` = $6.0m). `PlayerOut.cost` is the display value (float). The raw `10×` value is used in LP budget constraints.

**No tests exist yet.** The `.venv/` directory is excluded from git.
