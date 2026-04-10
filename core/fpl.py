"""Async wrapper around the Fantasy Premier League API."""

import os
from difflib import SequenceMatcher

import aiohttp

from core.auth import get_access_token

BASE_URL = "https://fantasy.premierleague.com/api"

# In-memory cache for bootstrap data (fetched once per session)
_bootstrap_cache: dict | None = None


async def _get(session: aiohttp.ClientSession, path: str) -> dict | list:
    """Make a GET request to the FPL API."""
    async with session.get(f"{BASE_URL}{path}") as resp:
        resp.raise_for_status()
        return await resp.json()


async def _auth_session() -> aiohttp.ClientSession:
    """Create an aiohttp session with Bearer auth if a token is available."""
    token = await get_access_token()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return aiohttp.ClientSession(headers=headers)


async def _auth_get(path: str) -> dict | list:
    """Make an authenticated GET request to the FPL API."""
    async with await _auth_session() as session:
        return await _get(session, path)


async def _auth_post(path: str, payload: dict) -> dict:
    """Make an authenticated POST request to the FPL API."""
    async with await _auth_session() as session:
        async with session.post(
            f"{BASE_URL}{path}",
            json=payload,
            headers={"X-Requested-With": "XMLHttpRequest"},
        ) as resp:
            resp.raise_for_status()
            return await resp.json()


async def get_bootstrap() -> dict:
    """Fetch /bootstrap-static/ and cache it for the session.

    Returns the full bootstrap payload containing all players (elements),
    teams, element_types, and events (gameweeks).
    """
    global _bootstrap_cache
    if _bootstrap_cache is not None:
        return _bootstrap_cache

    async with aiohttp.ClientSession() as session:
        data = await _get(session, "/bootstrap-static/")
        _bootstrap_cache = data
        return data


async def get_current_gameweek() -> int:
    """Return the current gameweek number from bootstrap data."""
    data = await get_bootstrap()
    for event in data["events"]:
        if event["is_current"]:
            return event["id"]
    # If no current gameweek (e.g. between seasons), return the next one
    for event in data["events"]:
        if event["is_next"]:
            return event["id"]
    return 1


async def get_my_team(team_id: str | None = None, gameweek: int | None = None) -> dict:
    """Fetch the picks for a given team and gameweek.

    Args:
        team_id: FPL team ID. Defaults to FPL_TEAM_ID env var.
        gameweek: Gameweek number. Defaults to current gameweek.

    Returns:
        Dict with picks, automatic_subs, entry_history for the gameweek.
    """
    if team_id is None:
        team_id = os.environ["FPL_TEAM_ID"]
    if gameweek is None:
        gameweek = await get_current_gameweek()

    async with aiohttp.ClientSession() as session:
        return await _get(session, f"/entry/{team_id}/event/{gameweek}/picks/")


async def get_entry(team_id: str | None = None) -> dict:
    """Fetch the entry (manager) data for a team.

    Returns overall info including name, bank, transfers, chips, etc.
    """
    if team_id is None:
        team_id = os.environ["FPL_TEAM_ID"]

    async with aiohttp.ClientSession() as session:
        return await _get(session, f"/entry/{team_id}/")


async def get_player_by_name(name: str) -> dict | None:
    """Search bootstrap data for a player by name.

    Matches against web_name and full name (first_name + second_name).
    Uses case-insensitive substring matching, with fuzzy fallback.

    Returns the best matching player element dict, or None.
    """
    data = await get_bootstrap()
    name_lower = name.lower()

    # Exact substring match on web_name or full name
    candidates = []
    for player in data["elements"]:
        web_name = player["web_name"].lower()
        full_name = f"{player['first_name']} {player['second_name']}".lower()
        if name_lower == web_name or name_lower == full_name:
            return player
        if name_lower in web_name or name_lower in full_name:
            candidates.append(player)

    if candidates:
        # Return the best substring match (shortest web_name wins for specificity)
        return min(candidates, key=lambda p: len(p["web_name"]))

    # Fuzzy fallback using SequenceMatcher
    best_match = None
    best_ratio = 0.0
    for player in data["elements"]:
        for field in [player["web_name"], f"{player['first_name']} {player['second_name']}"]:
            ratio = SequenceMatcher(None, name_lower, field.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = player

    if best_ratio >= 0.6:
        return best_match
    return None


async def get_fixtures() -> list[dict]:
    """Fetch all fixtures and return upcoming (unfinished) ones with FDR.

    Each fixture includes: id, team_h, team_a, team_h_difficulty,
    team_a_difficulty, event (gameweek), finished.
    """
    async with aiohttp.ClientSession() as session:
        fixtures = await _get(session, "/fixtures/")
        return [f for f in fixtures if not f["finished"]]


async def get_player_summary(player_id: int) -> dict:
    """Fetch detailed summary for a player.

    Returns history (past gameweeks this season), fixtures (upcoming),
    and history_past (previous seasons).
    """
    async with aiohttp.ClientSession() as session:
        return await _get(session, f"/element-summary/{player_id}/")


# --- Authenticated endpoints ---


async def get_me() -> dict:
    """Fetch the authenticated user's profile.

    Returns player info including the entry (team) ID.
    Requires authentication.
    """
    return await _auth_get("/me/")


async def get_my_squad(team_id: str | None = None) -> dict:
    """Fetch the authenticated user's current squad.

    Returns picks, chips status, and transfer info.
    Requires authentication — the team_id must match the logged-in user.
    """
    if team_id is None:
        team_id = os.environ["FPL_TEAM_ID"]
    return await _auth_get(f"/my-team/{team_id}/")


async def make_transfer(
    team_id: str,
    gameweek: int,
    transfers: list[dict],
    confirm: bool = False,
    wildcard: bool = False,
    freehit: bool = False,
) -> dict:
    """Execute transfers via the FPL API.

    Args:
        team_id: The manager's entry/team ID.
        gameweek: Current gameweek number.
        transfers: List of dicts with element_in, element_out,
                   purchase_price, selling_price.
        confirm: If False, validates only (dry run). If True, executes.
        wildcard: Set True to play the wildcard chip.
        freehit: Set True to play the free hit chip.

    Returns the API response dict.
    """
    payload = {
        "confirmed": confirm,
        "entry": int(team_id),
        "event": gameweek,
        "transfers": transfers,
        "wildcard": wildcard,
        "freehit": freehit,
    }
    return await _auth_post("/transfers/", payload)


async def set_lineup(
    team_id: str,
    picks: list[dict],
    chip: str | None = None,
) -> dict:
    """Set the squad lineup, captaincy, and bench order.

    Args:
        team_id: The manager's entry/team ID.
        picks: List of 15 dicts with element, position (1-15),
               is_captain, is_vice_captain.
        chip: Optional chip to play — "bboost" or "3xc".

    Returns the API response dict.
    """
    payload = {
        "chip": chip,
        "picks": picks,
    }
    return await _auth_post(f"/my-team/{team_id}/", payload)
