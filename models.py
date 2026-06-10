from typing import List, Optional
from pydantic import BaseModel


class OptimizeRequest(BaseModel):
    budget: int = 1000             # 10× display value (1000 = $100m)
    w_team_strength: float = 0.30
    w_fixture_ease:  float = 0.40
    w_form:          float = 0.20
    w_position_role: float = 0.10


class PlayerOut(BaseModel):
    id: int
    name: str
    short_name: str
    team: str
    team_id: int
    position: str                  # GKP / DEF / MID / FWD
    cost: float                    # display (e.g. 10.5)
    predicted_points: float        # 3-match group stage prediction
    predicted_g1: Optional[float] = None   # predicted pts game 1
    predicted_g2: Optional[float] = None   # predicted pts game 2
    predicted_g3: Optional[float] = None   # predicted pts game 3
    team_strength: float           # 0–1 normalised ELO rating
    fixture_ease: float            # 0–1 average ease of 3 group opponents
    form_score: float              # points scored so far this tournament
    position_role: float           # deprecated (kept for compat)
    total_points: int              # actual FIF fantasy points so far
    games_played: int
    goals: int
    assists: int
    clean_sheets: int
    picked_by: float               # % of managers who picked this player
    round_scores: Optional[dict] = None     # {"1": 4, "2": 1, "3": 6, ...}
    round_opponents: Optional[dict] = None  # {"1": "Algeria", "2": "Austria", ...}
    round_dates: Optional[dict] = None      # {"1": "2026-06-14", "2": "2026-06-20", ...}
    round_day_ranks: Optional[dict] = None  # {"1": 4, "2": 2, "3": 6} day rank within round
    status: str                    # "confirmed" / "unconfirmed" / "injured"


class SquadPlayer(PlayerOut):
    is_starter: bool


class OptimizeResponse(BaseModel):
    starters: List[SquadPlayer]
    bench: List[SquadPlayer]
    total_cost: float
    total_predicted_points: float
    captain_id: Optional[int] = None
    vice_captain_id: Optional[int] = None


class Fixture(BaseModel):
    id: int
    round_id: int
    stage: str
    home_team: str
    home_team_id: int
    away_team: str
    away_team_id: int
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    date: str
    status: str


class Round(BaseModel):
    id: int
    stage: str
    status: str
    start_date: str
    end_date: str
    fixtures: List[Fixture]


class GroupTeam(BaseModel):
    id: int
    name: str
    abbr: str
    rank: int
    strength: float   # 0–1 normalised


class GroupFixture(BaseModel):
    game: int           # 1/2/3 within group stage
    home_team: str
    home_team_id: int
    away_team: str
    away_team_id: int
    date: str
    status: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None


class Group(BaseModel):
    name: str            # "A" … "L"
    teams: List[GroupTeam]
    fixtures: List[GroupFixture]
