"""
FIFA Fantasy WC2026 – Data Client
Fetches players and fixtures from play.fifa.com/json/ (public, no auth).
Caches data for CACHE_TTL_SECONDS to avoid hammering the endpoint.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from config import (
    CACHE_TTL_SECONDS,
    FIFA_RANKINGS,
    PLAYERS_URL,
    POSITION_MAP,
    ROUNDS_URL,
    SEMAPHORE_LIMIT,
)

log = logging.getLogger(__name__)

_cache: dict[str, Any] = {}
_cache_ts: float = 0.0
_lock = asyncio.Lock()
_sem = asyncio.Semaphore(SEMAPHORE_LIMIT)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://play.fifa.com/",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _team_strength_score(team_name: str) -> float:
    """0–1 score from FIFA world ranking (1=best → 1.0, 48=worst → ~0.0)."""
    rank = FIFA_RANKINGS.get(team_name, 48)
    # Invert: rank 1 → 1.0, rank 48 → ~0.0
    return round(1.0 - (rank - 1) / 47, 4)


def _build_squad_name_map(squads: list[dict]) -> dict[int, str]:
    """Map squad ID → team name from the squads list in players API."""
    return {s["id"]: s["name"] for s in squads}


def _parse_rounds(raw_rounds: list[dict]) -> dict:
    """
    Returns:
      group_fixtures:   {squad_id: [opponent_squad_id, ...]}  (group stage only)
      group_rounds:     list of round dicts for group stage
      squad_id_to_name: {squad_id: team_name}
    """
    squad_id_to_name: dict[int, str] = {}
    group_fixtures: dict[int, list[int]] = {}
    group_rounds: list[dict] = []

    for rnd in raw_rounds:
        if rnd.get("stage") != "group":
            continue
        group_rounds.append(rnd)
        for match in rnd.get("tournaments", []):
            home = match["homeSquadId"]
            away = match["awaySquadId"]
            home_name = match.get("homeSquadName", "")
            away_name = match.get("awaySquadName", "")
            squad_id_to_name[home] = home_name
            squad_id_to_name[away] = away_name
            group_fixtures.setdefault(home, []).append(away)
            group_fixtures.setdefault(away, []).append(home)

    return {
        "group_fixtures": group_fixtures,
        "group_rounds": group_rounds,
        "squad_id_to_name": squad_id_to_name,
    }


def _fixture_ease(squad_id: int, opponents: list[int], squad_id_to_name: dict) -> float:
    """
    Average ease of a team's 3 group opponents.
    Ease = 1 - opponent_strength (weaker opponent → easier fixture → higher score).
    """
    if not opponents:
        return 0.5
    ease_scores = []
    for opp_id in opponents:
        opp_name = squad_id_to_name.get(opp_id, "")
        opp_strength = _team_strength_score(opp_name)
        ease_scores.append(1.0 - opp_strength)
    return round(sum(ease_scores) / len(ease_scores), 4)


def _enrich_players(
    raw_players: list[dict],
    squad_id_to_name: dict[int, str],
    group_fixtures: dict[int, list[int]],
) -> list[dict]:
    enriched = []
    for p in raw_players:
        squad_id = p.get("squadId", 0)
        team_name = squad_id_to_name.get(squad_id, "Unknown")
        position_id = p.get("position", 4)
        position = POSITION_MAP.get(position_id, "FWD")

        stats = p.get("stats", {})
        opponents = group_fixtures.get(squad_id, [])

        team_str = _team_strength_score(team_name)
        fix_ease = _fixture_ease(squad_id, opponents, squad_id_to_name)

        # Cost: the API returns 0 before the game launches; default $6.0m if missing
        raw_cost = p.get("cost", 0)
        cost = raw_cost if raw_cost > 0 else 60  # stored as 10× (60 = $6.0m)

        enriched.append({
            "id": p["id"],
            "name": p.get("name", ""),
            "short_name": p.get("shortName", p.get("preferredName", "")),
            "team": team_name,
            "team_id": squad_id,
            "position": position,
            "cost": cost,                          # raw (10×)
            "team_strength": team_str,
            "fixture_ease": fix_ease,
            "opponents": opponents,
            # Stats
            "total_points": stats.get("totalPoints", 0),
            "games_played": stats.get("gamesPlayed", 0),
            "goals": stats.get("goals", 0),
            "assists": stats.get("assists", 0),
            "clean_sheets": stats.get("cleanSheets", 0),
            "goals_conceded": stats.get("goalsConceded", 0),
            "picked_by": round(stats.get("pickedBy", 0.0) * 100, 1),  # → %
            "round_scores": stats.get("roundScores", {}),
            "status": p.get("status", "unconfirmed"),
        })
    return enriched


# ── Public API ────────────────────────────────────────────────────────────────

async def fetch_all_data() -> dict:
    global _cache, _cache_ts
    async with _lock:
        if _cache and (time.time() - _cache_ts) < CACHE_TTL_SECONDS:
            return _cache

        log.info("Fetching fresh data from play.fifa.com/json/")
        async with httpx.AsyncClient(headers=HEADERS, timeout=20) as client:
            p_resp, r_resp = await asyncio.gather(
                client.get(PLAYERS_URL),
                client.get(ROUNDS_URL),
            )

        p_resp.raise_for_status()
        r_resp.raise_for_status()

        raw_players: list[dict] = p_resp.json()
        raw_rounds: list[dict]  = r_resp.json()

        round_data = _parse_rounds(raw_rounds)
        squad_id_to_name = round_data["squad_id_to_name"]
        group_fixtures    = round_data["group_fixtures"]
        group_rounds      = round_data["group_rounds"]

        players = _enrich_players(raw_players, squad_id_to_name, group_fixtures)

        _cache = {
            "players": players,
            "group_rounds": group_rounds,
            "squad_id_to_name": squad_id_to_name,
        }
        _cache_ts = time.time()
        log.info(f"Loaded {len(players)} players, {len(group_rounds)} group rounds")
        return _cache
