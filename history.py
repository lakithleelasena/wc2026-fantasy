"""
Curated player projections — the single source of truth for the 17 covered
national teams (data/projections.csv). Replaces the old API-Football history
and the separate expected_starts CSV.

Each row provides, per player:
  • P_Start           → forward-looking "will they start" prior
  • Goal_Share_Pct    → player's share of the team's goals (percent)
  • Assist_Share_Pct  → player's share of the team's assists (percent)
  • Penalty_Taker     → Y/N: designated penalty taker
  • Set_Pieces        → Primary / Secondary / N: corner & free-kick duty

Goal/assist shares and P(start) feed the open-play model; penalty and
set-piece flags add small additive xG/xA bonuses on top (see set_piece_bonus).

Players/teams not in the file fall back to price-based shares in fifa_client
and the price-tier P(start) in predictor.
"""
from __future__ import annotations

import csv
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
PROJECTIONS_FILE = DATA_DIR / "projections.csv"

# generic name suffixes that are not a real surname (Brazilian/Iberian)
_NAME_SUFFIXES = {"junior", "jr", "filho", "neto", "segundo"}

# ── Penalty / set-piece bonus constants (additive xG/xA per game) ──────────────
PEN_TEAM_XG_PER_GAME = 0.20    # team penalty xG/game, split among its Y takers
SP_PRIMARY_XA = 0.12           # primary corner/FK deliverer assist bump
SP_PRIMARY_XG = 0.04           # primary direct-FK goal bump
SP_SECONDARY_XA = 0.06
SP_SECONDARY_XG = 0.02


def _norm(s: str) -> str:
    """Lowercase, strip accents, collapse punctuation to spaces."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("-", " ").replace(".", " ").split())


def _name_tokens(player_field: str) -> list[str]:
    """Significant name tokens (len>2, no generic suffix), annotations stripped."""
    base = player_field.split("(")[0]                       # drop "(GK)" etc.
    toks = [t for t in _norm(base).split() if len(t) > 2 and t not in _NAME_SUFFIXES]
    if not toks:                                            # name was only a suffix
        toks = [t for t in _norm(base).split() if len(t) > 2]
    return toks


@lru_cache(maxsize=1)
def _projections() -> dict:
    """
    {team: [ {tokens, pos, p_start, goal_share, assist_share,
              xg_bonus, xa_bonus}, ... ]}

    Penalty xG (PEN_TEAM_XG_PER_GAME) is split equally among a team's Y takers.
    """
    if not PROJECTIONS_FILE.exists():
        return {}

    rows: list[dict] = []
    pen_takers: dict[str, int] = defaultdict(int)

    with PROJECTIONS_FILE.open() as f:
        for r in csv.DictReader(f):
            team = r["Team"].strip()
            pos = r["Position"].strip().upper()
            pos = "GKP" if pos == "GK" else pos
            try:
                p_start = float(r["P_Start"])
                goal_share = float(r["Goal_Share_Pct"]) / 100.0
                assist_share = float(r["Assist_Share_Pct"]) / 100.0
            except (KeyError, ValueError):
                continue
            pen = r.get("Penalty_Taker", "N").strip().upper() == "Y"
            sp = r.get("Set_Pieces", "N").strip().lower()
            if pen:
                pen_takers[team] += 1
            rows.append({
                "team": team, "tokens": _name_tokens(r["Player"]), "pos": pos,
                "p_start": p_start, "goal_share": round(goal_share, 4),
                "assist_share": round(assist_share, 4), "pen": pen, "sp": sp,
            })

    out: dict[str, list] = defaultdict(list)
    for r in rows:
        xg = xa = 0.0
        if r["pen"]:
            xg += PEN_TEAM_XG_PER_GAME / pen_takers[r["team"]]
        if r["sp"] == "primary":
            xg += SP_PRIMARY_XG
            xa += SP_PRIMARY_XA
        elif r["sp"] == "secondary":
            xg += SP_SECONDARY_XG
            xa += SP_SECONDARY_XA
        out[r["team"]].append({
            "tokens": r["tokens"], "pos": r["pos"], "p_start": r["p_start"],
            "goal_share": r["goal_share"], "assist_share": r["assist_share"],
            "xg_bonus": round(xg, 4), "xa_bonus": round(xa, 4),
        })
    return dict(out)


def _pos_class(pos: str) -> str:
    """Keepers are isolated; outfield positions are interchangeable."""
    return "GKP" if pos == "GKP" else "OUT"


def _match(team: str, full_name: str, position: str) -> dict | None:
    """
    Match a FIFA (name, position) to one projection row.

    A row matches only if ALL of its significant name tokens appear in the FIFA
    name. This rejects same-surname different-player collisions — Anthony
    Valencia must not inherit Enner Valencia's row (shared surname, different
    first name), and a multi-token file name like "Enner Valencia" needs both
    "enner" and "valencia". Surname-only file rows ("Kane") still match on the
    single token.

    Position is enforced at the class level — keeper vs outfield — so a backup
    keeper never inherits an outfield star's row (Rui Silva GKP ≠ Bernardo Silva
    MID). Within the outfield, DEF/MID/FWD are interchangeable because FIFA and
    the file disagree on many attackers (Saka/Yamal are MID in FIFA, FWD in the
    file). Exact position is a tiebreaker among same-name teammates (the three
    Martínezes). More-specific rows (more matching tokens) win over less.
    """
    rows = _projections().get(team)
    if not rows:
        return None
    fifa_tokens = {t for t in _norm(full_name).split() if len(t) > 2}
    cls = _pos_class(position)
    candidates = [
        r for r in rows
        if r["tokens"] and set(r["tokens"]) <= fifa_tokens and _pos_class(r["pos"]) == cls
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda r: len(r["tokens"]), reverse=True)   # most specific first
    for r in candidates:                       # same-name teammates → use exact position
        if r["pos"] == position:
            return r
    return candidates[0]


def player_shares(team: str, full_name: str, position: str) -> dict | None:
    """Return {"goal_share","assist_share"} from projections, or None."""
    row = _match(team, full_name, position)
    if row is None:
        return None
    return {"goal_share": row["goal_share"], "assist_share": row["assist_share"]}


def start_prob(team: str, full_name: str, position: str) -> float | None:
    """Projected P(start) matched by (team, surname, position), or None."""
    row = _match(team, full_name, position)
    return row["p_start"] if row else None


def set_piece_bonus(team: str, full_name: str, position: str) -> dict:
    """Additive {"xg_bonus","xa_bonus"} from penalty/set-piece duty (zeros if none)."""
    row = _match(team, full_name, position)
    if row is None:
        return {"xg_bonus": 0.0, "xa_bonus": 0.0}
    return {"xg_bonus": row["xg_bonus"], "xa_bonus": row["xa_bonus"]}
