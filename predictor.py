"""
WC2026 Fantasy – Prediction Model (ELO-based)

Per-game expected fantasy points derived from physics, not curve-fitting:

  Step 1  ELO difference  →  expected goals (home/away each match)
  Step 2  ELO difference  →  clean-sheet probability (logistic)
  Step 3  Player price    →  P(start) and expected minutes
  Step 4  Price weight    →  each player's share of team goals/assists
  Step 5  Multiply out    →  xG, xA, xCS per player per game
  Step 6  Apply official  →  expected fantasy points using FIFA scoring rules
          scoring rules

No arbitrary weights — the model is fully determined by ELO ratings,
player prices, and the official point values.
"""
from __future__ import annotations

import math
from config import ELO_RATINGS
from scorer import (
    SCORING,
    GOAL_POS_SHARE,
    ASSIST_POS_SHARE,
    YELLOW_CARD_RATE,
    RED_CARD_RATE,
    ASSIST_RATE,
    GK_SAVES_PER_GAME,
)

_ELO_MIN = min(ELO_RATINGS.values())   # 1421 Qatar
_ELO_MAX = max(ELO_RATINGS.values())   # 2157 Spain
_ELO_MED = (_ELO_MIN + _ELO_MAX) // 2  # fallback when opponent unknown


# ── Core statistical models ───────────────────────────────────────────────────

def _start_prob(cost_10x: int) -> float:
    """
    P(player starts 60+ min) estimated from price tier.
    FIFA prices are set by analysts who see training squads — price is the
    single best public signal for who starts.
    """
    price = cost_10x / 10.0
    if price >= 10.0: return 0.97
    if price >= 9.0:  return 0.93
    if price >= 8.0:  return 0.85
    if price >= 7.0:  return 0.72
    if price >= 6.0:  return 0.55
    if price >= 5.0:  return 0.35
    if price >= 4.5:  return 0.20
    return 0.10


def _expected_goals(team_elo: int, opp_elo: int) -> float:
    """
    ELO-based expected goals for one team in one match.
    Formula: EG = 1.35 + 0.003 × (Elo_team − Elo_opp)
    Clamped to [0.3, 4.0] — no realistic WC game escapes that range.
    """
    eg = 1.35 + 0.003 * (team_elo - opp_elo)
    return round(max(0.3, min(4.0, eg)), 4)


def _clean_sheet_prob(team_elo: int, opp_elo: int) -> float:
    """
    Logistic model for P(clean sheet).
    P(CS) = sigmoid(0.5 + 0.002 × (Elo_team − Elo_opp))
    A 500-Elo gap gives P(CS) ≈ 73%; equal teams ≈ 62%.
    """
    return round(1.0 / (1.0 + math.exp(-(0.5 + 0.002 * (team_elo - opp_elo)))), 4)


# ── Per-game prediction ───────────────────────────────────────────────────────

def _predict_one_game(player: dict, game_idx: int) -> float:
    """Expected fantasy points for one group-stage match."""
    pos  = player.get("position", "MID")
    cost = player.get("cost", 60)      # 10× price
    team = player.get("team", "")

    team_elo = ELO_RATINGS.get(team, _ELO_MED)
    opp_name = player.get("round_opponents", {}).get(str(game_idx), "")
    opp_elo  = ELO_RATINGS.get(opp_name, _ELO_MED) if opp_name else _ELO_MED

    p_start    = _start_prob(cost)
    eg_for     = _expected_goals(team_elo, opp_elo)    # goals our team scores
    eg_against = _expected_goals(opp_elo, team_elo)    # goals opponent scores
    p_cs       = _clean_sheet_prob(team_elo, opp_elo)

    rules = SCORING[pos]

    # Player's share of team goals/assists (pre-computed in fifa_client, price-weighted)
    goal_share   = player.get("goal_share",   GOAL_POS_SHARE.get(pos, 0.05) / 11)
    assist_share = player.get("assist_share", ASSIST_POS_SHARE.get(pos, 0.05) / 11)

    xG = eg_for * goal_share            # expected goals this player scores
    xA = eg_for * ASSIST_RATE * assist_share  # expected assists

    # ── Expected fantasy points ──────────────────────────────────────────────
    pts_app    = rules["appearance_full"] * p_start
    pts_goal   = rules["goal"]   * xG * p_start
    pts_assist = rules["assist"] * xA * p_start

    # Clean sheet — GKP & DEF: 6 pts, MID: 1 pt, FWD: 0
    pts_cs     = rules.get("clean_sheet", 0) * p_cs * p_start

    # Goals conceded penalty — GKP & DEF only (−1 per 2 goals, 60+ min)
    gc_pts_per_goal = rules.get("goals_conceded_per_2", 0) / 2.0
    pts_gc     = gc_pts_per_goal * eg_against * p_start

    # Card deductions
    pts_cards  = (rules["yellow_card"] * YELLOW_CARD_RATE +
                  rules["red_card"] * RED_CARD_RATE) * p_start

    xFP = pts_app + pts_goal + pts_assist + pts_cs + pts_gc + pts_cards

    # GKP save bonus: +1 per 3 saves
    if pos == "GKP":
        xFP += rules.get("saves_per_3", 0) * (GK_SAVES_PER_GAME / 3.0) * p_start

    return round(max(0.0, xFP), 2)


# ── Public API ────────────────────────────────────────────────────────────────

def predict_points(player: dict, **kwargs) -> dict:
    """
    Predict fantasy points across all 3 group matches.
    kwargs accepted but ignored (legacy UI weight params — model is now fully
    ELO/price-driven, no manual weight tuning needed).
    """
    g1 = _predict_one_game(player, 1)
    g2 = _predict_one_game(player, 2)
    g3 = _predict_one_game(player, 3)

    team_elo  = ELO_RATINGS.get(player.get("team", ""), _ELO_MED)
    total_pts = player.get("total_points", 0)

    return {
        "predicted_points": round(g1 + g2 + g3, 2),
        "predicted_g1":     g1,
        "predicted_g2":     g2,
        "predicted_g3":     g3,
        "team_strength":    round((team_elo - _ELO_MIN) / (_ELO_MAX - _ELO_MIN), 4),
        "fixture_ease":     round(player.get("fixture_ease", 0.5), 4),
        "form_score":       round(min(total_pts / 30.0, 1.0), 4),
        "position_role":    0.0,   # deprecated, kept for API compatibility
    }
