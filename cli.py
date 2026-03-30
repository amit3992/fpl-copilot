"""FPL Copilot — conversational CLI for managing your Fantasy Premier League team."""

import asyncio
import json
import os
import sys
from pathlib import Path

import aiosqlite
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.status import Status

import anthropic
from tools.registry import TOOLS, TOOL_HANDLERS

console = Console()

CONFIG_DIR = Path.home() / ".config" / "fpl-copilot"
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_PATH = CONFIG_DIR / "fpl_copilot.db"

DB_SCHEMA = """\
CREATE TABLE IF NOT EXISTS session_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transfer_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gameweek INTEGER,
    player_out TEXT,
    player_in TEXT,
    hit_taken INTEGER DEFAULT 0,
    net_gain_projected FLOAT,
    reasoning TEXT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """\
You are FPL Copilot, an expert Fantasy Premier League assistant. You help the user \
manage their FPL team by analyzing players, suggesting transfers, checking fixtures, \
and executing transfers when asked.

Guidelines:
- Always check the user's current team before making suggestions.
- When recommending transfers, explain your reasoning using form, fixtures, and expected points.
- Before executing any transfer, clearly summarize what will happen and wait for user confirmation.
- NEVER call confirm_transfers() without the user explicitly saying "yes" or "y".
- Be concise but thorough. Use data to back up your advice.
- If the user asks about a player, look up their stats before answering.
- Reference fixture difficulty when discussing upcoming gameweeks.
"""

# Conversation history for the session
conversation: list[dict] = []
debug_mode = False


def load_config() -> dict:
    """Load config from ~/.config/fpl-copilot/config.json."""
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(config: dict):
    """Save config to ~/.config/fpl-copilot/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    # Restrict permissions — this file has secrets
    CONFIG_FILE.chmod(0o600)


def apply_config(config: dict):
    """Set environment variables from config so the rest of the app can use os.environ."""
    for key in ("ANTHROPIC_API_KEY", "FPL_TEAM_ID", "FPL_EMAIL", "FPL_PASSWORD", "FIRECRAWL_API_KEY"):
        value = config.get(key, "")
        if value:
            os.environ[key] = value


def run_init():
    """Interactive setup — prompts for credentials and saves to config."""
    console.print()
    console.print(Panel.fit(
        "[bold green]FPL Copilot Setup[/bold green]\n"
        "[dim]This will save your config to ~/.config/fpl-copilot/config.json[/dim]",
        border_style="green",
    ))
    console.print()

    existing = load_config()

    def ask(label: str, key: str, required: bool = False, password: bool = False) -> str:
        default = existing.get(key, "")
        suffix = "" if not default else f" [dim](press Enter to keep current)[/dim]"
        req = " [red](required)[/red]" if required else " [dim](optional)[/dim]"
        console.print(f"  {label}{req}{suffix}")
        value = Prompt.ask("  ", default=default, password=password)
        return value.strip()

    config = {}

    config["ANTHROPIC_API_KEY"] = ask("Anthropic API Key", "ANTHROPIC_API_KEY", required=True, password=True)
    console.print()

    config["FPL_TEAM_ID"] = ask(
        "FPL Team ID (from fantasy.premierleague.com/entry/XXXXXXX/...)",
        "FPL_TEAM_ID",
        required=True,
    )
    console.print()

    console.print("  [dim]FPL login is only needed if you want to execute transfers.[/dim]")
    config["FPL_EMAIL"] = ask("FPL Email", "FPL_EMAIL")
    config["FPL_PASSWORD"] = ask("FPL Password", "FPL_PASSWORD", password=True)
    console.print()

    config["FIRECRAWL_API_KEY"] = ask("Firecrawl API Key (for enhanced news)", "FIRECRAWL_API_KEY", password=True)

    save_config(config)

    console.print()
    console.print(f"  [green]Config saved to {CONFIG_FILE}[/green]")
    console.print("  [dim]Run [bold]fpl-copilot[/bold] to start chatting.[/dim]")
    console.print()


async def init_db():
    """Initialize SQLite database from schema if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(DB_SCHEMA)
        await db.commit()


async def save_transfer(gameweek: int, player_out: str, player_in: str,
                        hit_taken: int, net_gain: float, reasoning: str):
    """Record a completed transfer in the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO transfer_history (gameweek, player_out, player_in, hit_taken, net_gain_projected, reasoning) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (gameweek, player_out, player_in, hit_taken, net_gain, reasoning),
        )
        await db.commit()


async def get_transfer_history() -> list[dict]:
    """Load past transfers from the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM transfer_history ORDER BY executed_at DESC LIMIT 20") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def print_welcome():
    """Print the welcome banner with current team info."""
    from core.fpl import get_current_gameweek, get_entry

    console.print()
    console.print(Panel.fit(
        "[bold green]FPL Copilot[/bold green]\n"
        "[dim]Your AI-powered Fantasy Premier League assistant[/dim]",
        border_style="green",
    ))

    try:
        entry = await get_entry()
        gw = await get_current_gameweek()
        console.print(f"  Team: [bold]{entry.get('name', 'Unknown')}[/bold]")
        console.print(f"  Gameweek: [cyan]{gw}[/cyan]")
        console.print(f"  Overall rank: [yellow]{entry.get('summary_overall_rank', 'N/A'):,}[/yellow]")
        console.print(f"  Total points: [yellow]{entry.get('summary_overall_points', 'N/A')}[/yellow]")
    except Exception:
        console.print("  [dim]Could not load team info. Check your config with: fpl-copilot init[/dim]")

    console.print()
    console.print("[dim]Commands: /quit  /clear  /history  /debug[/dim]")
    console.print()


async def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return the result as a JSON string."""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        result = await handler(**args)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_special_command(command: str) -> bool:
    """Handle special slash commands. Returns True if handled."""
    global debug_mode

    cmd = command.strip().lower()

    if cmd in ("/quit", "/exit"):
        console.print("[dim]Goodbye![/dim]")
        sys.exit(0)

    if cmd == "/clear":
        conversation.clear()
        console.print("[dim]Conversation history cleared.[/dim]")
        return True

    if cmd == "/history":
        if not conversation:
            console.print("[dim]No conversation history yet.[/dim]")
        else:
            for msg in conversation:
                role = msg["role"]
                if role == "user":
                    content = msg["content"] if isinstance(msg["content"], str) else "[tool result]"
                    console.print(f"  [bold green]>[/bold green] {content}")
                elif role == "assistant":
                    if isinstance(msg["content"], str):
                        console.print(f"  [bold green]Claude:[/bold green] {msg['content'][:100]}...")
                    else:
                        console.print(f"  [bold green]Claude:[/bold green] [dim](tool use)[/dim]")
        return True

    if cmd == "/debug":
        debug_mode = not debug_mode
        state = "on" if debug_mode else "off"
        console.print(f"[dim]Debug mode: {state}[/dim]")
        return True

    return False


async def chat_turn(user_input: str):
    """Process one turn of the conversation."""
    client = anthropic.Anthropic()

    conversation.append({"role": "user", "content": user_input})

    # Build past transfer context
    history = await get_transfer_history()
    transfer_context = ""
    if history:
        transfer_context = "\n\nRecent transfer history:\n"
        for t in history[:5]:
            transfer_context += f"- GW{t['gameweek']}: {t['player_out']} → {t['player_in']} ({t['reasoning']})\n"

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT + transfer_context,
            tools=TOOLS,
            messages=conversation,
        )

        # Collect all content blocks
        assistant_content = response.content
        conversation.append({"role": "assistant", "content": assistant_content})

        # Check if we need to process tool calls
        tool_use_blocks = [b for b in assistant_content if b.type == "tool_use"]

        if not tool_use_blocks:
            # No tool calls — print the text response
            for block in assistant_content:
                if block.type == "text" and block.text:
                    console.print()
                    console.print(Markdown(block.text))
                    console.print()
            break

        # Process each tool call
        tool_results = []
        for tool_block in tool_use_blocks:
            tool_name = tool_block.name
            tool_args = tool_block.input

            # Print any text before the tool call
            for block in assistant_content:
                if block.type == "text" and block.text:
                    console.print()
                    console.print(Markdown(block.text))

            if debug_mode:
                args_str = ", ".join(f"{k}={v!r}" for k, v in tool_args.items()) if tool_args else ""
                console.print(f"[dim]  -> {tool_name}({args_str})[/dim]")

            # Human gate for confirm_transfers
            if tool_name == "confirm_transfers":
                console.print()
                console.print(Panel(
                    "[bold red]Transfer Confirmation Required[/bold red]\n\n"
                    "The transfers staged above are about to be confirmed.\n"
                    "This action is [bold]irreversible[/bold].",
                    border_style="red",
                ))
                answer = Prompt.ask("Confirm this transfer? [y/N]", default="n")
                if answer.lower() in ("y", "yes"):
                    with Status("[bold green]Confirming transfers...", console=console):
                        result = await execute_tool(tool_name, tool_args)
                    console.print("[green]Transfers confirmed.[/green]")
                else:
                    result = json.dumps({"cancelled": True, "message": "User cancelled the transfer."})
                    console.print("[yellow]Transfer cancelled.[/yellow]")
            else:
                with Status(f"[bold cyan]Checking {tool_name}...", console=console, spinner="dots"):
                    result = await execute_tool(tool_name, tool_args)

            if debug_mode:
                try:
                    parsed = json.loads(result)
                    pretty = json.dumps(parsed, indent=2, default=str)
                    # Truncate long debug output
                    lines = pretty.split("\n")
                    if len(lines) > 15:
                        pretty = "\n".join(lines[:15]) + f"\n  ... ({len(lines) - 15} more lines)"
                    console.print(f"[dim]  <- {pretty}[/dim]")
                except json.JSONDecodeError:
                    console.print(f"[dim]  <- {result[:200]}[/dim]")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": result,
            })

        # Send tool results back to Claude
        conversation.append({"role": "user", "content": tool_results})


async def main():
    """Main entry point — run the chat loop."""
    # Load config from ~/.config/fpl-copilot/config.json
    config = load_config()
    if not config:
        console.print("[yellow]No config found. Run [bold]fpl-copilot init[/bold] to set up.[/yellow]")
        sys.exit(1)

    apply_config(config)

    # Validate required keys
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]Error: Anthropic API key not configured. Run [bold]fpl-copilot init[/bold].[/red]")
        sys.exit(1)

    if not os.environ.get("FPL_TEAM_ID"):
        console.print("[red]Error: FPL Team ID not configured. Run [bold]fpl-copilot init[/bold].[/red]")
        sys.exit(1)

    # Initialize database
    await init_db()

    # Welcome banner
    await print_welcome()

    # Main chat loop
    while True:
        try:
            user_input = console.input("[bold green]>[/bold green] ")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input.strip():
            continue

        # Check for special commands
        if user_input.startswith("/"):
            handled = await handle_special_command(user_input)
            if handled:
                continue

        try:
            await chat_turn(user_input)
        except anthropic.APIError as e:
            console.print(f"[red]API error: {e}[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            if debug_mode:
                import traceback
                console.print(f"[dim]{traceback.format_exc()}[/dim]")


VERSION = "0.1.3"


def main_sync():
    """Sync entry point — routes subcommands."""
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "init":
            run_init()
        elif cmd in ("--version", "-v", "version"):
            console.print(f"fpl-copilot {VERSION}")
        elif cmd in ("--help", "-h", "help"):
            console.print(f"[bold]fpl-copilot[/bold] {VERSION}\n")
            console.print("Usage:")
            console.print("  fpl-copilot           Start chatting")
            console.print("  fpl-copilot init      Set up your credentials")
            console.print("  fpl-copilot version   Show version")
            console.print("  fpl-copilot help      Show this help")
        else:
            console.print(f"[red]Unknown command: {cmd}[/red]")
            console.print("Run [bold]fpl-copilot help[/bold] for usage.")
    else:
        asyncio.run(main())


if __name__ == "__main__":
    main_sync()
