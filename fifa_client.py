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
from scorer import GOAL_POS_SHARE, ASSIST_POS_SHARE

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

    # Per-round opponent and match date: {squad_id: {game_idx(1-3): opp_squad_id / date_str}}
    round_opponents_map: dict[int, dict[int, int]] = {}
    round_dates_map: dict[int, dict[int, str]] = {}
    for idx, rnd in enumerate(group_rounds, start=1):
        for match in rnd.get("tournaments", []):
            home, away = match["homeSquadId"], match["awaySquadId"]
            round_opponents_map.setdefault(home, {})[idx] = away
            round_opponents_map.setdefault(away, {})[idx] = home
            date_str = match.get("date", "")[:10]   # "2026-06-14"
            round_dates_map.setdefault(home, {})[idx] = date_str
            round_dates_map.setdefault(away, {})[idx] = date_str

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
        "group_fixtures":      group_fixtures,
        "group_rounds":        group_rounds,
        "squad_id_to_name":    squad_id_to_name,
        "squad_id_to_abbr":    squad_id_to_abbr,
        "round_opponents_map": round_opponents_map,
        "round_dates_map":     round_dates_map,
        "groups":              groups,
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
    round_dates_map: dict[int, dict[int, str]] | None = None,
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
            "round_dates": {
                str(i): (round_dates_map or {}).get(squad_id, {}).get(i, "")
                for i in [1, 2, 3]
            },
            "status":        p.get("status", "unconfirmed"),
        })
    return enriched


def _add_shares(players: list[dict]) -> None:
    """
    Compute each player's price-weighted goal_share and assist_share.
    Within each (team, position) group the share is proportional to price,
    giving stars a larger slice of the team's expected attacking output.
    Modifies players in-place.
    """
    from collections import defaultdict
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for p in players:
        groups[(p["team_id"], p["position"])].append(p)

    from history import player_shares, start_prob, set_piece_bonus

    for (_, pos), group in groups.items():
        total_cost = sum(p["cost"] for p in group) or 1
        for p in group:
            price_frac = p["cost"] / total_cost
            p["goal_share"]   = round(GOAL_POS_SHARE.get(pos, 0.05) * price_frac, 4)
            p["assist_share"] = round(ASSIST_POS_SHARE.get(pos, 0.05) * price_frac, 4)

            # Goal/assist shares from curated projections (collision-safe)
            hist = player_shares(p["team"], p["name"], pos)
            p["in_projection"] = hist is not None
            if hist:
                p["goal_share"]   = hist["goal_share"]
                p["assist_share"] = hist["assist_share"]

            # P(start) from curated projections; else predictor falls back to price tier
            ps = start_prob(p["team"], p["name"], pos)
            if ps is not None:
                p["p_start_hist"] = ps

            # Penalty / set-piece additive xG/xA bonuses
            sp = set_piece_bonus(p["team"], p["name"], pos)
            p["xg_bonus"] = sp["xg_bonus"]
            p["xa_bonus"] = sp["xa_bonus"]


def _add_day_ranks(players: list[dict]) -> None:
    """
    For each group-stage round (1-3), assign each player a 'day rank':
    1 = their team plays earliest in that round, N = latest.
    Stored as round_day_ranks: {"1": 3, "2": 1, "3": 5}
    and round_day_count: {"1": 8, ...} (total unique match days in that round).
    Modifies players in-place.
    """
    for round_idx in [1, 2, 3]:
        key = str(round_idx)
        # Collect all unique match dates this round, sorted chronologically
        dates = sorted(set(
            p.get("round_dates", {}).get(key, "")
            for p in players
            if p.get("round_dates", {}).get(key, "")
        ))
        date_rank = {d: i + 1 for i, d in enumerate(dates)}
        n_days = len(dates) or 1
        for p in players:
            date = p.get("round_dates", {}).get(key, "")
            p.setdefault("round_day_ranks", {})[key] = date_rank.get(date, 1)
            p.setdefault("round_day_count", {})[key] = n_days


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
        round_dates_map      = round_data["round_dates_map"]

        players = _enrich_players(
            raw_players, squad_id_to_name, group_fixtures,
            round_opponents_map, round_dates_map
        )
        _add_shares(players)
        _add_day_ranks(players)

        _cache = {
            "players":          players,
            "group_rounds":     group_rounds,
            "squad_id_to_name": squad_id_to_name,
            "groups":           round_data["groups"],
        }
        _cache_ts = time.time()
        log.info(f"Loaded {len(players)} players, {len(group_rounds)} group rounds")
        return _cache
