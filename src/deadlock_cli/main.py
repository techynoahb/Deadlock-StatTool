"""Command-line entry point: `deadlock <command>`."""

from __future__ import annotations

import time
from datetime import datetime
from typing import NoReturn, Optional

import typer
from rich.console import Console
from rich.table import Table

from . import config, stats
from . import draft as draft_model
from .api import APIError, DeadlockAPI

app = typer.Typer(
    help="Check your Deadlock stats from the terminal.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

# Swapped out in tests so nothing hits the network
get_api = DeadlockAPI

AccountArg = typer.Argument(
    None,
    help="Steam account ID or SteamID64. Leave blank to use the one saved with `deadlock set-me`.",
    show_default=False,
)


def resolve_account(account: Optional[str]) -> int:
    if account:
        try:
            return stats.to_account_id(account)
        except ValueError:
            console.print(f"[red]'{account}' isn't a Steam ID.[/] Try `deadlock search <name>` to find yours.")
            raise typer.Exit(1)
    saved = config.default_account_id()
    if saved is None:
        console.print("[red]No account given.[/] Pass an ID, or save yours with `deadlock set-me <id>`.")
        raise typer.Exit(1)
    return saved


def fail(error: APIError) -> NoReturn:
    console.print(f"[red]Error:[/] {error}")
    raise typer.Exit(1)


def resolve_hero(name: str, names: dict[int, str]) -> int:
    """Hero name -> hero ID. Exits with a clear message on a bad name."""
    hero_id = stats.find_hero(name, names)
    if hero_id is None:
        console.print(f"[red]Couldn't find a hero called '{name}'.[/]")
        raise typer.Exit(1)
    return hero_id


def resolve_heroes(raw: str, names: dict[int, str]) -> list[int]:
    """Comma-separated hero names -> hero IDs."""
    return [resolve_hero(n, names) for n in (n.strip() for n in raw.split(",")) if n]


def result_text(won: bool) -> str:
    return "[green]Win[/]" if won else "[red]Loss[/]"


def pct_color(value: float) -> str:
    color = "green" if value >= 55 else "red" if value < 45 else "yellow"
    return f"[{color}]{value:.0f}%[/]"


# ---- commands ---------------------------------------------------------------


@app.command()
def search(name: str = typer.Argument(..., help="Steam name to look for.")):
    """Find a player's account ID by Steam name."""
    try:
        profiles = get_api().search_players(name)
    except APIError as e:
        fail(e)
    if not profiles:
        console.print("No players found. Only players with recent Deadlock matches show up.")
        return
    table = Table(title=f"Players matching '{name}'")
    table.add_column("Account ID", style="cyan")
    table.add_column("Name")
    table.add_column("Matches (30d)", justify="right")
    table.add_column("Profile", overflow="fold")
    for p in profiles:
        table.add_row(
            str(p["account_id"]),
            p.get("personaname", ""),
            str(p.get("matches_played_last_30d", "")),
            p.get("profileurl", ""),
        )
    console.print(table)
    console.print("Save yours with [bold]deadlock set-me <account id>[/].")


@app.command("set-me")
def set_me(account: str = typer.Argument(..., help="Your Steam account ID or SteamID64.")):
    """Save your account ID so the other commands work without typing it."""
    account_id = resolve_account(account)
    config.set_default_account_id(account_id)
    console.print(f"Saved [cyan]{account_id}[/] as your account.")


@app.command()
def recent(
    account: Optional[str] = AccountArg,
    count: int = typer.Option(10, "--count", "-n", help="How many matches to show."),
):
    """Show your most recent matches."""
    account_id = resolve_account(account)
    try:
        api = get_api()
        matches = api.match_history(account_id)[:count]
        heroes = api.hero_names()
    except APIError as e:
        fail(e)
    if not matches:
        console.print("No matches found for that account.")
        return

    table = Table(title=f"Last {len(matches)} matches")
    table.add_column("Date")
    table.add_column("Hero")
    table.add_column("Result")
    table.add_column("K / D / A", justify="center")
    table.add_column("KDA", justify="right")
    table.add_column("Souls", justify="right")
    table.add_column("Souls/min", justify="right")
    table.add_column("Length", justify="right")
    for m in matches:
        minutes, seconds = divmod(m["match_duration_s"], 60)
        table.add_row(
            datetime.fromtimestamp(m["start_time"]).strftime("%b %d %H:%M"),
            stats.hero_name(m["hero_id"], heroes),
            result_text(stats.is_win(m)),
            f"{m['player_kills']} / {m['player_deaths']} / {m['player_assists']}",
            f"{stats.kda(m['player_kills'], m['player_deaths'], m['player_assists']):.2f}",
            f"{m['net_worth']:,}",
            f"{stats.souls_per_min(m):,.0f}",
            f"{minutes}:{seconds:02d}",
        )
    console.print(table)


@app.command()
def heroes(
    account: Optional[str] = AccountArg,
    min_games: int = typer.Option(3, "--min-games", "-m", help="Hide heroes with fewer games."),
):
    """Show your stats on each hero you've played."""
    account_id = resolve_account(account)
    try:
        api = get_api()
        rows = stats.hero_rows(api.hero_stats(account_id), min_games=min_games)
        names = api.hero_names()
    except APIError as e:
        fail(e)
    if not rows:
        console.print(f"No heroes with at least {min_games} games. Try --min-games 1.")
        return

    table = Table(title="Hero stats (all tracked matches)")
    table.add_column("Hero")
    table.add_column("Games", justify="right")
    table.add_column("Win %", justify="right")
    table.add_column("KDA", justify="right")
    table.add_column("Souls/min", justify="right")
    table.add_column("Damage/min", justify="right")
    table.add_column("Accuracy", justify="right")
    table.add_column("Last played")
    for r in rows:
        table.add_row(
            stats.hero_name(r["hero_id"], names),
            str(r["games"]),
            pct_color(r["win_rate"]),
            f"{r['kda']:.2f}",
            f"{r['souls_per_min']:,.0f}",
            f"{r['damage_per_min']:,.0f}",
            f"{r['accuracy']:.0f}%",
            datetime.fromtimestamp(r["last_played"]).strftime("%b %d") if r["last_played"] else "-",
        )
    console.print(table)


@app.command()
def summary(
    account: Optional[str] = AccountArg,
    count: int = typer.Option(50, "--count", "-n", help="How many recent matches to include."),
):
    """Overview of your recent form: win rate, KDA, rank, top heroes, and trend."""
    account_id = resolve_account(account)
    try:
        api = get_api()
        history = api.match_history(account_id)
        names = api.hero_names()
        ranks = api.rank_names()
    except APIError as e:
        fail(e)
    matches = history[:count]
    if not matches:
        console.print("No matches found for that account.")
        return

    s = stats.summarize(matches)
    rank = stats.rank_label(stats.current_rank_badge(history), ranks)

    console.print(f"\n[bold]Last {s.matches} matches[/] (account {account_id})")
    if rank:
        console.print(f"  Rank:        [cyan]{rank}[/]")
    console.print(f"  Record:      {s.wins}W - {s.matches - s.wins}L  ({pct_color(s.win_rate)})")
    console.print(
        f"  Avg K/D/A:   {s.avg_kills:.1f} / {s.avg_deaths:.1f} / {s.avg_assists:.1f}"
        f"  (KDA {s.kda:.2f})"
    )
    console.print(f"  Souls/min:   {s.avg_souls_per_min:,.0f}")
    console.print(f"  Avg length:  {s.avg_duration_min:.0f} min")

    console.print("\n[bold]Most played[/]")
    for hero_id, games, wins in stats.most_played(matches):
        console.print(
            f"  {stats.hero_name(hero_id, names):<14} {games:>3} games  {pct_color(wins / games * 100)}"
        )

    # Trend: last 10 games against the rest of the window
    if len(matches) >= 20:
        last10, earlier = stats.summarize(matches[:10]), stats.summarize(matches[10:])
        console.print(f"\n[bold]Trend[/] (last 10 vs previous {earlier.matches})")
        for label, now, before, fmt in [
            ("Win rate", last10.win_rate, earlier.win_rate, "{:.0f}%"),
            ("KDA", last10.kda, earlier.kda, "{:.2f}"),
            ("Souls/min", last10.avg_souls_per_min, earlier.avg_souls_per_min, "{:,.0f}"),
        ]:
            arrow = "[green]▲[/]" if now > before else "[red]▼[/]" if now < before else "="
            console.print(f"  {label:<12} {fmt.format(now):>7}  {arrow}  (was {fmt.format(before)})")
    console.print()


@app.command()
def coach(
    hero: Optional[str] = typer.Argument(None, help="Hero name, e.g. Haze. Defaults to your most played.", show_default=False),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Account ID. Defaults to your saved one."),
    days: int = typer.Option(30, "--days", "-d", help="How many days of matches to compare."),
    tier: Optional[int] = typer.Option(None, "--tier", "-t", help="Compare against this rank tier (1-11) instead of your own."),
):
    """Compare your stats on a hero to the average player at your rank."""
    account_id = resolve_account(account)
    since = int(time.time()) - days * 86400
    try:
        api = get_api()
        names = api.hero_names()
        ranks = api.rank_names()
        my_rows = api.analytics_hero_stats(account_id=account_id, since_unix=since)
    except APIError as e:
        fail(e)

    my_by_hero = {r["hero_id"]: r for r in my_rows if r.get("matches")}
    if not my_by_hero:
        console.print(f"No matches in the last {days} days. Try a bigger window with --days 90.")
        raise typer.Exit(1)

    # Which hero
    if hero:
        hero_id = resolve_hero(hero, names)
        if hero_id not in my_by_hero:
            console.print(f"You haven't played {names[hero_id]} in the last {days} days.")
            raise typer.Exit(1)
    else:
        hero_id = max(my_by_hero, key=lambda h: my_by_hero[h]["matches"])
    hero_name = stats.hero_name(hero_id, names)

    # Which rank bracket
    if tier is not None:
        low, high = stats.badge_range(tier * 10)
    else:
        try:
            badge = stats.current_rank_badge(api.match_history(account_id))
        except APIError as e:
            fail(e)
        if not badge:
            console.print("No ranked badge found in your history. Pick a bracket with --tier (1-11).")
            raise typer.Exit(1)
        low, high = stats.badge_range(badge)
    rank_name = ranks.get(low // 10, f"Tier {low // 10}")

    try:
        bracket_rows = api.analytics_hero_stats(min_badge=low, max_badge=high, since_unix=since)
    except APIError as e:
        fail(e)
    bracket = next((r for r in bracket_rows if r["hero_id"] == hero_id), None)
    if not bracket or not bracket.get("matches"):
        console.print(f"Not enough {hero_name} games at {rank_name} to compare.")
        raise typer.Exit(1)

    mine = my_by_hero[hero_id]
    rows = stats.compare(stats.per_match(mine), stats.per_match(bracket))

    table = Table(title=f"{hero_name}: you vs. average {rank_name} player (per match, last {days} days)")
    table.add_column("Stat")
    table.add_column("You", justify="right")
    table.add_column(f"{rank_name} avg", justify="right")
    table.add_column("Difference", justify="right")
    for r in rows:
        color = "green" if r["good"] else "red"
        if r["fmt"].endswith("%"):  # already a percentage: show the gap in points
            diff = f"{r['you'] - r['avg']:+.0f} pts"
        else:
            diff = f"{r['diff_pct']:+.0f}%"
        table.add_row(
            r["label"],
            r["fmt"].format(r["you"]),
            r["fmt"].format(r["avg"]),
            f"[{color}]{diff}[/]",
        )
    console.print(table)
    console.print(f"Based on your {mine['matches']} games vs. {bracket['matches']:,} {rank_name} games.")
    if mine["matches"] < 5:
        console.print("[yellow]Small sample: play a few more games on this hero for reliable numbers.[/]")

    tips = stats.coach_tips(rows)
    if tips:
        console.print("\n[bold]What to work on[/]")
        for tip in tips:
            console.print(f"  • {tip}")
    else:
        console.print("\n[green]You're at or above average everywhere that matters. Nice.[/]")
    console.print()


@app.command()
def items(
    hero: str = typer.Argument(..., help="Hero name, e.g. Haze."),
    vs: Optional[str] = typer.Option(None, "--vs", help="Comma-separated enemy heroes to narrow the matchup."),
    min_matches: int = typer.Option(30, "--min-matches", help="Hide items with fewer matches."),
    top: int = typer.Option(15, "--top", help="How many items to show."),
    days: int = typer.Option(90, "--days", "-d", help="How many days of matches to include."),
):
    """Highest win-rate items for a hero, optionally against specific enemies."""
    since = int(time.time()) - days * 86400
    try:
        api = get_api()
        names = api.hero_names()
    except APIError as e:
        fail(e)
    hero_id = resolve_hero(hero, names)
    enemy_ids = resolve_heroes(vs, names) if vs else None

    try:
        item_stats = api.item_stats(hero_id, enemy_hero_ids=enemy_ids, min_matches=min_matches, since_unix=since)
        items_by_id = stats.purchasable_items(api.items())
    except APIError as e:
        fail(e)
    rows = stats.item_rows(item_stats, items_by_id, min_matches=min_matches)[:top]
    if not rows:
        console.print(f"No items with at least {min_matches} matches. Try --min-matches 10.")
        return

    title = f"Best items for {names[hero_id]}"
    if enemy_ids:
        title += " vs " + ", ".join(names[h] for h in enemy_ids)
    table = Table(title=title)
    table.add_column("Item")
    table.add_column("Slot")
    table.add_column("Tier", justify="right")
    table.add_column("Win %", justify="right")
    table.add_column("Matches", justify="right")
    for r in rows:
        table.add_row(r["name"], r["slot"], str(r["tier"]), pct_color(r["win_rate"]), f"{r['matches']:,}")
    console.print(table)
    console.print(f"Last {days} days, min {min_matches} matches per item.")


@app.command()
def draft(
    allies: str = typer.Option(..., "--allies", help="Comma-separated hero names on your team."),
    enemies: str = typer.Option(..., "--enemies", help="Comma-separated hero names on the enemy team."),
    min_matches: int = typer.Option(50, "--min-matches", help="Hide hero matchups with fewer matches."),
    days: int = typer.Option(90, "--days", "-d", help="How many days of matchup data to use."),
):
    """Predict win probability for a draft, based on real hero-vs-hero matchup data."""
    since = int(time.time()) - days * 86400
    try:
        api = get_api()
        names = api.hero_names()
    except APIError as e:
        fail(e)
    ally_ids = resolve_heroes(allies, names)
    enemy_ids = resolve_heroes(enemies, names)
    if not ally_ids or not enemy_ids:
        console.print("[red]Need at least one hero on each side.[/]")
        raise typer.Exit(1)

    try:
        counter_stats = api.hero_counter_stats(min_matches=min_matches, since_unix=since)
    except APIError as e:
        fail(e)
    ratings = draft_model.fit_hero_ratings(counter_stats)
    probability = draft_model.win_probability(ratings, ally_ids, enemy_ids)

    console.print(f"\n[bold]Predicted win chance:[/] {pct_color(probability)}")
    table = Table(title="Hero ratings (higher is stronger right now)")
    table.add_column("Hero")
    table.add_column("Side")
    table.add_column("Rating", justify="right")
    for r in draft_model.rating_breakdown(ratings, ally_ids, enemy_ids):
        side_text = "[cyan]Ally[/]" if r["side"] == "ally" else "[magenta]Enemy[/]"
        table.add_row(stats.hero_name(r["hero_id"], names), side_text, f"{r['rating']:+.2f}")
    console.print(table)
    console.print(
        f"\n[dim]Based on hero-vs-hero win rates over the last {days} days. "
        "Doesn't account for team synergy or how good you are with these heroes.[/]\n"
    )


if __name__ == "__main__":
    app()
