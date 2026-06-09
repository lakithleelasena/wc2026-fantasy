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

    starters, bench = [], []
    for i in ids:
        if pulp.value(selected[i]) and pulp.value(selected[i]) > 0.5:
            p = dict(players[i])
            p["is_starter"] = bool(pulp.value(starting[i]) and pulp.value(starting[i]) > 0.5)
            if p["is_starter"]:
                starters.append(p)
            else:
                bench.append(p)

    return {"starters": starters, "bench": bench}
