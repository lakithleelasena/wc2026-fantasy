from __future__ import annotations

import time
from typing import List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_BUILD_TS = int(time.time())

from fifa_client import fetch_all_data
from models import (
    Fixture,
    Group,
    OptimizeRequest,
    OptimizeResponse,
    PlayerOut,
    Round,
    SquadPlayer,
)
from config import W_FIXTURE_EASE, W_FORM, W_POSITION_ROLE, W_TEAM_STRENGTH
from optimizer import optimize_squad
from predictor import predict_points

app = FastAPI(title="WC 2026 Fantasy Optimizer")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_player_out(p: dict, pred: dict) -> dict:
    return {
        **p,
        "predicted_points": pred["predicted_points"],
        "team_strength":    pred["team_strength"],
        "fixture_ease":     pred["fixture_ease"],
        "form_score":       pred["form_score"],
        "position_role":    pred["position_role"],
        "cost_display":     round(p["cost"] / 10, 1),
    }


def _to_player_out(p: dict) -> PlayerOut:
    return PlayerOut(
        id=p["id"],
        name=p["name"],
        short_name=p.get("short_name", ""),
        team=p["team"],
        team_id=p["team_id"],
        position=p["position"],
        cost=round(p["cost"] / 10, 1),
        predicted_points=p["predicted_points"],
        team_strength=p["team_strength"],
        fixture_ease=p["fixture_ease"],
        form_score=p["form_score"],
        position_role=p["position_role"],
        total_points=p["total_points"],
        games_played=p["games_played"],
        goals=p["goals"],
        assists=p["assists"],
        clean_sheets=p["clean_sheets"],
        picked_by=p["picked_by"],
        round_scores=p["round_scores"],
        round_opponents=p.get("round_opponents"),
        status=p["status"],
    )


def _to_squad_player(p: dict, is_starter: bool) -> SquadPlayer:
    return SquadPlayer(
        **_to_player_out(p).model_dump(),
        is_starter=is_starter,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    resp = templates.TemplateResponse(
        "index.html", {"request": request, "cache_bust": _BUILD_TS}
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/players", response_model=List[PlayerOut])
async def get_players(
    w_team_strength: float = W_TEAM_STRENGTH,
    w_fixture_ease:  float = W_FIXTURE_EASE,
    w_form:          float = W_FORM,
    w_position_role: float = W_POSITION_ROLE,
):
    data = await fetch_all_data()
    result = []
    for p in data["players"]:
        pred = predict_points(p, w_team_strength, w_fixture_ease, w_form, w_position_role)
        out = _build_player_out(p, pred)
        result.append(_to_player_out(out))
    result.sort(key=lambda x: x.predicted_points, reverse=True)
    return result


@app.post("/api/optimize", response_model=OptimizeResponse)
async def run_optimize(req: OptimizeRequest):
    data = await fetch_all_data()

    enriched = []
    for p in data["players"]:
        pred = predict_points(
            p,
            req.w_team_strength,
            req.w_fixture_ease,
            req.w_form,
            req.w_position_role,
        )
        out = _build_player_out(p, pred)
        enriched.append(out)

    result = optimize_squad(enriched, budget=req.budget)

    starters, bench = [], []
    total_cost = 0.0
    total_pts  = 0.0

    for p in result["starters"]:
        total_cost += p["cost"] / 10
        total_pts  += p["predicted_points"]
        starters.append(_to_squad_player(p, True))

    for p in result["bench"]:
        total_cost += p["cost"] / 10
        bench.append(_to_squad_player(p, False))

    # Sort by position
    pos_order = {"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}
    starters.sort(key=lambda s: pos_order.get(s.position, 9))
    bench.sort(key=lambda s: pos_order.get(s.position, 9))

    # Captain = highest predicted non-GKP starter
    eligible = sorted(
        [s for s in starters if s.position != "GKP"],
        key=lambda s: s.predicted_points,
        reverse=True,
    )
    captain_id      = eligible[0].id if eligible else None
    vice_captain_id = eligible[1].id if len(eligible) > 1 else None

    return OptimizeResponse(
        starters=starters,
        bench=bench,
        total_cost=round(total_cost, 1),
        total_predicted_points=round(total_pts, 2),
        captain_id=captain_id,
        vice_captain_id=vice_captain_id,
    )


@app.get("/api/groups", response_model=List[Group])
async def get_groups():
    from models import GroupTeam, GroupFixture
    data = await fetch_all_data()
    result = []
    for g in data["groups"]:
        result.append(Group(
            name=g["name"],
            teams=[GroupTeam(**t) for t in g["teams"]],
            fixtures=[GroupFixture(**f) for f in g["fixtures"]],
        ))
    return result


@app.get("/api/fixtures", response_model=List[Round])
async def get_fixtures():
    data = await fetch_all_data()
    rounds = []
    for rnd in data["group_rounds"]:
        fixtures = []
        for m in rnd.get("tournaments", []):
            fixtures.append(Fixture(
                id=m["id"],
                round_id=rnd["id"],
                stage=rnd["stage"],
                home_team=m.get("homeSquadName", ""),
                home_team_id=m["homeSquadId"],
                away_team=m.get("awaySquadName", ""),
                away_team_id=m["awaySquadId"],
                home_score=m.get("homeScore"),
                away_score=m.get("awayScore"),
                date=m.get("date", ""),
                status=m.get("status", "scheduled"),
            ))
        rounds.append(Round(
            id=rnd["id"],
            stage=rnd["stage"],
            status=rnd["status"],
            start_date=rnd["startDate"],
            end_date=rnd["endDate"],
            fixtures=fixtures,
        ))
    return rounds
