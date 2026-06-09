# ── FIFA Fantasy World Cup 2026 – Config ─────────────────────────────────────

# Public JSON endpoints (no auth required)
PLAYERS_URL   = "https://play.fifa.com/json/players.json"
ROUNDS_URL    = "https://play.fifa.com/json/rounds.json"
CHECKSUMS_URL = "https://play.fifa.com/json/checksums.json"

# Squad rules (FIFA Fantasy Classic)
BUDGET      = 1000   # stored as 10× (i.e. 1000 = $100.0m)
SQUAD_SIZE  = 15
STARTING_XI = 11

# Position IDs → labels (same as Women's WC API)
POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

SQUAD_COMPOSITION = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
MIN_STARTING      = {"GKP": 1, "DEF": 3, "MID": 2, "FWD": 1}

MAX_PER_SQUAD = 3   # max players from the same national team

# Group stage: 3 rounds (each team plays 3 matches)
GROUP_STAGE_ROUNDS = 3

# Prediction weight defaults
# Signals available for a tournament (no club season stats):
#   team_strength  – FIFA world ranking proxy (how good is the player's team?)
#   fixture_ease   – how weak are their 3 group opponents?
#   form           – early-tournament points already scored (0 at start)
#   position_role  – attackers rewarded more for goals, defenders for clean sheets

W_TEAM_STRENGTH = 0.30
W_FIXTURE_EASE  = 0.40
W_FORM          = 0.20
W_POSITION_ROLE = 0.10

# FIFA World Rankings (June 2026 approximation) – used as team strength proxy
# Lower rank = stronger team. We invert and normalise to a 0–1 score.
# Top-48 WC teams ranked approximately (rank as of mid-2026):
FIFA_RANKINGS: dict[str, int] = {
    "Argentina":    1,
    "France":       2,
    "England":      3,
    "Brazil":       4,
    "Portugal":     5,
    "Spain":        6,
    "Belgium":      7,
    "Netherlands":  8,
    "Germany":      9,
    "Italy":       10,
    "Croatia":     11,
    "Morocco":     12,
    "USA":         13,
    "Japan":       14,
    "Senegal":     15,
    "Uruguay":     16,
    "Denmark":     17,
    "Mexico":      18,
    "Switzerland": 19,
    "Colombia":    20,
    "South Korea": 21,
    "Ecuador":     22,
    "Canada":      23,
    "Australia":   24,
    "Poland":      25,
    "Serbia":      26,
    "Iran":        27,
    "Cameroon":    28,
    "Costa Rica":  29,
    "Turkey":      30,
    "Ukraine":     31,
    "Tunisia":     32,
    "Ghana":       33,
    "Côte d'Ivoire": 34,
    "Saudi Arabia": 35,
    "Paraguay":    36,
    "Mali":        37,
    "Algeria":     38,
    "Venezuela":   39,
    "Chile":       40,
    "Austria":     41,
    "Wales":       42,
    "Egypt":       43,
    "Qatar":       44,
    "New Zealand": 45,
    "Jamaica":     46,
    "Panama":      47,
    "Bolivia":     48,
}

CACHE_TTL_SECONDS = 300   # 5 min (data updates slowly during group stage)
SEMAPHORE_LIMIT   = 5
