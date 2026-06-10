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

# World Football Elo Ratings – pre-tournament 2026 (source: eloratings.net/2026_World_Cup)
# Ratings range from 1421 (Qatar) to 2157 (Spain).
# More precise than FIFA rankings: continuous, margin-of-victory weighted, zero-sum.
# Frozen at tournament start — no live fetch needed.
# Team names must match the WC2026 Fantasy API squad names exactly.
ELO_RATINGS: dict[str, int] = {
    "Spain":                  2157,
    "Argentina":              2114,
    "France":                 2063,
    "England":                2021,
    "Brazil":                 1991,
    "Portugal":               1986,
    "Colombia":               1982,
    "Netherlands":            1948,
    "Ecuador":                1938,
    "Germany":                1932,
    "Norway":                 1914,
    "Croatia":                1912,
    "Türkiye":                1911,
    "Japan":                  1906,
    "Belgium":                1894,
    "Uruguay":                1892,
    "Switzerland":            1891,
    "Mexico":                 1875,
    "Senegal":                1860,
    "Paraguay":               1834,
    "Austria":                1830,
    "Morocco":                1827,
    "Canada":                 1788,
    "Scotland":               1782,
    "Australia":              1777,
    "IR Iran":                1772,
    "Algeria":                1760,
    "Korea Republic":         1758,
    "Czechia":                1740,
    "Panama":                 1730,
    "USA":                    1726,
    "Uzbekistan":             1714,
    "Sweden":                 1712,
    "Egypt":                  1696,
    "Côte d'Ivoire":          1695,
    "Jordan":                 1680,
    "Congo DR":               1652,
    "Tunisia":                1628,
    "Iraq":                   1618,
    "Bosnia and Herzegovina": 1595,
    "Cabo Verde":             1578,
    "Saudi Arabia":           1576,
    "New Zealand":            1562,
    "Haiti":                  1548,
    "South Africa":           1517,
    "Ghana":                  1510,
    "Curaçao":                1434,
    "Qatar":                  1421,
}

CACHE_TTL_SECONDS = 300   # 5 min (data updates slowly during group stage)
SEMAPHORE_LIMIT   = 5
