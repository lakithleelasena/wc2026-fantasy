# ── FIFA Fantasy World Cup 2026 – Config ─────────────────────────────────────

# WC2026 JSON endpoints (public, no auth required)
PLAYERS_URL   = "https://play.fifa.com/json/fantasy/players.json"
ROUNDS_URL    = "https://play.fifa.com/json/fantasy/rounds.json"
CHECKSUMS_URL = "https://play.fifa.com/json/fantasy/checksums.json"

# Squad rules (FIFA Fantasy Classic)
BUDGET      = 1000   # stored as 10× (i.e. 1000 = $100.0m); API price × 10
SQUAD_SIZE  = 15
STARTING_XI = 11

SQUAD_COMPOSITION = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
MIN_STARTING      = {"GKP": 1, "DEF": 3, "MID": 2, "FWD": 1}

MAX_PER_SQUAD = 3   # max players from the same national team

# Group stage: 3 rounds (each team plays 3 matches)
GROUP_STAGE_ROUNDS = 3

# Prediction weight defaults
W_TEAM_STRENGTH = 0.30
W_FIXTURE_EASE  = 0.40
W_FORM          = 0.20
W_POSITION_ROLE = 0.10

# FIFA World Rankings (June 2026) – team names match API exactly
# Used as team strength proxy: rank 1 → score 1.0, rank 48 → score ~0.0
FIFA_RANKINGS: dict[str, int] = {
    "Argentina":              1,
    "France":                 2,
    "England":                3,
    "Brazil":                 4,
    "Portugal":               5,
    "Spain":                  6,
    "Belgium":                7,
    "Netherlands":            8,
    "Germany":                9,
    "Morocco":               10,
    "USA":                   11,
    "Japan":                 12,
    "Senegal":               13,
    "Uruguay":               14,
    "Colombia":              15,
    "Mexico":                16,
    "Switzerland":           17,
    "Korea Republic":        18,
    "Ecuador":               19,
    "Canada":                20,
    "Croatia":               21,
    "Austria":               22,
    "Australia":             23,
    "IR Iran":               24,
    "Czechia":               25,
    "Norway":                26,
    "Sweden":                27,
    "Türkiye":               28,
    "Tunisia":               29,
    "Scotland":              30,
    "Ghana":                 31,
    "Algeria":               32,
    "South Africa":          33,
    "Côte d'Ivoire":         34,
    "Saudi Arabia":          35,
    "Paraguay":              36,
    "Panama":                37,
    "Egypt":                 38,
    "Qatar":                 39,
    "Bosnia and Herzegovina": 40,
    "Jordan":                41,
    "New Zealand":           42,
    "Iraq":                  43,
    "Congo DR":              44,
    "Uzbekistan":            45,
    "Cabo Verde":            46,
    "Haiti":                 47,
    "Curaçao":               48,
}

CACHE_TTL_SECONDS = 300   # 5 min (data updates slowly during group stage)
SEMAPHORE_LIMIT   = 5
