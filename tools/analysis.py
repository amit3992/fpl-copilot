"""Tools for transfer analysis, fixture difficulty, and hit calculations."""

from core import fpl, scoring


POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


async def get_transfer_options(player_name: str) -> dict | None:
    """Find the top 5 replacement options for a player within your budget.

    Args:
        player_name: Name of the player you want to replace.

    Searches for players in the same position, affordable within your
    current budget plus the outgoing player's sale price. Ranks them
    using the composite scoring formula (form, PPG, fixture difficulty).
    Returns None if the player is not found.
    """
    player_out = await fpl.get_player_by_name(player_name)
    if player_out is None:
        return None

    bootstrap = await fpl.get_bootstrap()
    teams = {t["id"]: t["name"] for t in bootstrap["teams"]}
    fixtures = await fpl.get_fixtures()

    # Get budget
    current_gw = await fpl.get_current_gameweek()
    picks_data = await fpl.get_my_team(gameweek=current_gw)
    entry_history = picks_data.get("entry_history", {})
    bank = entry_history.get("bank", 0)  # in tenths of £m

    # Budget = bank + selling price of outgoing player
    sell_price = player_out["now_cost"]  # approximate (actual may differ)
    budget = bank + sell_price

    # Find all players in same position, within budget, not on your team
    my_player_ids = {p["element"] for p in picks_data["picks"]}
    position = player_out["element_type"]

    candidates = [
        p for p in bootstrap["elements"]
        if p["element_type"] == position
        and p["now_cost"] <= budget
        and p["id"] not in my_player_ids
        and p["status"] == "a"  # only available players
    ]

    # Score and rank
    ranked = scoring.rank_players_by_position(candidates, position, fixtures)

    top_5 = ranked[:5]
    return {
        "player_out": {
            "name": player_out["web_name"],
            "position": POSITION_MAP.get(position, "???"),
            "price": player_out["now_cost"] / 10,
        },
        "budget_available": budget / 10,
        "recommendations": [
            {
                "name": p["web_name"],
                "team": teams.get(p["team"], "???"),
                "price": p["now_cost"] / 10,
                "form": float(p["form"]),
                "points_per_game": float(p["points_per_game"]),
                "composite_score": round(p["composite_score"], 2),
            }
            for p in top_5
        ],
    }


async def calculate_hit_value(
    player_out: str, player_in: str, horizon: int = 3
) -> dict | None:
    """Calculate whether taking a transfer hit is worth it.

    Args:
        player_out: Name of the player to sell.
        player_in: Name of the player to buy.
        horizon: Number of gameweeks to project over (default 3).

    Computes expected point gain over the horizon minus the 4-point hit cost.
    Only recommends the hit if net gain exceeds 2 points.
    Returns None if either player is not found.
    """
    p_out = await fpl.get_player_by_name(player_out)
    p_in = await fpl.get_player_by_name(player_in)

    if p_out is None or p_in is None:
        return None

    fixtures = await fpl.get_fixtures()
    return scoring.calculate_hit_value(p_out, p_in, fixtures, horizon)


async def get_fixture_difficulty(player_name: str, gameweeks: int = 5) -> dict | None:
    """Show upcoming fixtures with FDR ratings for a specific player.

    Args:
        player_name: The player's name (partial matches accepted).
        gameweeks: Number of upcoming gameweeks to show (default 5).

    Returns the player's upcoming fixtures with opponent, home/away,
    and difficulty rating (1=easy, 5=hard). Returns None if the player
    is not found.
    """
    player = await fpl.get_player_by_name(player_name)
    if player is None:
        return None

    bootstrap = await fpl.get_bootstrap()
    teams = {t["id"]: t["name"] for t in bootstrap["teams"]}
    fixtures = await fpl.get_fixtures()

    team_id = player["team"]
    upcoming = []
    for f in fixtures:
        if len(upcoming) >= gameweeks:
            break
        if f["team_h"] == team_id:
            upcoming.append({
                "gameweek": f["event"],
                "opponent": teams.get(f["team_a"], "???"),
                "is_home": True,
                "difficulty": f["team_h_difficulty"],
            })
        elif f["team_a"] == team_id:
            upcoming.append({
                "gameweek": f["event"],
                "opponent": teams.get(f["team_h"], "???"),
                "is_home": False,
                "difficulty": f["team_a_difficulty"],
            })

    return {
        "player": player["web_name"],
        "team": teams.get(team_id, "???"),
        "fixtures": upcoming,
    }
