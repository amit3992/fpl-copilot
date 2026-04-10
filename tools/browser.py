"""Tools for FPL login and transfer execution via the API.

Uses the DaVinci OAuth flow for authentication and direct API calls
for transfers and lineup management. No browser automation required.
"""

import os

from core import fpl
from core.auth import login as auth_login, get_access_token


async def fpl_login() -> dict:
    """Log into FPL using the OAuth API flow.

    Uses FPL_EMAIL and FPL_PASSWORD from your config to authenticate
    via the PingOne DaVinci OAuth flow. Saves tokens for reuse so you
    don't need to log in again for ~8 hours (auto-refreshes after that).

    Returns a dict with login status and any error message.
    """
    # Check if we already have a valid token
    token = await get_access_token()
    if token:
        return {"success": True, "message": "Already authenticated (token valid)."}

    return await auth_login()


async def execute_transfer(player_out: str, player_in: str) -> dict:
    """Stage a transfer via the FPL API (dry run).

    Args:
        player_out: Name of the player to transfer out.
        player_in: Name of the player to transfer in.

    Validates the transfer without confirming it. You must call
    confirm_transfers() separately to finalize.

    Returns a summary of the pending transfer for human review.
    """
    token = await get_access_token()
    if not token:
        return {"success": False, "error": "Not logged in. Call fpl_login first."}

    try:
        # Resolve player names to IDs and prices
        bootstrap = await fpl.get_bootstrap()
        elements = {p["id"]: p for p in bootstrap["elements"]}

        player_out_data = await fpl.get_player_by_name(player_out)
        if not player_out_data:
            return {"success": False, "error": f"Player not found: {player_out}"}

        player_in_data = await fpl.get_player_by_name(player_in)
        if not player_in_data:
            return {"success": False, "error": f"Player not found: {player_in}"}

        team_id = os.environ["FPL_TEAM_ID"]
        gameweek = await fpl.get_current_gameweek()

        # Get selling price from current squad
        squad = await fpl.get_my_squad(team_id)
        selling_price = None
        for pick in squad.get("picks", []):
            if pick["element"] == player_out_data["id"]:
                selling_price = pick["selling_price"]
                break

        if selling_price is None:
            return {
                "success": False,
                "error": f"{player_out_data['web_name']} is not in your squad.",
            }

        transfer = {
            "element_in": player_in_data["id"],
            "element_out": player_out_data["id"],
            "purchase_price": player_in_data["now_cost"],
            "selling_price": selling_price,
        }

        # Dry run — validate without confirming
        result = await fpl.make_transfer(
            team_id=team_id,
            gameweek=gameweek,
            transfers=[transfer],
            confirm=False,
        )

        return {
            "success": True,
            "pending_transfer": {
                "out": player_out_data["web_name"],
                "out_id": player_out_data["id"],
                "in": player_in_data["web_name"],
                "in_id": player_in_data["id"],
                "selling_price": selling_price / 10,
                "purchase_price": player_in_data["now_cost"] / 10,
            },
            "validation": result,
            "message": (
                f"Transfer validated: {player_out_data['web_name']} "
                f"(${selling_price / 10}m) -> {player_in_data['web_name']} "
                f"(${player_in_data['now_cost'] / 10}m). "
                "This has NOT been confirmed yet. "
                "Call confirm_transfers() to finalize."
            ),
        }

    except Exception as e:
        return {"success": False, "error": f"Failed to stage transfer: {e}"}


async def confirm_transfers() -> dict:
    """Confirm the most recently staged transfer via the FPL API.

    WARNING: This makes irreversible changes to your team.
    NEVER call this without explicit user approval.

    Returns confirmation status and details.
    """
    token = await get_access_token()
    if not token:
        return {"success": False, "error": "Not logged in. Call fpl_login first."}

    try:
        team_id = os.environ["FPL_TEAM_ID"]
        gameweek = await fpl.get_current_gameweek()

        # Re-read the pending transfer from the last execute_transfer call
        # The FPL API handles pending state server-side, so we just confirm
        # with the same transfer details
        result = await fpl.make_transfer(
            team_id=team_id,
            gameweek=gameweek,
            transfers=[],  # Empty confirms the pending transfer
            confirm=True,
        )

        return {
            "success": True,
            "message": "Transfers confirmed successfully!",
            "result": result,
        }

    except Exception as e:
        return {"success": False, "error": f"Failed to confirm transfers: {e}"}
