# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
./run.sh          # creates .venv, installs deps, starts on http://localhost:8001
```

Or manually:
```bash
source .venv/bin/activate
python3 -m uvicorn main:app --reload --port 8001
```

The app is also deployed on Render (auto-deploys on `git push` to main):
- Repo: https://github.com/lakithleelasena/wc2026-fantasy
- Config: `render.yaml` (free tier, Python, `uvicorn main:app --host 0.0.0.0 --port $PORT`)

---

## Architecture

Single-page FastAPI app, no database. All state is fetched live from the public FIFA Fantasy API and cached in-process for 5 minutes (`CACHE_TTL_SECONDS` in `config.py`).

### Data flow

```
FIFA API (players.json + rounds.json)
  → fifa_client.fetch_all_data()       # fetch, enrich, cache
      → history.py                      # curated projections.csv: shares, P(start), set pieces
  → predictor.predict_points()          # ELO-based xFP per game
  → optimizer.optimize_squad()          # PuLP LP → 15 players (projection-file players only)
      → _resolve_day_conflicts()        # post-LP: swap same-day clashes
      → _timing_bench_assign()          # post-LP: early starts, late bench
  → FastAPI routes (main.py)
  → frontend (static/app.js + templates/index.html)
```

### API endpoints

| Route | Description |
|---|---|
| `GET /` | SPA (Jinja2 template) |
| `GET /api/players` | All 1484 enriched players, sorted by predicted_points |
| `POST /api/optimize` | Run LP optimizer, returns 15-player squad |
| `GET /api/groups` | 12 group cards (A–L) with fixtures and team data |
| `GET /api/fixtures` | Raw group-stage rounds/fixtures |
| `GET /api/predicted-results` | Predicted scorelines per group fixture (ELO expected goals) |

---

## Key files

| File | Purpose |
|---|---|
| `config.py` | Squad rules, budget, ELO ratings for all 48 WC2026 teams |
| `fifa_client.py` | Fetches + enriches players; applies projections and day ranks |
| `history.py` | Reads `data/projections.csv` — curated goal/assist shares, P(start), penalty/set-piece flags |
| `scorer.py` | Official FIFA Fantasy WC2026 scoring rules (goals, CS, saves, cards) |
| `predictor.py` | ELO-based expected-points model (see below) |
| `optimizer.py` | PuLP LP solver + post-LP passes (diversity + timing) |
| `models.py` | Pydantic models for all API responses |
| `main.py` | FastAPI routes; wires fifa_client → predictor → optimizer |
| `static/app.js` | Vanilla JS frontend: optimizer view, players table, fixtures tab |
| `static/style.css` | FIFA-blue dark theme |
| `templates/index.html` | Single HTML template (Jinja2, cache-busted) |

---

## Prediction model (`predictor.py` + `scorer.py`)

The model is ELO-driven for team output, with per-player shares/starts/set-piece
duty supplied by the curated projections file. No manual weight sliders.

### Per-game expected fantasy points

For each player × each group-stage match:

1. **Expected goals (team):** `EG = 1.35 + 0.003 × (team_elo − opp_elo)`, clamped [0.3, 4.0]
2. **Clean sheet probability:** `P(CS) = sigmoid(0.5 + 0.002 × (team_elo − opp_elo))`
3. **P(start):** from `data/projections.csv` for covered teams; else price-tiered fallback ($10m+ → 97%, $8m → 85%, $6m → 55%, $4.5m → 20%)
4. **Goal/assist share:** from `projections.csv` for covered teams; else price-weighted within each (team, position) group
5. **Penalty / set-piece bonus:** additive xG/xA for designated takers (see below)
6. **xFP:** multiply out using official FIFA Fantasy scoring rules from `scorer.py`

```
xFP = pts_appearance × P(start)
    + pts_goal × xG × P(start)            # xG includes penalty/set-piece bonus
    + pts_assist × xA × P(start)          # xA includes set-piece bonus
    + pts_clean_sheet × P(CS) × P(start)
    + pts_goals_conceded_penalty × eg_against × P(start)   # GKP/DEF only
    + card_deduction × P(start)
    + save_bonus   # GKP only, ~3.5 saves/game
```

### Curated projections (`data/projections.csv` via `history.py`)

For the covered national teams, this file is the single source of truth — it
replaces the old API-Football history and the price-based proxies. Columns:
`Team, Player, Position, P_Start, Expected_Minutes, Goal_Share_Pct,
Assist_Share_Pct, Penalty_Taker (Y/N), Set_Pieces (Primary/Secondary/N)`.

Players are matched to FIFA Fantasy by team + surname; position is only a
tiebreaker for same-surname teammates (FIFA and the file disagree on many
MID/FWD labels). Players/teams not in the file fall back to price-based shares
and the price-tier P(start).

**Additive bonuses** (per game, before P(start) and scoring multipliers; constants in `history.py`):
- Penalty `Y`: +0.20 team xG, split equally among the team's takers
- Set piece `Primary`: +0.04 xG, +0.12 xA
- Set piece `Secondary`: +0.02 xG, +0.06 xA

### Official scoring rules (stored in `scorer.py`)

| Event | GKP | DEF | MID | FWD |
|---|---|---|---|---|
| Appearance (60+ min) | +2 | +2 | +2 | +2 |
| Goal | +10 | +8 | +6 | +5 |
| Assist | +3 | +3 | +3 | +3 |
| Clean sheet | +6 | +6 | +1 | 0 |
| Goals conceded (per 2) | −1 | −1 | 0 | 0 |
| Yellow card | −1 | −1 | −1 | −1 |
| Red card | −3 | −3 | −3 | −3 |
| Save (per 3) | +1 | — | — | — |

`predicted_points` = sum of per-game predictions across all 3 group matches.
`predicted_g1/g2/g3` are stored separately so the UI can show them individually (turning to actual points once a game is played).

---

## Squad optimizer (`optimizer.py`)

### Step 1: LP (PuLP, HiGHS solver — ARM-native, CBC fallback)

The candidate pool is restricted to players present in `data/projections.csv`
(`in_projection` flag); players outside the file are never selected. Selects
the best 15 maximising predicted_points of the starting XI subject to:
- Squad: exactly 2 GKP, 5 DEF, 5 MID, 3 FWD
- Starting XI: 11 players (min 1 GKP, 3 DEF, 2 MID, 1 FWD)
- Budget ≤ `req.budget` (stored as 10× display, e.g. 1000 = $100m)
- Max 3 players from any single national team

Restricting the pool shrinks the substitution options, so the day-diversity
pass (Step 2) may leave more unresolved clashes than with the full roster.

### Step 2: Day-diversity conflict resolution

FIFA Fantasy allows mid-round substitutions — you can swap a player in before they kick off in the same round. This only works if your bench players play on *different days* than your starters.

Rule: **no two players in the same position group (GKP/DEF/MID/FWD) should play on the same day in any of the 3 group-stage rounds.**

Algorithm (iterative, up to 50 passes):
1. Find any same-day clash within a position group
2. Identify the weaker player (lower `predicted_points`) in the clash
3. Find the next-best unselected player of the same position who:
   - Doesn't clash with remaining position-group players in any round
   - Fits within the remaining budget
   - Doesn't violate the 3-per-team cap
4. Swap. Repeat until no conflicts or none are resolvable.

Unresolvable conflicts (e.g. budget too tight) are returned as warning strings and shown as an amber banner in the UI.

### Step 3: Timing-aware bench assignment

Among the 15 selected players:
- **GKP:** earlier-playing starts, later-playing benches
- **Outfield:** mandatory formation minimums (3 earliest DEF, 2 earliest MID, 1 earliest FWD) start; from the remaining 7 — the 4 earliest-playing start, the 3 latest-playing bench

"Earliest/latest" = day rank within Round 1 (1 = first match day of the round, 8 = last).

Round 1 has 8 match days (Jun 11–18). Round 2 has 7. Round 3 has only 5. Bench players ideally play on the final day(s) so any early-playing starter who underperforms can be subbed out before the bench player kicks off.

---

## Data pipeline details (`fifa_client.py`)

### Per-player enrichment

Each player dict gets:
- `team_strength` — ELO rating normalised 0–1 (Spain=1.0, Qatar=0.0)
- `fixture_ease` — avg weakness of 3 group opponents `mean(1 − opp_strength)`
- `cost` — price × 10 (integer, for LP budget arithmetic)
- `round_opponents` — `{"1": "Algeria", "2": "France", "3": "Brazil"}`
- `round_dates` — `{"1": "2026-06-14", "2": "2026-06-20", "3": "2026-06-26"}`
- `round_day_ranks` — `{"1": 4, "2": 2, "3": 5}` — day position within each round
- `round_day_count` — `{"1": 8, "2": 7, "3": 5}` — total match days in each round
- `goal_share` / `assist_share` — fraction of team goals/assists (projections file, else price-weighted)
- `xg_bonus` / `xa_bonus` — additive penalty/set-piece xG/xA (0 if not a designated taker)
- `in_projection` — `True` if the player is in `data/projections.csv` (gates optimizer + UI highlight)
- `round_scores` — actual fantasy points per round once played `{"1": 7, "2": 3, ...}`

### ELO ratings (`config.py`)

All 48 WC2026 teams have hand-curated ELO ratings from eloratings.net/2026_World_Cup, frozen at tournament start. Range: 1421 (Qatar) → 2157 (Spain). Team names must match the FIFA Fantasy API squad names exactly.

---

## Frontend notes

- **Tabs:** Squad Optimizer / All Players / Group Fixtures / Predicted Results
- **Player cards** (optimizer view): show position badge, name, team, per-game rows with opponent + date + day-rank (e.g. `Jun 17 D7/8`) + predicted/actual pts, total, cost. Captain = C badge (blue), vice = V badge (cyan).
- **Players table:** sortable by clicking any column header (▲/▼). G1/G2/G3 columns show actual pts (green) once played, predicted (muted italic) before. Players in `projections.csv` show name + country in cyan (`.proj-player`).
- **Group Fixtures tab:** 12 group cards (A–L), each showing team standings with ELO strength bars and fixture list with scores/dates.
- **Predicted Results tab:** per-group cards listing each fixture's predicted scoreline (ELO expected goals), sorted by date.
- **Conflict banner:** amber warning shown below squad if any same-day position clashes couldn't be resolved.

## Cost encoding

Costs stored internally as integers 10× display value (e.g. `60` = $6.0m). `PlayerOut.cost` in API responses is the display value (float). Raw 10× value used in LP budget constraints.

## No tests exist yet

The `.venv/` directory is excluded from git.
