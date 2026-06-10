"""
WC2026 Fantasy – Squad Optimizer (PuLP LP solver)

Constraints:
  - 15 players total (2 GKP, 5 DEF, 5 MID, 3 FWD)
  - Starting XI: 11 (1 GKP, at least 3 DEF, 2 MID, 1 FWD)
  - Budget ≤ 1000 (× $0.1m)
  - ≤ MAX_PER_SQUAD players from any one national team

Post-LP passes (applied in order):
  1. Day-diversity: no two players in the same position group may play on
     the same day in any of the 3 group-stage rounds. Conflicts are resolved
     by swapping the weaker player for the next-best unselected player who
     breaks the clash (best-effort; some conflicts may be unresolvable).
  2. Timing bench: earliest-playing players start, latest-playing bench
     (maximises mid-round substitution flexibility).
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


# ── Main entry point ──────────────────────────────────────────────────────────

def optimize_squad(players: list[dict], budget: int = BUDGET) -> dict[str, Any]:
    """
    Run LP to pick optimal 15-player squad, then apply post-LP diversity
    and timing passes.
    Returns {"starters": [...], "bench": [...], "conflicts": [...]}
    """
    prob = pulp.LpProblem("WC2026_Squad", pulp.LpMaximize)

    n = len(players)
    ids = list(range(n))

    # Decision variables
    sel = [pulp.LpVariable(f"sel_{i}", cat="Binary") for i in ids]
    sta = [pulp.LpVariable(f"sta_{i}", cat="Binary") for i in ids]

    # Objective: maximise XI predicted points + tiny bench bonus
    prob += (
        pulp.lpSum(players[i]["predicted_points"] * sta[i] for i in ids)
        + EPSILON * pulp.lpSum(players[i]["predicted_points"] * (sel[i] - sta[i]) for i in ids)
    )

    # Squad size = 15
    prob += pulp.lpSum(sel) == SQUAD_SIZE

    # Starting XI = 11
    prob += pulp.lpSum(sta) == STARTING_XI

    # Starter must be selected
    for i in ids:
        prob += sta[i] <= sel[i]

    # Position quotas – squad
    for pos, quota in SQUAD_COMPOSITION.items():
        prob += pulp.lpSum(sel[i] for i in ids if players[i]["position"] == pos) == quota

    # Position minimums – starting XI
    for pos, min_count in MIN_STARTING.items():
        prob += pulp.lpSum(sta[i] for i in ids if players[i]["position"] == pos) >= min_count

    # Exactly 1 starting GKP
    prob += pulp.lpSum(sta[i] for i in ids if players[i]["position"] == "GKP") == 1

    # Budget
    prob += pulp.lpSum(players[i]["cost"] * sel[i] for i in ids) <= budget

    # Max per squad (national team)
    for tid in set(p["team_id"] for p in players):
        prob += pulp.lpSum(sel[i] for i in ids if players[i]["team_id"] == tid) <= MAX_PER_SQUAD

    # Solve
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[prob.status] != "Optimal":
        log.warning(f"LP status: {pulp.LpStatus[prob.status]}")

    selected_players = [
        dict(players[i]) for i in ids
        if pulp.value(sel[i]) and pulp.value(sel[i]) > 0.5
    ]

    # Post-LP pass 1: resolve same-day position conflicts
    selected_players, conflicts = _resolve_day_conflicts(selected_players, players, budget)

    # Post-LP pass 2: timing-aware starter/bench assignment
    starters, bench = _timing_bench_assign(selected_players)

    return {"starters": starters, "bench": bench, "conflicts": conflicts}


# ── Day-diversity conflict resolution ─────────────────────────────────────────

def _find_day_conflict(
    selected: list[dict],
    skip: set[tuple] | None = None,
) -> tuple | None:
    """
    Return the first (pos, round_key, date, conflicting_players) tuple where
    two or more players of the same position play on the same day in any round.
    Entries in `skip` are ignored.
    """
    for pos in ("GKP", "DEF", "MID", "FWD"):
        group = [p for p in selected if p["position"] == pos]
        for rk in ("1", "2", "3"):
            day_buckets: dict[str, list] = {}
            for p in group:
                day = p.get("round_dates", {}).get(rk, "")
                if not day:
                    continue
                day_buckets.setdefault(day, []).append(p)
            for day, players_on_day in day_buckets.items():
                if len(players_on_day) > 1:
                    key = (pos, rk, day)
                    if skip and key in skip:
                        continue
                    return (pos, rk, day, players_on_day)
    return None


def _has_day_conflict_with(candidate: dict, others: list[dict]) -> bool:
    """True if candidate plays on the same day as any player in `others` in any round."""
    for rk in ("1", "2", "3"):
        cand_day = candidate.get("round_dates", {}).get(rk, "")
        if not cand_day:
            continue
        for p in others:
            if p.get("round_dates", {}).get(rk, "") == cand_day:
                return True
    return False


def _resolve_day_conflicts(
    selected: list[dict],
    all_players: list[dict],
    budget: int,
) -> tuple[list[dict], list[dict]]:
    """
    Iteratively fix same-day position conflicts by swapping the weakest
    player in each conflict for the best unselected replacement that
    doesn't create new conflicts.

    Returns (updated_selected, list_of_conflict_warning_strings).
    """
    selected = list(selected)
    selected_ids = {p["id"] for p in selected}
    unresolvable: set[tuple] = set()
    conflict_log: list[str] = []

    # Sort all_players by predicted_points desc once (used for candidate search)
    sorted_all = sorted(all_players, key=lambda p: p["predicted_points"], reverse=True)

    for _iteration in range(50):   # hard cap to prevent infinite loops
        conflict = _find_day_conflict(selected, skip=unresolvable)
        if conflict is None:
            break

        pos, rk, conflict_day, clash_group = conflict

        # Weakest player in the clash
        weak = min(clash_group, key=lambda p: p["predicted_points"])

        # Remaining same-position players after removing weak
        remaining_pos = [
            p for p in selected
            if p["position"] == pos and p["id"] != weak["id"]
        ]

        # Budget headroom for replacement
        cost_without_weak = sum(p["cost"] for p in selected if p["id"] != weak["id"])
        max_cost = budget - cost_without_weak

        # Team counts without weak player
        team_counts: dict[int, int] = {}
        for p in selected:
            if p["id"] != weak["id"]:
                team_counts[p["team_id"]] = team_counts.get(p["team_id"], 0) + 1

        # Find best replacement
        replacement = None
        for cand in sorted_all:
            if cand["id"] in selected_ids:
                continue
            if cand["position"] != pos:
                continue
            if cand["cost"] > max_cost:
                continue
            if team_counts.get(cand["team_id"], 0) >= MAX_PER_SQUAD:
                continue
            if _has_day_conflict_with(cand, remaining_pos):
                continue
            replacement = cand
            break

        if replacement is None:
            msg = (f"⚠ Could not resolve: {pos} clash on round {rk} "
                   f"({conflict_day}) – {[p['name'] for p in clash_group]}")
            log.warning(msg)
            conflict_log.append(msg)
            unresolvable.add((pos, rk, conflict_day))
            continue

        # Perform swap
        log.info(
            f"Day conflict fixed: swapped out {weak['name']} "
            f"({pos}, round {rk} day {conflict_day}) "
            f"→ {replacement['name']}"
        )
        selected = [p for p in selected if p["id"] != weak["id"]]
        selected.append(replacement)
        selected_ids.discard(weak["id"])
        selected_ids.add(replacement["id"])

    return selected, conflict_log


# ── Timing-aware starter / bench assignment ───────────────────────────────────

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
    by_pos = {
        pos: sorted([p for p in outfield if p["position"] == pos], key=r1_day)
        for pos in ("DEF", "MID", "FWD")
    }
    mandatory = (
        by_pos["DEF"][:3] +
        by_pos["MID"][:2] +
        by_pos["FWD"][:1]
    )
    mandatory_ids = {p["id"] for p in mandatory}

    # ── Remaining outfield: earliest 4 start, latest 3 bench ─────────────────
    remaining = sorted(
        [p for p in outfield if p["id"] not in mandatory_ids],
        key=r1_day
    )
    flex_starters = remaining[:4]
    flex_bench    = remaining[4:]

    starters = starting_gkp + mandatory + flex_starters
    bench    = bench_gkp    + flex_bench

    return starters, bench
