# FPL Copilot

A conversational CLI copilot for Fantasy Premier League. Chat with Claude to analyze your team, scout players, check fixtures, and execute transfers — all from your terminal.

Think of it like Claude Code, but for FPL.

## Installation

```bash
pip install fpl-copilot
playwright install chromium
```

## Setup

```bash
fpl-copilot init
```

This will prompt you for:
- **Anthropic API key** ([get one here](https://console.anthropic.com/))
- **FPL team ID** (find it in the URL when viewing your team: `fantasy.premierleague.com/entry/XXXXXXX/...`)
- **FPL email & password** (optional — only needed to execute transfers)
- **Firecrawl API key** (optional — for enhanced player news from BBC/Sky Sports)

Config is saved to `~/.config/fpl-copilot/config.json`.

## Usage

```bash
fpl-copilot
```

```
> who is my captain?
  ⠋ Checking get_my_team...

Your captain is Erling Haaland (Manchester City, £14.4m).

> any injury concerns?
  ⠋ Checking get_injury_news...

2 flagged players in your squad:
  Salah — Doubtful (hamstring, 50% chance)
  Watkins — Injured (knee, expected back GW32)

> who should I replace Watkins with?
  ⠋ Checking get_transfer_options...

Top 5 replacements for Watkins (FWD, £7.8m budget):
  1. Isak (NEW) — £7.5m, form 8.2, score 6.41
  ...
```

## What you can ask

- **"Show me my team"** — full squad with form, price, and status
- **"How's my budget looking?"** — bank balance, free transfers, available chips
- **"Any injury news?"** — flagged players in your squad
- **"Tell me about Palmer"** — detailed stats, recent form, upcoming fixtures
- **"Who should I replace Salah with?"** — top 5 ranked alternatives within budget
- **"Is it worth taking a hit for Haaland?"** — projected net gain analysis
- **"What are Arsenal's next 5 fixtures?"** — fixture difficulty ratings
- **"Transfer out Salah, bring in Palmer"** — stages the transfer for your approval

## CLI Reference

```
fpl-copilot           Open the copilot
fpl-copilot init      Set up your credentials
fpl-copilot version   Show version
fpl-copilot help      Show help
```

In-session commands:

| Command    | Description                        |
|------------|------------------------------------|
| `/quit`    | Exit                               |
| `/clear`   | Clear conversation history         |
| `/history` | Show conversation history          |
| `/debug`   | Toggle verbose tool call logging   |

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
```

Claude handles all orchestration — no LangGraph or agent frameworks. The CLI sends your message plus the tool definitions to Claude, which decides what to call based on your question. Transfers require explicit `y` confirmation before executing.
