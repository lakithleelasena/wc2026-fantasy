"""
FIFA Fantasy WC2026 – Official Scoring Rules
Source: play.fifa.com/fantasy game-rules (WC2026 edition)
Based on published WC2022 Fantasy ruleset (WC2026 uses the same structure).
"""

# Points per event, by position
SCORING: dict[str, dict[str, float]] = {
    "GKP": {
        "appearance_part": 1,        # played 1–59 min
        "appearance_full": 2,        # played 60+ min
        "goal":            10,
        "assist":          3,
        "clean_sheet":     6,        # 60+ min, 0 goals conceded
        "goals_conceded_per_2": -1,  # per 2 goals conceded (60+ min)
        "yellow_card":     -1,
        "red_card":        -3,
        "saves_per_3":     1,        # +1 for every 3 saves
        "penalty_save":    5,
        "penalty_miss":    -2,
    },
    "DEF": {
        "appearance_part": 1,
        "appearance_full": 2,
        "goal":            8,
        "assist":          3,
        "clean_sheet":     6,
        "goals_conceded_per_2": -1,
        "yellow_card":     -1,
        "red_card":        -3,
        "penalty_miss":    -2,
    },
    "MID": {
        "appearance_part": 1,
        "appearance_full": 2,
        "goal":            6,
        "assist":          3,
        "clean_sheet":     1,
        "goals_conceded_per_2": 0,
        "yellow_card":     -1,
        "red_card":        -3,
        "penalty_miss":    -2,
    },
    "FWD": {
        "appearance_part": 1,
        "appearance_full": 2,
        "goal":            5,
        "assist":          3,
        "clean_sheet":     0,
        "goals_conceded_per_2": 0,
        "yellow_card":     -1,
        "red_card":        -3,
        "penalty_miss":    -2,
    },
}

# ── Share of team goals/assists by position group ─────────────────────────────
# Based on historical WC data: FWDs score ~55% of goals, MIDs ~35%, DEFs ~9%, GKPs ~1%
GOAL_POS_SHARE: dict[str, float] = {
    "GKP": 0.01,
    "DEF": 0.09,
    "MID": 0.35,
    "FWD": 0.55,
}

# Assists: MIDs provide ~42%, FWDs ~39%, DEFs ~18%, GKPs ~1%
ASSIST_POS_SHARE: dict[str, float] = {
    "GKP": 0.01,
    "DEF": 0.18,
    "MID": 0.42,
    "FWD": 0.39,
}

# ── Per-game rate assumptions ─────────────────────────────────────────────────
YELLOW_CARD_RATE  = 0.07   # ~7% chance of yellow per player per game
RED_CARD_RATE     = 0.005  # ~0.5% chance of red per player per game
ASSIST_RATE       = 0.75   # ~75% of goals have a recorded assist
GK_SAVES_PER_GAME = 3.5    # avg saves per GKP per game (drives save bonus)
