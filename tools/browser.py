"""Browser automation tools for FPL login and transfer execution.

Uses Playwright to interact with the FPL website for actions that
require authentication (making transfers).
"""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "fpl-copilot"
SESSION_FILE = CONFIG_DIR / "session.json"

# Module-level browser/page reference for reuse within a session
_browser = None
_page = None


async def _get_page():
    """Get or create a Playwright browser page with saved session cookies."""
    global _browser, _page

    if _page is not None:
        return _page

    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    _browser = await pw.chromium.launch(headless=True)

    context_opts = {}
    if SESSION_FILE.exists():
        with open(SESSION_FILE) as f:
            storage_state = json.load(f)
        context_opts["storage_state"] = storage_state

    context = await _browser.new_context(**context_opts)
    _page = await context.new_page()
    return _page


async def _save_session():
    """Save browser session cookies to disk."""
    if _page is None:
        return
    storage_state = await _page.context.storage_state()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SESSION_FILE, "w") as f:
        json.dump(storage_state, f)


async def fpl_login() -> dict:
    """Log into the FPL website using credentials from environment variables.

    Uses FPL_EMAIL and FPL_PASSWORD from your .env file to authenticate
    via the Premier League login page. Saves session cookies for reuse
    so you don't need to log in again during this session.

    Returns a dict with login status and any error message.
    """
    email = os.environ.get("FPL_EMAIL")
    password = os.environ.get("FPL_PASSWORD")

    if not email or not password:
        return {"success": False, "error": "FPL_EMAIL and FPL_PASSWORD must be set in .env"}

    try:
        page = await _get_page()

        await page.goto("https://users.premierleague.com/accounts/login/")
        await page.fill("input[name='login']", email)
        await page.fill("input[name='password']", password)
        await page.click("button[type='submit']")

        # Wait for redirect back to FPL
        await page.wait_for_url("**/fantasy.premierleague.com/**", timeout=15000)

        await _save_session()
        return {"success": True, "message": "Logged in successfully. Session saved."}

    except Exception as e:
        return {"success": False, "error": f"Login failed: {str(e)}"}


async def execute_transfer(player_out: str, player_in: str) -> dict:
    """Navigate to the FPL transfers page and select a transfer.

    Args:
        player_out: Name of the player to transfer out.
        player_in: Name of the player to transfer in.

    This sets up the transfer on the FPL website but does NOT confirm it.
    You must call confirm_transfers() separately to finalize.

    Returns a summary of the pending transfer for human review.
    """
    page = await _get_page()

    try:
        # Navigate to transfers page
        await page.goto("https://fantasy.premierleague.com/transfers")
        await page.wait_for_load_state("networkidle")

        # Search and select player to remove
        # Click on the player in the squad list
        player_out_el = page.locator(f"text={player_out}").first
        await player_out_el.click()

        # Wait for the replacement panel to appear, then search
        search_input = page.locator("input[type='search']").first
        await search_input.fill(player_in)
        await page.wait_for_timeout(1000)  # wait for search results

        # Select the first matching player
        player_in_el = page.locator(f"text={player_in}").first
        await player_in_el.click()

        # Wait for transfer to register
        await page.wait_for_timeout(500)

        return {
            "success": True,
            "pending_transfer": {
                "out": player_out,
                "in": player_in,
            },
            "message": (
                f"Transfer staged: {player_out} → {player_in}. "
                "This has NOT been confirmed yet. "
                "Call confirm_transfers() to finalize."
            ),
        }

    except Exception as e:
        return {"success": False, "error": f"Failed to stage transfer: {str(e)}"}


async def confirm_transfers() -> dict:
    """Confirm all pending transfers on the FPL website.

    WARNING: This is the only function that makes real, irreversible changes
    to your FPL team. It clicks the confirm button on the transfers page.

    This should NEVER be called without explicit user approval. The CLI
    will always show what is about to happen and ask for a 'y' confirmation
    before this function executes.

    Returns confirmation status and details of the completed transfers.
    """
    page = await _get_page()

    try:
        # Click the "Make Transfers" / confirm button
        confirm_btn = page.locator("button:has-text('Confirm')").first
        await confirm_btn.click()

        # Handle any confirmation dialog
        await page.wait_for_timeout(2000)

        await _save_session()
        return {
            "success": True,
            "message": "Transfers confirmed successfully!",
        }

    except Exception as e:
        return {"success": False, "error": f"Failed to confirm transfers: {str(e)}"}
