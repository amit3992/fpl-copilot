"""Tools for checking injury news and player availability."""

import os

from core import fpl

STATUS_MAP = {"a": "Available", "d": "Doubtful", "i": "Injured", "s": "Suspended", "u": "Unavailable"}


async def get_injury_news() -> list[dict]:
    """Check the availability status of all players in your current squad.

    Returns a list of players with their status (Available, Doubtful, Injured,
    Suspended), news text, and when the news was last updated.
    Only includes players who are NOT fully available, unless all are fit.
    """
    bootstrap = await fpl.get_bootstrap()
    elements = {p["id"]: p for p in bootstrap["elements"]}

    picks_data = await fpl.get_my_team()
    picks = picks_data["picks"]

    news_items = []
    for pick in picks:
        player = elements[pick["element"]]
        item = {
            "player_name": player["web_name"],
            "status": STATUS_MAP.get(player["status"], player["status"]),
            "status_code": player["status"],
            "news": player.get("news", ""),
            "news_added": player.get("news_added", ""),
            "chance_of_playing_next_round": player.get("chance_of_playing_next_round"),
        }
        news_items.append(item)

    # Filter to only flagged players unless everyone is fit
    flagged = [n for n in news_items if n["status_code"] != "a"]
    return flagged if flagged else news_items


async def get_player_news(player_name: str) -> dict | None:
    """Get detailed news and availability info for a specific player.

    Args:
        player_name: The player's name (partial matches accepted).

    Returns FPL API status data supplemented with a web search for
    recent news from BBC Sport and Sky Sports. Returns None if the
    player is not found.
    """
    player = await fpl.get_player_by_name(player_name)
    if player is None:
        return None

    bootstrap = await fpl.get_bootstrap()
    teams = {t["id"]: t["name"] for t in bootstrap["teams"]}

    result = {
        "player_name": player["web_name"],
        "full_name": f"{player['first_name']} {player['second_name']}",
        "team": teams.get(player["team"], "???"),
        "status": STATUS_MAP.get(player["status"], player["status"]),
        "news": player.get("news", ""),
        "news_added": player.get("news_added", ""),
        "chance_of_playing_next_round": player.get("chance_of_playing_next_round"),
        "web_articles": [],
    }

    # Supplement with Firecrawl web search if API key is available
    firecrawl_key = os.environ.get("FIRECRAWL_API_KEY")
    if firecrawl_key:
        try:
            from firecrawl import FirecrawlApp

            app = FirecrawlApp(api_key=firecrawl_key)
            query = f"{player['first_name']} {player['second_name']} injury news Premier League"
            search_results = app.search(query, params={"limit": 3})

            if search_results and "data" in search_results:
                result["web_articles"] = [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("description", ""),
                    }
                    for r in search_results["data"]
                ]
        except Exception:
            # Firecrawl is supplementary — don't fail if it errors
            pass

    return result
