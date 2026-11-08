# Deadlock Stat Tool

[![CI](https://github.com/techynoahb/Deadlock-StatTool/actions/workflows/ci.yml/badge.svg)](https://github.com/techynoahb/Deadlock-StatTool/actions/workflows/ci.yml)

Check your [Deadlock](https://store.steampowered.com/app/1422450/Deadlock/) stats from the terminal or Discord.
Data comes from the free community [Deadlock API](https://api.deadlock-api.com/docs).

## Install

```bash
git clone https://github.com/techynoahb/Deadlock-StatTool.git
cd Deadlock-StatTool
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## CLI

```bash
deadlock search "your steam name"   # find your account ID
deadlock set-me 123456789           # save it as your default

deadlock summary                    # win rate, KDA, rank, top heroes, recent trend
deadlock recent -n 20               # last 20 matches
deadlock heroes --min-games 5       # per-hero stats
deadlock coach haze                 # you vs. the average player at your rank on Haze
deadlock items haze --vs infernus   # best items for Haze, optionally vs. specific enemies
deadlock draft --allies haze,infernus,wraith --enemies seven,abrams,vindicta   # predicted win %
```

Pass an account ID or SteamID64 to any stats command to look up someone else, e.g. `deadlock summary 123456789`.

`draft` rates each hero from real hero-vs-hero win rates (logistic regression) and compares the two
teams' totals. It doesn't account for team synergy or how well you play a hero.

## Discord bot

| Command | What it does |
|---|---|
| `/link <account>` | Link your account (account ID, SteamID64, or Steam name) |
| `/stats [user]` | Rank, win rate, KDA, top heroes, recent form |
| `/recent [user] [count]` | Last 1-10 matches |
| `/heroes [user]` | Per-hero stats |
| `/hero <name> [user]` | Stats on one hero |
| `/search <name>` | Find an account ID by Steam name |
| `/unlink` | Forget your linked account |

Stats commands also take `account:` to look up any account ID.

To run your own:

1. Create an application in the [Discord Developer Portal](https://discord.com/developers/applications), add a bot, and copy its token.
2. Invite it with the `bot` and `applications.commands` scopes and the `Send Messages` and `Embed Links` permissions.
3. Configure and start it:

```bash
pip install -e ".[bot]"
cp .env.example .env      # add your token; DEV_GUILD_ID makes commands show up instantly
deadlock-bot
```

Linked accounts are stored in SQLite. Player data is cached for two minutes to go easy on the API.

## Project layout

| File | Job |
|---|---|
| `src/deadlock_cli/api.py` | API client; caches rarely-changing data for a day |
| `src/deadlock_cli/stats.py` | All the math, no network calls |
| `src/deadlock_cli/draft.py` | Draft win predictor |
| `src/deadlock_cli/main.py` | CLI commands and table output (Typer + Rich) |
| `src/deadlock_cli/config.py` | Saved default account |
| `src/deadlock_bot/bot.py` | Discord slash commands, built on the same `api.py` and `stats.py` |
| `src/deadlock_bot/embeds.py` | Formats stats as Discord embeds |
| `src/deadlock_bot/storage.py` | Discord user → Deadlock account links |

## Development

```bash
ruff check .
pytest
```

Tests run offline against fake data shaped like real API responses. CI runs both on every push.
