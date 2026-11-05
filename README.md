# deadlock-cli

Check your [Deadlock](https://store.steampowered.com/app/1422450/Deadlock/) stats from the terminal.

Data comes from the free community [Deadlock API](https://api.deadlock-api.com/docs).

## Install

```bash
git clone <this repo>
cd deadlock-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
deadlock search "your steam name"   # find your account ID
deadlock set-me 123456789           # save it so you don't have to type it again

deadlock summary                    # win rate, KDA, rank, top heroes, recent trend
deadlock recent -n 20               # last 20 matches
deadlock heroes --min-games 5       # per-hero stats
deadlock coach haze                 # you vs. the average player at your rank on Haze
deadlock items haze --vs infernus   # highest win-rate items for Haze, vs. a specific enemy
deadlock draft --allies haze,infernus,wraith --enemies seven,abrams,vindicta   # predicted win %
```

`coach` options: `--days 90` for a longer window, `--tier 8` to compare against a different rank.

`draft` fits a logistic regression ("power rating" per hero) on real hero-vs-hero win rates and
predicts `sigmoid(ally ratings - enemy ratings)`. It doesn't know about team synergy or your
personal skill with a hero — see Roadmap below for why.

Every command also takes an account ID (or SteamID64) to look up someone else:

```bash
deadlock summary 123456789
```

## Discord bot

The same stats are available as a Discord bot, so a server can check each other's games.

| Command | What it does |
|---|---|
| `/link <account>` | Link your Deadlock account (account ID, SteamID64, or Steam name) |
| `/stats [user]` | Rank, win rate, KDA, top heroes, and recent form |
| `/recent [user] [count]` | Last 1-10 matches |
| `/heroes [user]` | Per-hero stats, most played first |
| `/hero <name> [user]` | Stats on one hero (with name autocomplete) |
| `/search <name>` | Find an account ID by Steam name |
| `/unlink` | Forget your linked account |

Every stats command also takes `account:` to look up any account ID.

### Running it

1. Create an application at the [Discord Developer Portal](https://discord.com/developers/applications),
   add a bot, and copy its token.
2. Invite it to your server: OAuth2 → URL Generator → scopes `bot` and `applications.commands`,
   permissions `Send Messages` and `Embed Links`.
3. Configure and run:

```bash
pip install -e ".[bot]"
cp .env.example .env      # paste your token; DEV_GUILD_ID makes commands appear instantly
deadlock-bot
```

Linked accounts are stored in a local SQLite file (`deadlock_bot.db`). Player data is cached
in memory for two minutes so repeated commands don't hammer the community API.

## How it's organized

| File | Job |
|---|---|
| `src/deadlock_cli/api.py` | Talks to the API; caches hero and rank names for a day |
| `src/deadlock_cli/stats.py` | All the math (win rate, KDA, souls/min, trends). No network calls |
| `src/deadlock_cli/main.py` | The commands and table output (Typer + Rich) |
| `src/deadlock_cli/config.py` | Saves your default account in `~/.config/deadlock-cli/` |
| `src/deadlock_cli/draft.py` | The draft win predictor: a logistic-regression hero rating model |
| `src/deadlock_bot/bot.py` | Discord slash commands; calls the same `api.py` and `stats.py` |
| `src/deadlock_bot/embeds.py` | Turns stats into Discord embeds (no network, unit tested) |
| `src/deadlock_bot/storage.py` | SQLite table of Discord user → Deadlock account |

## Tests

```bash
pytest
```

Tests use fake data shaped like real API responses, so they run offline.

## Roadmap

- [x] Stats commands: `summary`, `recent`, `heroes`, `search`
- [x] `coach`: compare your stats on a hero to the average at your rank, with tips
- [x] `items`: highest win-rate items for a hero (optionally vs. a specific enemy)
- [x] `draft`: predict win probability from a draft. The community API has no endpoint
      with raw per-match draft data (all 12 heroes + outcome), so this fits a
      Bradley-Terry style logistic regression on aggregated hero-vs-hero win rates
      instead — a per-hero "power rating" rather than a model trained on real drafts.
      It can't see team synergy or personal skill with a hero.
