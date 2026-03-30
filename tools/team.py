"""Tools for viewing your FPL team, budget, and player stats."""

from core import fpl


POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
STATUS_MAP = {"a": "Available", "d": "Doubtful", "i": "Injured", "s": "Suspended", "u": "Unavailable"}


async def get_my_team() -> list[dict]:
    """Get your current FPL squad with position, price, form, and status for each player.

    Returns a list of players in your team with their key stats including
    name, position, current price, form, points per game, and availability status.
    """
    bootstrap = await fpl.get_bootstrap()
    elements = {p["id"]: p for p in bootstrap["elements"]}
    teams = {t["id"]: t["name"] for t in bootstrap["teams"]}

    picks_data = await fpl.get_my_team()
    picks = picks_data["picks"]

    squad = []
    for pick in picks:
        player = elements[pick["element"]]
        squad.append({
            "name": player["web_name"],
            "full_name": f"{player['first_name']} {player['second_name']}",
            "position": POSITION_MAP.get(player["element_type"], "???"),
            "team": teams.get(player["team"], "???"),
            "price": player["now_cost"] / 10,
            "form": float(player["form"]),
            "points_per_game": float(player["points_per_game"]),
            "total_points": player["total_points"],
            "status": STATUS_MAP.get(player["status"], player["status"]),
            "news": player.get("news", ""),
            "is_captain": pick["is_captain"],
            "is_vice_captain": pick["is_vice_captain"],
            "multiplier": pick["multiplier"],
        })

    return squad


async def get_budget() -> dict:
    """Get your bank balance, free transfers available, and remaining chips.

    Returns a dict with bank (in £m), free_transfers count, and a list of
    chips still available to play.
    """
    bootstrap = await fpl.get_bootstrap()
    entry = await fpl.get_entry()

    # Current gameweek entry_history has bank info
    current_gw = await fpl.get_current_gameweek()
    picks_data = await fpl.get_my_team(gameweek=current_gw)
    entry_history = picks_data.get("entry_history", {})

    # Chips played this season
    chips_played = [c["name"] for c in entry.get("chips", [])] if "chips" in entry else []
    all_chips = ["wildcard", "freehit", "bboost", "3xc"]
    chips_available = [c for c in all_chips if c not in chips_played]

    return {
        "bank": entry_history.get("bank", 0) / 10,
        "total_value": entry_history.get("value", 0) / 10,
        "free_transfers": entry_history.get("event_transfers", 0),
        "chips_available": chips_available,
        "team_name": entry.get("name", "Unknown"),
        "overall_rank": entry.get("summary_overall_rank"),
        "total_points": entry.get("summary_overall_points"),
    }


async def get_player_stats(player_name: str) -> dict | None:
    """Get detailed stats for a specific player by name.

    Args:
        player_name: The player's name (partial matches accepted).

    Returns stats including form, ICT index, expected goals/assists,
    ownership percentage, recent gameweek history, and upcoming fixtures.
    Returns None if the player is not found.
    """
    player = await fpl.get_player_by_name(player_name)
    if player is None:
        return None

    bootstrap = await fpl.get_bootstrap()
    teams = {t["id"]: t["name"] for t in bootstrap["teams"]}
    summary = await fpl.get_player_summary(player["id"])

    recent_history = summary.get("history", [])[-5:]  # last 5 GWs
    upcoming_fixtures = summary.get("fixtures", [])[:5]  # next 5

    return {
        "name": player["web_name"],
        "full_name": f"{player['first_name']} {player['second_name']}",
        "team": teams.get(player["team"], "???"),
        "position": POSITION_MAP.get(player["element_type"], "???"),
        "price": player["now_cost"] / 10,
        "form": float(player["form"]),
        "points_per_game": float(player["points_per_game"]),
        "total_points": player["total_points"],
        "goals_scored": player["goals_scored"],
        "assists": player["assists"],
        "clean_sheets": player["clean_sheets"],
        "ict_index": float(player["ict_index"]),
        "expected_goals": float(player.get("expected_goals", 0)),
        "expected_assists": float(player.get("expected_assists", 0)),
        "selected_by_percent": player["selected_by_percent"],
        "status": STATUS_MAP.get(player["status"], player["status"]),
        "news": player.get("news", ""),
        "recent_gameweeks": [
            {
                "gameweek": h["round"],
                "points": h["total_points"],
                "minutes": h["minutes"],
                "goals": h["goals_scored"],
                "assists": h["assists"],
            }
            for h in recent_history
        ],
        "upcoming_fixtures": [
            {
                "gameweek": f["event"],
                "opponent": teams.get(
                    f["team_a"] if f["is_home"] else f["team_h"], "???"
                ),
                "is_home": f["is_home"],
                "difficulty": f["difficulty"],
            }
            for f in upcoming_fixtures
        ],
    }
