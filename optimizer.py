"""
WC2026 Fantasy – Squad Optimizer (PuLP LP solver)

Constraints:
  - 15 players total (2 GKP, 5 DEF, 5 MID, 3 FWD)
  - Starting XI: 11 (1 GKP, at least 3 DEF, 2 MID, 1 FWD)
  - Budget ≤ 1000 (× $0.1m)
  - ≤ MAX_PER_SQUAD players from any one national team

Objective: maximise sum of predicted_points for starting XI.
Bench players get a tiny ε to encourage using the full budget.
"""
from __future__ import annotations

import logging
from typing import Any

import pulp

from config import (
    BUDGET,
    MAX_PER_SQUAD,
    MIN_STARTING,
    SQUAD_COMPOSITION,
    STARTING_XI,
    SQUAD_SIZE,
)

log = logging.getLogger(__name__)

EPSILON = 0.001   # bench objective weight


def optimize_squad(players: list[dict], budget: int = BUDGET) -> dict[str, Any]:
    """
    Run LP to pick optimal 15-player squad.
    Returns {"starters": [...], "bench": [...]}
    """
    prob = pulp.LpProblem("WC2026_Squad", pulp.LpMaximize)

    n = len(players)
    ids = list(range(n))

    # Decision variables
    selected = [pulp.LpVariable(f"sel_{i}", cat="Binary") for i in ids]
    starting = [pulp.LpVariable(f"sta_{i}", cat="Binary") for i in ids]

    # Objective: maximise XI predicted points + tiny bench bonus
    prob += (
        pulp.lpSum(players[i]["predicted_points"] * starting[i] for i in ids)
        + EPSILON * pulp.lpSum(players[i]["predicted_points"] * (selected[i] - starting[i]) for i in ids)
    )

    # Squad size = 15
    prob += pulp.lpSum(selected) == SQUAD_SIZE

    # Starting XI = 11
    prob += pulp.lpSum(starting) == STARTING_XI

    # Starter must be selected
    for i in ids:
        prob += starting[i] <= selected[i]

    # Position quotas – squad
    for pos, quota in SQUAD_COMPOSITION.items():
        prob += pulp.lpSum(selected[i] for i in ids if players[i]["position"] == pos) == quota

    # Position minimums – starting XI
    for pos, min_count in MIN_STARTING.items():
        prob += pulp.lpSum(starting[i] for i in ids if players[i]["position"] == pos) >= min_count

    # Exactly 1 starting GKP
    prob += pulp.lpSum(starting[i] for i in ids if players[i]["position"] == "GKP") == 1

    # Budget
    prob += pulp.lpSum(players[i]["cost"] * selected[i] for i in ids) <= budget

    # Max per squad (national team)
    team_ids = set(p["team_id"] for p in players)
    for tid in team_ids:
        prob += pulp.lpSum(selected[i] for i in ids if players[i]["team_id"] == tid) <= MAX_PER_SQUAD

    # Solve (suppress solver output)
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    if pulp.LpStatus[prob.status] != "Optimal":
        log.warning(f"LP status: {pulp.LpStatus[prob.status]}")

    selected_players = []
    for i in ids:
        if pulp.value(selected[i]) and pulp.value(selected[i]) > 0.5:
            selected_players.append(dict(players[i]))

    starters, bench = _timing_bench_assign(selected_players)
    return {"starters": starters, "bench": bench}


def _timing_bench_assign(
    players_15: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Assign starter/bench roles within the 15 selected players based on
    match timing in Round 1: earliest-playing players start, latest-playing
    go to bench (maximising mid-round substitution flexibility).

    Formation constraints are respected:
      - Exactly 1 GKP starts (the one playing earlier)
      - Starters: ≥3 DEF, ≥2 MID, ≥1 FWD
    """
    def r1_day(p: dict) -> int:
        return p.get("round_day_ranks", {}).get("1", 99)

    # ── GKPs: earlier starts, later benches ──────────────────────────────────
    gkps = sorted([p for p in players_15 if p["position"] == "GKP"], key=r1_day)
    starting_gkp = [gkps[0]]
    bench_gkp    = [gkps[1]] if len(gkps) > 1 else []

    outfield = [p for p in players_15 if p["position"] != "GKP"]

    # ── Mandatory starters: satisfy formation minimums ────────────────────────
    # Sort each group earliest→latest so mandatory slots go to early-playing players
    by_pos = {
        pos: sorted([p for p in outfield if p["position"] == pos], key=r1_day)
        for pos in ("DEF", "MID", "FWD")
    }
    mandatory = (
        by_pos["DEF"][:3] +   # earliest 3 DEF must start
        by_pos["MID"][:2] +   # earliest 2 MID must start
        by_pos["FWD"][:1]     # earliest 1 FWD must start
    )
    mandatory_ids = {p["id"] for p in mandatory}

    # ── Remaining outfield: 2 DEF + 3 MID + 2 FWD = 7 players ───────────────
    remaining = sorted(
        [p for p in outfield if p["id"] not in mandatory_ids],
        key=r1_day
    )
    # Earliest 4 fill flexible starter spots; latest 3 go to bench
    flex_starters = remaining[:4]
    flex_bench    = remaining[4:]

    starters = starting_gkp + mandatory + flex_starters
    bench    = bench_gkp    + flex_bench

    return starters, bench
