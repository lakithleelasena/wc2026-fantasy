"""
WC2026 Fantasy – Prediction Model

Signals (no season-long FPL data available for a tournament):

  team_strength  – How good is this player's team? (FIFA ranking proxy)
                   Better team → more likely to score/clean sheet
  fixture_ease   – How weak are their 3 group opponents?
                   Easier fixtures → more predicted points
  form           – Points already scored in this tournament (0 at start)
                   Rewards in-form players once the group stage starts
  position_role  – Attackers score more goals; defenders/GKPs score clean sheets
                   Acts as a per-position baseline multiplier

All signals are normalised to 0–1. The weighted sum is then scaled to a
realistic predicted-points range (~2–12 pts per match × 3 matches).
"""

# Position-specific scoring potential multipliers
# GKPs: clean sheet (6 pts) + saves bonus; DEF: goals + CS; MID/FWD: goals/assists
_POSITION_MULTIPLIER = {
    "GKP": 0.55,
    "DEF": 0.65,
    "MID": 0.85,
    "FWD": 1.00,
}

# Rough scale: a perfectly scored player (all signals = 1.0)
# across 3 group matches should predict ~30 pts (10 pts/match captain potential)
_SCALE = 30.0


def predict_points(
    player: dict,
    w_team_strength: float = 0.30,
    w_fixture_ease: float  = 0.40,
    w_form: float          = 0.20,
    w_position_role: float = 0.10,
) -> dict:
    """
    Return a prediction dict for a single player.
    player must contain: team_strength, fixture_ease, total_points, games_played, position
    """
    team_strength = player.get("team_strength", 0.5)
    fixture_ease  = player.get("fixture_ease", 0.5)
    position      = player.get("position", "MID")

    # Form: normalise total_points to 0–1 (cap at 30 = very high)
    total_pts   = player.get("total_points", 0)
    form_signal = min(total_pts / 30.0, 1.0)

    # Position role multiplier → signal (already 0–1)
    pos_role = _POSITION_MULTIPLIER.get(position, 0.8)

    # Weighted composite score (0–1)
    composite = (
        w_team_strength * team_strength +
        w_fixture_ease  * fixture_ease  +
        w_form          * form_signal   +
        w_position_role * pos_role
    )

    predicted = round(composite * _SCALE, 2)

    return {
        "predicted_points": predicted,
        "team_strength":    round(team_strength, 4),
        "fixture_ease":     round(fixture_ease, 4),
        "form_score":       round(form_signal, 4),
        "position_role":    round(pos_role, 4),
    }
