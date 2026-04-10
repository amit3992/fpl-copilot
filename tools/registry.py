"""Tool registry — wraps all tool functions as Anthropic tool definitions.

Exports:
    TOOLS: list of Anthropic tool definition dicts
    TOOL_HANDLERS: dict mapping tool name → async function
"""

from tools import team, news, analysis, browser


# --- Tool definitions for the Anthropic API ---

TOOLS = [
    # team.py
    {
        "name": "get_my_team",
        "description": (
            "Get your current FPL squad with position, price, form, and status "
            "for each player."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_budget",
        "description": (
            "Get your bank balance, free transfers available, total team value, "
            "and remaining chips."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_player_stats",
        "description": (
            "Get detailed stats for a specific player including form, ICT index, "
            "expected goals/assists, recent gameweek history, and upcoming fixtures."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {
                    "type": "string",
                    "description": "The player's name (partial matches accepted, e.g. 'Salah' or 'Palmer').",
                },
            },
            "required": ["player_name"],
        },
    },
    # news.py
    {
        "name": "get_injury_news",
        "description": (
            "Check the injury/availability status of all players in your current squad. "
            "Shows flagged players (doubtful, injured, suspended) with news details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_player_news",
        "description": (
            "Get detailed news and availability info for a specific player, "
            "including FPL status and recent web articles from BBC Sport and Sky Sports."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {
                    "type": "string",
                    "description": "The player's name (partial matches accepted).",
                },
            },
            "required": ["player_name"],
        },
    },
    # analysis.py
    {
        "name": "get_transfer_options",
        "description": (
            "Find the top 5 replacement options for a player, ranked by a composite "
            "score of form, points per game, and fixture difficulty. Only shows players "
            "within your budget and in the same position."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {
                    "type": "string",
                    "description": "Name of the player you want to replace.",
                },
            },
            "required": ["player_name"],
        },
    },
    {
        "name": "calculate_hit_value",
        "description": (
            "Calculate whether taking a 4-point transfer hit is worth it. "
            "Compares expected points over a horizon and only recommends the hit "
            "if the net gain exceeds 2 points."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_out": {
                    "type": "string",
                    "description": "Name of the player to sell.",
                },
                "player_in": {
                    "type": "string",
                    "description": "Name of the player to buy.",
                },
                "horizon": {
                    "type": "integer",
                    "description": "Number of gameweeks to project over (default 3).",
                    "default": 3,
                },
            },
            "required": ["player_out", "player_in"],
        },
    },
    {
        "name": "get_fixture_difficulty",
        "description": (
            "Show upcoming fixtures with FDR (Fixture Difficulty Rating) for a "
            "specific player. Ratings range from 1 (easy) to 5 (hard)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {
                    "type": "string",
                    "description": "The player's name (partial matches accepted).",
                },
                "gameweeks": {
                    "type": "integer",
                    "description": "Number of upcoming gameweeks to show (default 5).",
                    "default": 5,
                },
            },
            "required": ["player_name"],
        },
    },
    # browser.py
    {
        "name": "fpl_login",
        "description": (
            "Authenticate with the FPL API to enable transfers and lineup changes. "
            "Uses FPL_EMAIL and FPL_PASSWORD from config. Tokens are cached and "
            "auto-refreshed. Must be called before execute_transfer or confirm_transfers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "execute_transfer",
        "description": (
            "Stage a transfer via the FPL API (validates without confirming). "
            "This does NOT confirm the transfer — it only validates it for review. "
            "You must call confirm_transfers() separately after user approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_out": {
                    "type": "string",
                    "description": "Name of the player to transfer out.",
                },
                "player_in": {
                    "type": "string",
                    "description": "Name of the player to transfer in.",
                },
            },
            "required": ["player_out", "player_in"],
        },
    },
    {
        "name": "confirm_transfers",
        "description": (
            "Confirm all pending transfers via the FPL API. "
            "WARNING: This makes irreversible changes to your team. "
            "NEVER call this without showing the user exactly what will happen "
            "and receiving their explicit 'yes' approval first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# --- Handler mapping ---

TOOL_HANDLERS = {
    "get_my_team": team.get_my_team,
    "get_budget": team.get_budget,
    "get_player_stats": team.get_player_stats,
    "get_injury_news": news.get_injury_news,
    "get_player_news": news.get_player_news,
    "get_transfer_options": analysis.get_transfer_options,
    "calculate_hit_value": analysis.calculate_hit_value,
    "get_fixture_difficulty": analysis.get_fixture_difficulty,
    "fpl_login": browser.fpl_login,
    "execute_transfer": browser.execute_transfer,
    "confirm_transfers": browser.confirm_transfers,
}
