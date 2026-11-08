"""Deadlock stats Discord bot (commands are listed in the README).

Run with:  DISCORD_TOKEN=... deadlock-bot
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

import discord
from discord import app_commands

from deadlock_cli import stats
from deadlock_cli.api import APIError, DeadlockAPI

from . import embeds
from .storage import DEFAULT_DB, LinkStore

log = logging.getLogger("deadlock_bot")

PLAYER_CACHE_SECONDS = 120  # don't hit the API again if someone re-runs a command right away


class TTLCache:
    """Tiny in-memory cache so repeated commands don't hammer the community API."""

    def __init__(self, ttl: float, clock: Callable[[], float] = time.monotonic):
        self.ttl = ttl
        self.clock = clock
        self._data: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any | None:
        hit = self._data.get(key)
        if hit and self.clock() - hit[0] < self.ttl:
            return hit[1]
        self._data.pop(key, None)
        return None

    def set(self, key: Any, value: Any) -> None:
        self._data[key] = (self.clock(), value)


class NotLinked(Exception):
    pass


class DeadlockBot(discord.Client):
    def __init__(self, store: LinkStore, api: DeadlockAPI | None = None, dev_guild_id: int | None = None):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.store = store
        self.api = api or DeadlockAPI()
        self.cache = TTLCache(PLAYER_CACHE_SECONDS)
        self.dev_guild_id = dev_guild_id
        register_commands(self)

    async def setup_hook(self) -> None:
        if self.dev_guild_id:
            # Guild sync shows up instantly; global sync can take up to an hour
            guild = discord.Object(id=self.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        log.info("Logged in as %s", self.user)

    # ---- data helpers (the API client is sync, so run it off the event loop) ----

    async def fetch(self, key: tuple, fn: Callable[[], Any]) -> Any:
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        value = await asyncio.to_thread(fn)
        self.cache.set(key, value)
        return value

    async def match_history(self, account_id: int) -> list[dict]:
        return await self.fetch(("matches", account_id), lambda: self.api.match_history(account_id))

    async def hero_stats(self, account_id: int) -> list[dict]:
        return await self.fetch(("heroes", account_id), lambda: self.api.hero_stats(account_id))

    async def hero_names(self) -> dict[int, str]:
        return await asyncio.to_thread(self.api.hero_names)  # already cached on disk for a day

    async def rank_names(self) -> dict[int, str]:
        return await asyncio.to_thread(self.api.rank_names)

    def resolve_target(
        self, caller: discord.abc.User, user: Optional[discord.abc.User], account: Optional[str]
    ) -> tuple[int, str]:
        """Work out whose stats to show: an explicit account ID, a mentioned user, or the caller."""
        if account:
            account_id = stats.to_account_id(account)  # ValueError on junk
            return account_id, f"Account {account_id}"
        target = user or caller
        account_id = self.store.get(target.id)
        if account_id is None:
            if target.id == caller.id:
                raise NotLinked("You haven't linked an account yet. Use `/link` first.")
            raise NotLinked(f"{target.display_name} hasn't linked a Deadlock account.")
        return account_id, target.display_name


def register_commands(bot: DeadlockBot) -> None:
    tree = bot.tree

    async def run(interaction: discord.Interaction, work: Callable[[], Any]) -> None:
        """Defer (API calls can take a few seconds), run the command, and turn errors into embeds."""
        await interaction.response.defer(thinking=True)
        try:
            embed = await work()
        except NotLinked as e:
            embed = embeds.error_embed(str(e))
        except ValueError:
            embed = embeds.error_embed("That isn't a valid Steam account ID. Try `/search <name>`.")
        except APIError as e:
            embed = embeds.error_embed(f"Deadlock API error: {e}")
        except Exception:
            log.exception("Command failed")
            embed = embeds.error_embed("Something went wrong. Try again in a bit.")
        await interaction.followup.send(embed=embed)

    @tree.command(description="Link your Deadlock account (account ID, SteamID64, or Steam name)")
    @app_commands.describe(account="Your account ID, SteamID64, or Steam name")
    async def link(interaction: discord.Interaction, account: str):
        async def work():
            if account.strip().isdigit():
                account_id = stats.to_account_id(account)
            else:
                profiles = await asyncio.to_thread(bot.api.search_players, account)
                if len(profiles) != 1:
                    embed = embeds.search_embed(account, profiles)
                    if profiles:
                        embed.description = "More than one match, so pick yours:\n\n" + embed.description
                    return embed
                account_id = profiles[0]["account_id"]
            bot.store.link(interaction.user.id, account_id)
            return discord.Embed(
                description=f"Linked {interaction.user.mention} to account `{account_id}`. Try `/stats`.",
                color=embeds.WIN_COLOR,
            )

        await run(interaction, work)

    @tree.command(description="Unlink your Deadlock account")
    async def unlink(interaction: discord.Interaction):
        removed = bot.store.unlink(interaction.user.id)
        msg = "Unlinked your account." if removed else "You didn't have an account linked."
        await interaction.response.send_message(msg, ephemeral=True)

    @tree.command(name="stats", description="Overall stats, rank, top heroes, and recent form")
    @app_commands.describe(user="Whose stats (defaults to you)", account="Look up any account ID instead")
    async def stats_cmd(
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        account: Optional[str] = None,
    ):
        async def work():
            account_id, name = bot.resolve_target(interaction.user, user, account)
            matches = await bot.match_history(account_id)
            if not matches:
                return embeds.error_embed("No matches found for that account.")
            return embeds.summary_embed(name, matches, await bot.hero_names(), await bot.rank_names())

        await run(interaction, work)

    @tree.command(description="Your most recent matches")
    @app_commands.describe(user="Whose matches (defaults to you)", count="How many (1-10)", account="Any account ID")
    async def recent(
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        count: app_commands.Range[int, 1, 10] = 5,
        account: Optional[str] = None,
    ):
        async def work():
            account_id, name = bot.resolve_target(interaction.user, user, account)
            matches = (await bot.match_history(account_id))[:count]
            if not matches:
                return embeds.error_embed("No matches found for that account.")
            return embeds.recent_embed(name, matches, await bot.hero_names())

        await run(interaction, work)

    @tree.command(description="Per-hero stats, most played first")
    @app_commands.describe(user="Whose stats (defaults to you)", min_games="Hide heroes with fewer games")
    async def heroes(
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        min_games: app_commands.Range[int, 1, 500] = 1,
        account: Optional[str] = None,
    ):
        async def work():
            account_id, name = bot.resolve_target(interaction.user, user, account)
            rows = await bot.hero_stats(account_id)
            return embeds.heroes_embed(name, rows, await bot.hero_names(), min_games=min_games)

        await run(interaction, work)

    @tree.command(description="Your stats on one hero")
    @app_commands.describe(name="Hero name", user="Whose stats (defaults to you)")
    async def hero(
        interaction: discord.Interaction,
        name: str,
        user: Optional[discord.User] = None,
        account: Optional[str] = None,
    ):
        async def work():
            names = await bot.hero_names()
            hero_id = stats.find_hero(name, names)
            if hero_id is None:
                return embeds.error_embed(f"Couldn't find a hero called '{name}'.")
            account_id, player = bot.resolve_target(interaction.user, user, account)
            rows = await bot.hero_stats(account_id)
            return embeds.hero_embed(player, hero_id, rows, names)

        await run(interaction, work)

    @hero.autocomplete("name")
    async def hero_autocomplete(interaction: discord.Interaction, current: str):
        try:
            names = await bot.hero_names()
        except APIError:
            return []
        current = current.lower()
        matches = sorted(n for n in names.values() if current in n.lower())
        return [app_commands.Choice(name=n, value=n) for n in matches[:25]]

    @tree.command(description="Find a player's account ID by Steam name")
    async def search(interaction: discord.Interaction, name: str):
        async def work():
            profiles = await asyncio.to_thread(bot.api.search_players, name)
            return embeds.search_embed(name, profiles)

        await run(interaction, work)


def load_dotenv(path: Path = Path(".env")) -> None:
    """Read KEY=value lines from .env without needing another dependency."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Set DISCORD_TOKEN (in your environment or a .env file).")
    guild = os.environ.get("DEV_GUILD_ID")
    store = LinkStore(os.environ.get("DEADLOCK_BOT_DB", DEFAULT_DB))
    bot = DeadlockBot(store, dev_guild_id=int(guild) if guild else None)
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
