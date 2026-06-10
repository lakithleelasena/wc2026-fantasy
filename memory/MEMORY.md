# WC 2026 Fantasy Optimizer — Project Memory

## Version
Current version: **v0.1**
Version badge location: `templates/index.html` — `<p class="version">v0.1</p>` in the header.
**Rule: update the version number on every release.**

## Project Location
`~/ClaudeApps/wc2026-fantasy/`  
Run locally: `./run.sh` → http://localhost:8001

## Static File Caching
Same pattern as FPL app:
- `_BUILD_TS = int(time.time())` in `main.py` computed at server startup
- Passed as `cache_bust` → `/static/app.js?v=<timestamp>`

## Data Source — FIFA Fantasy API
The official FIFA Fantasy game runs at **https://play.fifa.com/fantasy**

Public JSON endpoints (no auth required):
- `https://play.fifa.com/json/players.json` — 736 players with stats, position, squadId, cost
- `https://play.fifa.com/json/rounds.json` — group stage fixtures (3 rounds)
- `https://play.fifa.com/json/checksums.json` — `{"rounds": false, "players": false}` means WC2026 data not yet published (game launches June 11, 2026)

**Important:** Current data is Women's WC 2023 (all costs = 0). 
Once WC2026 launches (~June 11), costs will be populated with real values.
The `fifa_client.py` defaults cost=60 (=$6.0m) when cost=0.

Backend infrastructure: `backend-fifa.eu.f2p.media.geniussports.com` (via Genius Sports)
The JSON files at `play.fifa.com/json/` are the public-facing cached endpoints.

## Player Data Schema
```json
{
  "id": 1000000002,
  "name": "Player Name",
  "shortName": "Surname",
  "preferredName": "Surname",
  "squadId": 1000000001,
  "cost": 0,
  "position": 1,           // 1=GKP, 2=DEF, 3=MID, 4=FWD
  "status": "unconfirmed", // "confirmed" | "unconfirmed" | "injured"
  "stats": {
    "totalPoints": 9,
    "avgPoints": 3,
    "gamesPlayed": 3,
    "roundScores": {"1": 4, "2": 1, "3": 4},
    "pickedBy": 0.95,      // fraction (multiply ×100 for %)
    "goals": 0, "assists": 0, "cleanSheets": 0, "goalsConceded": 5
  },
  "matchDayPoints": {"1": null, ...}
}
```

## Round Data Schema
```json
{
  "id": 1,
  "stage": "group",
  "status": "complete",
  "startDate": "...",
  "endDate": "...",
  "tournaments": [{
    "id": 1000000001,
    "homeSquadId": 1000000019,
    "awaySquadId": 1000000021,
    "homeSquadName": "Argentina",
    "awaySquadName": "France",
    "homeScore": 2, "awayScore": 1,
    "status": "complete",
    "date": "2026-06-12T..."
  }]
}
```

## Prediction Model (4 signals)
No FPL-style season stats available for a tournament. Signals:

| Signal | Key | Weight |
|---|---|---|
| Team Strength | `team_strength` | 0.30 |
| Fixture Ease | `fixture_ease` | 0.40 |
| Form | `form` | 0.20 |
| Position Role | `position_role` | 0.10 |

- `team_strength`: FIFA world ranking proxy, inverted & normalised 0–1
- `fixture_ease`: average of (1 - opponent_strength) across 3 group games
- `form`: total_points / 30 (capped at 1.0) — updates as tournament progresses
- `position_role`: multiplier (GKP=0.55, DEF=0.65, MID=0.85, FWD=1.0)
- Predicted pts = composite × 30.0 (scale factor)

## Squad Rules (FIFA Fantasy Classic)
- Squad: 15 players (2 GKP, 5 DEF, 5 MID, 3 FWD)
- Starting XI: 11 (min 1 GKP, 3 DEF, 2 MID, 1 FWD)
- Budget: $100m (stored as 1000 in 10× format)
- Max 3 players per national team

## Project Structure
- `main.py` — FastAPI; endpoints: `/api/players`, `/api/optimize`, `/api/fixtures`
- `fifa_client.py` — Fetches + caches players.json & rounds.json (5-min TTL)
- `predictor.py` — 4-signal scoring model
- `optimizer.py` — PuLP LP solver
- `models.py` — Pydantic models
- `config.py` — Constants + FIFA_RANKINGS dict (48 WC teams)
- `templates/index.html` + `static/app.js` + `static/style.css`
- `run.sh` — Local startup (port 8001)

## FIFA Rankings in config.py
Top-48 teams hardcoded in `FIFA_RANKINGS` dict. Update when actual June 2026 rankings published.
When WC2026 data goes live, the squad names returned by the API must match these keys exactly.
Check `squad_id_to_name` mapping from rounds.json if teams aren't scoring correctly.

## Key Known Issues / Next Steps
- Costs are 0 until WC2026 fantasy game launches — client defaults to $6.0m
- Team name matching for FIFA_RANKINGS: API uses full names (e.g. "United States" vs "USA") — may need aliasing
- No Render deployment yet
- No transfer/second-round optimizer yet (focus is group stage for now)
- `round_scores` can be null — model handles Optional[dict]
