"""OAuth authentication for the FPL API via PingOne DaVinci flow.

Implements the 5-step redirectless OAuth flow:
1. Initiate authorization with PKCE
2. Skip the bot-protection node
3. Submit credentials (email + password)
4. Continue through the login interstitial
5. Exchange authorization code for tokens

Tokens are stored in ~/.config/fpl-copilot/tokens.json and refreshed
automatically when expired.
"""

import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path

import aiohttp

CONFIG_DIR = Path.home() / ".config" / "fpl-copilot"
TOKEN_FILE = CONFIG_DIR / "tokens.json"

AUTH_BASE = "https://account.premierleague.com"
CLIENT_ID = "bfcbaf69-aade-4c1b-8f00-c1cb8a193030"
REDIRECT_URI = "https://fantasy.premierleague.com/"
SCOPES = "openid profile email"

# Module-level token cache
_tokens: dict | None = None


def _generate_pkce() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256)."""
    verifier = secrets.token_urlsafe(32)  # 43-char base64url string
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _load_tokens() -> dict | None:
    """Load tokens from disk if they exist."""
    global _tokens
    if _tokens is not None:
        return _tokens
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            _tokens = json.load(f)
        return _tokens
    return None


def _save_tokens(tokens: dict):
    """Save tokens to disk."""
    global _tokens
    _tokens = tokens
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    TOKEN_FILE.chmod(0o600)


def _is_token_expired(tokens: dict) -> bool:
    """Check if the access token has expired (with 60s buffer)."""
    expires_at = tokens.get("expires_at", 0)
    return time.time() >= (expires_at - 60)


async def _authorize(session: aiohttp.ClientSession, code_challenge: str) -> dict:
    """Step 1: Initiate the authorization flow with PKCE.

    Returns the DaVinci flow step containing connection/capability info.
    """
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "response_mode": "pi.flow",
        "scope": SCOPES,
        "redirect_uri": REDIRECT_URI,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    async with session.get(f"{AUTH_BASE}/as/authorize", params=params) as resp:
        resp.raise_for_status()
        return await resp.json()


async def _skip_protect_node(
    session: aiohttp.ClientSession,
    step: dict,
    interaction_id: str,
) -> dict:
    """Step 2: Skip the bot-protection (Protect) node.

    Returns the next DaVinci flow step (the login form).
    """
    connection_id = step["connectionId"]
    capability_name = step["capabilityName"]

    url = (
        f"{AUTH_BASE}/davinci/connections/{connection_id}"
        f"/capabilities/{capability_name}"
    )
    payload = {
        "id": step["id"],
        "eventName": "continue",
        "parameters": {
            "eventType": "submit",
            "data": {
                "actionKey": "continue",
                "formData": {"protectsdk": ""},
            },
        },
    }
    async with session.post(
        url,
        json=payload,
        params={"interactionId": interaction_id},
    ) as resp:
        resp.raise_for_status()
        return await resp.json()


async def _submit_credentials(
    session: aiohttp.ClientSession,
    step: dict,
    interaction_id: str,
    email: str,
    password: str,
) -> dict:
    """Step 3: Submit email and password to the DaVinci login form.

    Returns the DaVinci response containing the authorization code on success.
    Raises ValueError on invalid credentials.
    """
    connection_id = step["connectionId"]
    capability_name = step["capabilityName"]

    url = (
        f"{AUTH_BASE}/davinci/connections/{connection_id}"
        f"/capabilities/{capability_name}"
    )
    payload = {
        "id": step["id"],
        "eventName": "continue",
        "interactionId": interaction_id,
        "parameters": {
            "buttonValue": "SIGNON",
            "username": email,
            "password": password,
        },
    }
    async with session.post(
        url,
        json=payload,
        params={"interactionId": interaction_id},
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()

    # Check for error response
    if "code" in data and isinstance(data["code"], str) and "nvalid" in data["code"]:
        raise ValueError(f"Login failed: {data['code']}")

    return data


async def _continue_interstitial(
    session: aiohttp.ClientSession,
    step: dict,
    interaction_id: str,
) -> dict:
    """Step 4: Continue through the 'Logging you in...' interstitial.

    After credentials are accepted, DaVinci shows an interstitial page.
    We submit a continue event to get the authorization code.
    """
    connection_id = step["connectionId"]
    capability_name = step["capabilityName"]

    url = (
        f"{AUTH_BASE}/davinci/connections/{connection_id}"
        f"/capabilities/{capability_name}"
    )
    payload = {
        "id": step["id"],
        "eventName": "continue",
        "parameters": {
            "eventType": "submit",
            "data": {
                "actionKey": "continue",
                "formData": {"buttonValue": ""},
            },
        },
    }
    async with session.post(
        url,
        json=payload,
        params={"interactionId": interaction_id},
    ) as resp:
        resp.raise_for_status()
        return await resp.json()


async def _exchange_code(
    session: aiohttp.ClientSession,
    code: str,
    code_verifier: str,
) -> dict:
    """Step 5: Exchange the authorization code for tokens.

    Returns the token response (access_token, refresh_token, etc).
    """
    payload = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code": code,
        "code_verifier": code_verifier,
    }
    async with session.post(
        f"{AUTH_BASE}/as/token",
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://fantasy.premierleague.com",
        },
    ) as resp:
        resp.raise_for_status()
        return await resp.json()


async def _refresh_access_token(session: aiohttp.ClientSession, refresh_token: str) -> dict:
    """Use the refresh token to get a new access token."""
    payload = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }
    async with session.post(
        f"{AUTH_BASE}/as/token",
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://fantasy.premierleague.com",
        },
    ) as resp:
        resp.raise_for_status()
        return await resp.json()


async def login(email: str | None = None, password: str | None = None) -> dict:
    """Authenticate with FPL using the DaVinci OAuth flow.

    Args:
        email: FPL account email. Defaults to FPL_EMAIL env var.
        password: FPL account password. Defaults to FPL_PASSWORD env var.

    Returns:
        Dict with success status and message.
    """
    if email is None:
        email = os.environ.get("FPL_EMAIL")
    if password is None:
        password = os.environ.get("FPL_PASSWORD")

    if not email or not password:
        return {
            "success": False,
            "error": "FPL_EMAIL and FPL_PASSWORD must be set. Run: fpl-copilot init",
        }

    try:
        code_verifier, code_challenge = _generate_pkce()

        async with aiohttp.ClientSession() as session:
            # Step 1: Initiate authorization
            step1 = await _authorize(session, code_challenge)
            interaction_id = step1["interactionId"]

            # Step 2: Skip bot protection
            step2 = await _skip_protect_node(session, step1, interaction_id)

            # Step 3: Submit credentials
            step3 = await _submit_credentials(
                session, step2, interaction_id, email, password,
            )

            # Step 4: Continue through the "Logging you in..." interstitial
            # The interactionId may change after credential submission
            interaction_id = step3.get("interactionId", interaction_id)
            step4 = await _continue_interstitial(session, step3, interaction_id)

            # Extract authorization code from the response
            auth_response = step4.get("authorizeResponse", {})
            code = auth_response.get("code")
            if not code:
                return {
                    "success": False,
                    "error": f"No authorization code in response. Keys: {list(step4.keys())}",
                }

            # Step 5: Exchange code for tokens
            token_data = await _exchange_code(session, code, code_verifier)

        # Store tokens with expiry timestamp
        token_data["expires_at"] = time.time() + token_data.get("expires_in", 28800)
        _save_tokens(token_data)

        return {"success": True, "message": "Logged in successfully. Tokens saved."}

    except ValueError as e:
        return {"success": False, "error": str(e)}
    except aiohttp.ClientResponseError as e:
        return {"success": False, "error": f"HTTP {e.status}: {e.message}"}
    except Exception as e:
        return {"success": False, "error": f"Login failed: {e}"}


async def get_access_token() -> str | None:
    """Get a valid access token, refreshing if needed.

    Returns the access token string, or None if not authenticated.
    """
    tokens = _load_tokens()
    if tokens is None:
        return None

    if not _is_token_expired(tokens):
        return tokens["access_token"]

    # Try to refresh
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            new_tokens = await _refresh_access_token(session, refresh_token)
        new_tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 28800)
        # Keep the refresh token if the server didn't issue a new one
        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = refresh_token
        _save_tokens(new_tokens)
        return new_tokens["access_token"]
    except Exception:
        # Refresh failed — user needs to log in again
        return None


def clear_tokens():
    """Remove stored tokens (logout)."""
    global _tokens
    _tokens = None
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
