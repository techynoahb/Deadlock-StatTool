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
```

`coach` options: `--days 90` for a longer window, `--tier 8` to compare against a different rank.

Every command also takes an account ID (or SteamID64) to look up someone else:

```bash
deadlock summary 123456789
```

## How it's organized

| File | Job |
|---|---|
| `src/deadlock_cli/api.py` | Talks to the API; caches hero and rank names for a day |
| `src/deadlock_cli/stats.py` | All the math (win rate, KDA, souls/min, trends). No network calls |
| `src/deadlock_cli/main.py` | The commands and table output (Typer + Rich) |
| `src/deadlock_cli/config.py` | Saves your default account in `~/.config/deadlock-cli/` |

## Tests

```bash
pytest
```

Tests use fake data shaped like real API responses, so they run offline.

## Roadmap

- [x] Stats commands: `summary`, `recent`, `heroes`, `search`
- [x] `coach`: compare your stats on a hero to the average at your rank, with tips
- [ ] ML: predict win probability from a draft, recommend items
