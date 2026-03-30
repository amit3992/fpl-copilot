# FPL Copilot

A conversational CLI copilot for Fantasy Premier League. Chat with Claude to analyze your team, scout players, check fixtures, and execute transfers — all from your terminal.

Think of it like Claude Code, but for FPL.

## Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/)
- Your FPL team ID (find it in the URL when viewing your team on the FPL website)
- (Optional) FPL login credentials for executing transfers
- (Optional) [Firecrawl API key](https://firecrawl.dev/) for enhanced player news

## Installation

```bash
git clone <repo-url>
cd fpl-copilot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

## Usage

```bash
python cli.py
```

## What you can ask

- **"Show me my team"** — view your full squad with form, price, and status
- **"How's my budget looking?"** — bank balance, free transfers, available chips
- **"Any injury news?"** — check which of your players are flagged
- **"Tell me about Palmer"** — detailed stats, recent form, upcoming fixtures
- **"Who should I replace Salah with?"** — top 5 ranked alternatives within budget
- **"Is it worth taking a hit to bring in Haaland for Watkins?"** — projected net gain analysis
- **"What are Arsenal's next 5 fixtures?"** — fixture difficulty ratings
- **"Transfer out Salah, bring in Palmer"** — stages the transfer for your approval
- **"Show my transfer history"** — past transfers from previous sessions

## Commands

| Command    | Description                        |
|------------|------------------------------------|
| `/quit`    | Exit the CLI                       |
| `/clear`   | Clear conversation history         |
| `/history` | Show conversation history          |
| `/debug`   | Toggle verbose tool call logging   |

## Environment Variables

| Variable           | Required | Description                                    |
|--------------------|----------|------------------------------------------------|
| `ANTHROPIC_API_KEY`| Yes      | Your Anthropic API key                         |
| `FPL_TEAM_ID`     | Yes      | Your FPL team ID                               |
| `FPL_EMAIL`       | No       | FPL login email (needed for transfers)         |
| `FPL_PASSWORD`    | No       | FPL login password (needed for transfers)      |
| `FIRECRAWL_API_KEY`| No      | Firecrawl API key for enhanced news scraping   |

## Architecture

```
cli.py              → Chat loop (Rich UI + Anthropic API)
core/fpl.py         → Async FPL API wrapper (aiohttp)
core/scoring.py     → Player scoring and ranking logic
tools/team.py       → Team, budget, and player stat tools
tools/news.py       → Injury news and player availability
tools/analysis.py   → Transfer recommendations and fixture analysis
tools/browser.py    → Playwright-based login and transfer execution
tools/registry.py   → Anthropic tool definitions and handler mapping
db/schema.sql       → SQLite schema for session state and transfer history
```

Claude handles all orchestration — no LangGraph or agent frameworks. The CLI sends your message plus the tool definitions to Claude, which decides what to call based on your question. Transfers require explicit `y` confirmation before executing.
