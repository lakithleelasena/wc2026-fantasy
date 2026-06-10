"""
FIFA Fantasy WC2026 – Data Client
Fetches players and fixtures from play.fifa.com/json/fantasy/ (public, no auth).
Caches data for CACHE_TTL_SECONDS to avoid hammering the endpoint.

WC2026 schema differences from Women's WC:
  - Player: firstName/lastName/knownName, price (float $m), position string,
            percentSelected, stats.roundPoints (array), stats.form
  - Round:  stage is uppercase ("GROUP"), squad IDs are small ints (1–48)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from config import (
    CACHE_TTL_SECONDS,
    ELO_RATINGS,
    PLAYERS_URL,
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
    "Referer": "https://play.fifa.com/fantasy",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

_ELO_MIN = min(ELO_RATINGS.values())   # 1421 (Qatar)
_ELO_MAX = max(ELO_RATINGS.values())   # 2157 (Spain)

def _team_strength_score(team_name: str) -> float:
    """0–1 score from Elo rating: best WC team → 1.0, worst → 0.0."""
    elo = ELO_RATINGS.get(team_name, _ELO_MIN)
    return round((elo - _ELO_MIN) / (_ELO_MAX - _ELO_MIN), 4)


def _fixture_ease(squad_id: int, opponents: list[int], squad_id_to_name: dict) -> float:
    """Average ease of a team's 3 group opponents (weaker opponent = higher ease)."""
    if not opponents:
        return 0.5
    ease_scores = [1.0 - _team_strength_score(squad_id_to_name.get(opp, "")) for opp in opponents]
    return round(sum(ease_scores) / len(ease_scores), 4)


def _parse_rounds(raw_rounds: list[dict]) -> dict:
    """Extract group-stage fixture data, squad mappings, per-round opponents, and groups."""
    squad_id_to_name: dict[int, str] = {}
    squad_id_to_abbr: dict[int, str] = {}
    group_fixtures: dict[int, list[int]] = {}
    group_rounds: list[dict] = []

    for rnd in raw_rounds:
        if rnd.get("stage", "").upper() != "GROUP":
            continue
        group_rounds.append(rnd)
        for match in rnd.get("tournaments", []):
            home = match["homeSquadId"]
            away = match["awaySquadId"]
            squad_id_to_name[home] = match.get("homeSquadName", "")
            squad_id_to_name[away] = match.get("awaySquadName", "")
            squad_id_to_abbr[home] = match.get("homeSquadAbbr", "")
            squad_id_to_abbr[away] = match.get("awaySquadAbbr", "")
            group_fixtures.setdefault(home, []).append(away)
            group_fixtures.setdefault(away, []).append(home)

    # Per-round opponent: {squad_id: {game_idx(1-3): opp_squad_id}}
    round_opponents_map: dict[int, dict[int, int]] = {}
    for idx, rnd in enumerate(group_rounds, start=1):
        for match in rnd.get("tournaments", []):
            home, away = match["homeSquadId"], match["awaySquadId"]
            round_opponents_map.setdefault(home, {})[idx] = away
            round_opponents_map.setdefault(away, {})[idx] = home

    # Detect groups (connected components in fixture graph → 12 groups of 4)
    visited: set[int] = set()
    raw_groups: list[list[int]] = []
    for sid in sorted(group_fixtures.keys()):
        if sid in visited:
            continue
        grp: set[int] = set()
        queue = [sid]
        while queue:
            s = queue.pop()
            if s in grp:
                continue
            grp.add(s)
            queue.extend(group_fixtures.get(s, []))
        visited |= grp
        raw_groups.append(sorted(grp))
    raw_groups.sort(key=lambda g: g[0])

    # Build structured group data with fixtures
    groups: list[dict] = []
    for i, squad_ids in enumerate(raw_groups):
        letter = chr(ord("A") + i)
        teams = [
            {
                "id":       sid,
                "name":     squad_id_to_name.get(sid, ""),
                "abbr":     squad_id_to_abbr.get(sid, ""),
                "rank":     ELO_RATINGS.get(squad_id_to_name.get(sid, ""), _ELO_MIN),
                "strength": _team_strength_score(squad_id_to_name.get(sid, "")),
            }
            for sid in squad_ids
        ]
        fixtures: list[dict] = []
        for game_idx, rnd in enumerate(group_rounds, start=1):
            for match in rnd.get("tournaments", []):
                if match["homeSquadId"] in squad_ids:
                    fixtures.append({
                        "game":         game_idx,
                        "home_team":    match.get("homeSquadName", ""),
                        "home_team_id": match["homeSquadId"],
                        "away_team":    match.get("awaySquadName", ""),
                        "away_team_id": match["awaySquadId"],
                        "date":         match.get("date", ""),
                        "status":       match.get("status", "scheduled"),
                        "home_score":   match.get("homeScore"),
                        "away_score":   match.get("awayScore"),
                    })
        groups.append({"name": letter, "teams": teams, "fixtures": fixtures})

    return {
        "group_fixtures":     group_fixtures,
        "group_rounds":       group_rounds,
        "squad_id_to_name":   squad_id_to_name,
        "squad_id_to_abbr":   squad_id_to_abbr,
        "round_opponents_map": round_opponents_map,
        "groups":             groups,
    }


def _player_name(p: dict) -> tuple[str, str]:
    """Return (full_name, short_name) from a WC2026 player dict."""
    known = p.get("knownName")
    first = p.get("firstName", "")
    last  = p.get("lastName", "")
    full  = known or f"{first} {last}".strip()
    short = known or last or full
    return full, short


def _round_scores(round_points: list) -> dict:
    """
    Convert stats.roundPoints array to {group_round_index: points} dict.
    Each element is either an int or {"roundId": x, "points": y}.
    Keys are 1-based group stage round indices ("1", "2", "3").
    """
    scores = {}
    for i, entry in enumerate(round_points, start=1):
        if isinstance(entry, (int, float)):
            scores[str(i)] = entry
        elif isinstance(entry, dict):
            scores[str(i)] = entry.get("points")
    return scores


def _enrich_players(
    raw_players: list[dict],
    squad_id_to_name: dict[int, str],
    group_fixtures: dict[int, list[int]],
    round_opponents_map: dict[int, dict[int, int]] | None = None,
) -> list[dict]:
    enriched = []
    for p in raw_players:
        squad_id = p.get("squadId", 0)
        team_name = squad_id_to_name.get(squad_id, "Unknown")
        raw_pos   = p.get("position", "FWD")
        position  = "GKP" if raw_pos == "GK" else raw_pos  # normalise GK → GKP

        stats    = p.get("stats", {})
        opponents = group_fixtures.get(squad_id, [])

        team_str = _team_strength_score(team_name)
        fix_ease = _fixture_ease(squad_id, opponents, squad_id_to_name)

        # price is in $m (e.g. 4.9); store as 10× for LP budget integer arithmetic
        price = p.get("price") or 0
        cost  = round(price * 10) if price else 60   # default $6.0m if missing

        full_name, short_name = _player_name(p)

        enriched.append({
            "id":           p["id"],
            "name":         full_name,
            "short_name":   short_name,
            "team":         team_name,
            "team_id":      squad_id,
            "position":     position,
            "cost":         cost,                                    # raw 10×
            "team_strength": team_str,
            "fixture_ease":  fix_ease,
            "opponents":     opponents,
            # Stats
            "total_points":  stats.get("totalPoints", 0),
            "games_played":  len(stats.get("roundPoints", [])),
            "goals":         stats.get("goals", 0),
            "assists":       stats.get("assists", 0),
            "clean_sheets":  stats.get("cleanSheets", 0),
            "goals_conceded": stats.get("goalsConceded", 0),
            "picked_by":     round(p.get("percentSelected", 0.0), 1),
            "round_scores":  _round_scores(stats.get("roundPoints", [])),
            "round_opponents": {
                str(i): squad_id_to_name.get(
                    (round_opponents_map or {}).get(squad_id, {}).get(i), ""
                )
                for i in [1, 2, 3]
            },
            "status":        p.get("status", "unconfirmed"),
        })
    return enriched


# ── Public API ────────────────────────────────────────────────────────────────

async def fetch_all_data() -> dict:
    global _cache, _cache_ts
    async with _lock:
        if _cache and (time.time() - _cache_ts) < CACHE_TTL_SECONDS:
            return _cache

        log.info("Fetching fresh data from play.fifa.com/json/fantasy/")
        async with httpx.AsyncClient(headers=HEADERS, timeout=20) as client:
            p_resp, r_resp = await asyncio.gather(
                client.get(PLAYERS_URL),
                client.get(ROUNDS_URL),
            )

        p_resp.raise_for_status()
        r_resp.raise_for_status()

        raw_players: list[dict] = p_resp.json()
        raw_rounds:  list[dict] = r_resp.json()

        round_data           = _parse_rounds(raw_rounds)
        squad_id_to_name     = round_data["squad_id_to_name"]
        group_fixtures       = round_data["group_fixtures"]
        group_rounds         = round_data["group_rounds"]
        round_opponents_map  = round_data["round_opponents_map"]

        players = _enrich_players(
            raw_players, squad_id_to_name, group_fixtures, round_opponents_map
        )

        _cache = {
            "players":          players,
            "group_rounds":     group_rounds,
            "squad_id_to_name": squad_id_to_name,
            "groups":           round_data["groups"],
        }
        _cache_ts = time.time()
        log.info(f"Loaded {len(players)} players, {len(group_rounds)} group rounds")
        return _cache
