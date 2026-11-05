"""Builds Discord embeds from stats. Pure functions, no network, so they're easy to test."""

from __future__ import annotations

import discord

from deadlock_cli import stats

WIN_COLOR = discord.Color.green()
LOSS_COLOR = discord.Color.red()
NEUTRAL_COLOR = discord.Color.blurple()
ERROR_COLOR = discord.Color.dark_red()


def error_embed(message: str) -> discord.Embed:
    return discord.Embed(description=message, color=ERROR_COLOR)


def _hero(hero_id: int, heroes: dict[int, str]) -> str:
    return heroes.get(hero_id, f"Hero {hero_id}")


def summary_embed(
    name: str,
    matches: list[dict],
    heroes: dict[int, str],
    ranks: dict[int, str],
    recent_count: int = 20,
) -> discord.Embed:
    """Overall stats, rank, top heroes, and how the last `recent_count` games went."""
    overall = stats.summarize(matches)
    recent = stats.summarize(matches[:recent_count])
    color = WIN_COLOR if recent.win_rate >= 50 else LOSS_COLOR

    embed = discord.Embed(title=f"{name}'s Deadlock stats", color=color)
    rank = stats.rank_label(stats.current_rank_badge(matches), ranks)
    if rank:
        embed.add_field(name="Rank", value=rank, inline=True)
    embed.add_field(name="Matches", value=f"{overall.matches:,}", inline=True)
    embed.add_field(name="Win rate", value=f"{overall.win_rate:.1f}%", inline=True)
    embed.add_field(
        name="Avg K / D / A",
        value=f"{overall.avg_kills:.1f} / {overall.avg_deaths:.1f} / {overall.avg_assists:.1f}",
        inline=True,
    )
    embed.add_field(name="KDA", value=f"{overall.kda:.2f}", inline=True)
    embed.add_field(name="Souls/min", value=f"{overall.avg_souls_per_min:,.0f}", inline=True)

    top = stats.most_played(matches, top=3)
    if top:
        lines = [
            f"**{_hero(h, heroes)}**: {g} games, {w / g * 100:.0f}% WR" for h, g, w in top
        ]
        embed.add_field(name="Most played", value="\n".join(lines), inline=False)

    if overall.matches > recent.matches:
        embed.add_field(
            name=f"Last {recent.matches} games",
            value=f"{recent.wins}W {recent.matches - recent.wins}L "
            f"({recent.win_rate:.0f}%), KDA {recent.kda:.2f}",
            inline=False,
        )
    return embed


def recent_embed(name: str, matches: list[dict], heroes: dict[int, str]) -> discord.Embed:
    """One line per match: result, hero, K/D/A, souls/min, length."""
    wins = sum(stats.is_win(m) for m in matches)
    embed = discord.Embed(
        title=f"{name}'s last {len(matches)} matches",
        description=f"{wins}W {len(matches) - wins}L",
        color=WIN_COLOR if wins * 2 >= len(matches) else LOSS_COLOR,
    )
    lines = []
    for m in matches:
        icon = "🟢" if stats.is_win(m) else "🔴"
        k, d, a = m["player_kills"], m["player_deaths"], m["player_assists"]
        minutes = m["match_duration_s"] // 60
        lines.append(
            f"{icon} **{_hero(m['hero_id'], heroes)}** {k}/{d}/{a} · "
            f"{stats.souls_per_min(m):,.0f} souls/min · {minutes}m · `{m['match_id']}`"
        )
    embed.add_field(name="Matches", value="\n".join(lines) or "None", inline=False)
    return embed


def heroes_embed(
    name: str, hero_stats: list[dict], heroes: dict[int, str], limit: int = 10, min_games: int = 1
) -> discord.Embed:
    rows = stats.hero_rows(hero_stats, min_games=min_games)[:limit]
    embed = discord.Embed(title=f"{name}'s top heroes", color=NEUTRAL_COLOR)
    if not rows:
        embed.description = "No hero stats found."
        return embed
    lines = [
        f"**{_hero(r['hero_id'], heroes)}**: {r['games']} games · {r['win_rate']:.0f}% WR · "
        f"{r['kda']:.2f} KDA · {r['souls_per_min']:,.0f} souls/min"
        for r in rows
    ]
    embed.description = "\n".join(lines)
    return embed


def hero_embed(name: str, hero_id: int, hero_stats: list[dict], heroes: dict[int, str]) -> discord.Embed:
    """Detailed stats for one hero."""
    hero_name = _hero(hero_id, heroes)
    row = next((r for r in stats.hero_rows(hero_stats) if r["hero_id"] == hero_id), None)
    embed = discord.Embed(title=f"{name} on {hero_name}", color=NEUTRAL_COLOR)
    if row is None:
        embed.description = f"No games on {hero_name} yet."
        return embed
    embed.add_field(name="Games", value=str(row["games"]), inline=True)
    embed.add_field(name="Win rate", value=f"{row['win_rate']:.1f}%", inline=True)
    embed.add_field(name="KDA", value=f"{row['kda']:.2f}", inline=True)
    embed.add_field(name="Souls/min", value=f"{row['souls_per_min']:,.0f}", inline=True)
    embed.add_field(name="Damage/min", value=f"{row['damage_per_min']:,.0f}", inline=True)
    embed.add_field(name="Accuracy", value=f"{row['accuracy']:.0f}%", inline=True)
    return embed


def search_embed(query: str, profiles: list[dict]) -> discord.Embed:
    embed = discord.Embed(title=f"Players matching '{query}'", color=NEUTRAL_COLOR)
    if not profiles:
        embed.description = "No players found. Only players with recent Deadlock matches show up."
        return embed
    lines = [
        f"**{p.get('personaname', '?')}**: `{p['account_id']}` "
        f"({p.get('matches_played_last_30d', 0)} matches in 30d)"
        for p in profiles[:10]
    ]
    embed.description = "\n".join(lines)
    embed.set_footer(text="Link yours with /link <account id>")
    return embed
