"""Bot tests: storage, caching, embeds, and target resolution. All offline."""

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("discord")

from deadlock_bot import embeds
from deadlock_bot.bot import DeadlockBot, NotLinked, TTLCache
from deadlock_bot.storage import LinkStore

from test_cli import HERO_STATS, MATCHES

HEROES = {1: "Infernus", 7: "Haze"}
RANKS = {8: "Ascendant"}


@pytest.fixture
def store(tmp_path):
    s = LinkStore(tmp_path / "links.db")
    yield s
    s.close()


class FakeAPI:
    def __init__(self):
        self.calls = 0

    def match_history(self, account_id):
        self.calls += 1
        return MATCHES

    def hero_names(self):
        return HEROES


def user(uid, name="noah"):
    return SimpleNamespace(id=uid, display_name=name)


# ---- storage ---------------------------------------------------------------

def test_link_get_unlink(store):
    assert store.get(1) is None
    store.link(1, 123)
    assert store.get(1) == 123
    store.link(1, 456)  # relinking replaces
    assert store.get(1) == 456
    assert store.unlink(1) is True
    assert store.unlink(1) is False
    assert store.get(1) is None


def test_links_persist(tmp_path):
    path = tmp_path / "links.db"
    LinkStore(path).link(5, 999)
    assert LinkStore(path).get(5) == 999


# ---- cache -----------------------------------------------------------------

def test_ttl_cache_expires():
    now = [0.0]
    cache = TTLCache(ttl=10, clock=lambda: now[0])
    cache.set("k", "v")
    now[0] = 9
    assert cache.get("k") == "v"
    now[0] = 11
    assert cache.get("k") is None


def test_repeat_commands_use_cache(store):
    api = FakeAPI()
    bot = DeadlockBot(store, api=api)
    asyncio.run(bot.match_history(123))
    asyncio.run(bot.match_history(123))
    assert api.calls == 1


# ---- whose stats -----------------------------------------------------------

def test_resolve_target(store):
    bot = DeadlockBot(store, api=FakeAPI())
    me, friend = user(1, "noah"), user(2, "ian")
    store.link(1, 123)

    assert bot.resolve_target(me, None, None) == (123, "noah")
    assert bot.resolve_target(me, None, "76561197960265851") == (123, "Account 123")
    with pytest.raises(NotLinked, match="ian"):
        bot.resolve_target(me, friend, None)
    with pytest.raises(ValueError):
        bot.resolve_target(me, None, "not-an-id")


def test_unlinked_caller_gets_hint(store):
    bot = DeadlockBot(store, api=FakeAPI())
    with pytest.raises(NotLinked, match="/link"):
        bot.resolve_target(user(1), None, None)


def test_commands_registered(store):
    bot = DeadlockBot(store, api=FakeAPI())
    names = {c.name for c in bot.tree.get_commands()}
    assert names == {"link", "unlink", "stats", "recent", "heroes", "hero", "search"}


# ---- embeds ----------------------------------------------------------------

def fields(embed):
    return {f.name: f.value for f in embed.fields}


def test_summary_embed():
    e = embeds.summary_embed("noah", MATCHES, HEROES, RANKS)
    f = fields(e)
    assert e.title == "noah's Deadlock stats"
    assert f["Rank"] == "Ascendant 4"
    assert f["Matches"] == "25"
    assert "Infernus" in f["Most played"]
    assert f["Last 20 games"].startswith("15W 5L")


def test_recent_embed_lists_each_match():
    e = embeds.recent_embed("noah", MATCHES[:5], HEROES)
    assert e.description == "5W 0L"
    lines = fields(e)["Matches"].splitlines()
    assert len(lines) == 5
    assert lines[0].startswith("🟢 **Haze** 5/3/8")


def test_recent_embed_fits_discord_limit():
    e = embeds.recent_embed("noah", MATCHES[:10], HEROES)
    assert len(fields(e)["Matches"]) <= 1024


def test_heroes_embed_filters_min_games():
    e = embeds.heroes_embed("noah", HERO_STATS, HEROES, min_games=5)
    assert "Infernus" in e.description and "Haze" not in e.description


def test_hero_embed():
    e = embeds.hero_embed("noah", 1, HERO_STATS, HEROES)
    assert e.title == "noah on Infernus"
    assert fields(e)["Win rate"] == "60.0%"
    assert "No games" in embeds.hero_embed("noah", 99, HERO_STATS, HEROES).description


def test_search_embed_empty():
    assert "No players" in embeds.search_embed("x", []).description


# ---- full command path -----------------------------------------------------

class FakeInteraction:
    def __init__(self, caller):
        self.user = caller
        self.sent = []
        self.response = SimpleNamespace(defer=self._defer)
        self.followup = SimpleNamespace(send=self._send)

    async def _defer(self, **kwargs):
        pass

    async def _send(self, **kwargs):
        self.sent.append(kwargs["embed"])


def run_command(bot, name, interaction, **kwargs):
    cmd = bot.tree.get_command(name)
    asyncio.run(cmd.callback(interaction, **kwargs))
    return interaction.sent[-1]


def test_stats_command_end_to_end(store):
    api = FakeAPI()
    api.rank_names = lambda: RANKS
    bot = DeadlockBot(store, api=api)
    store.link(1, 123)
    embed = run_command(bot, "stats", FakeInteraction(user(1)), user=None, account=None)
    assert embed.title == "noah's Deadlock stats"


def test_command_errors_become_embeds(store):
    bot = DeadlockBot(store, api=FakeAPI())
    embed = run_command(bot, "recent", FakeInteraction(user(1)), user=None, count=5, account=None)
    assert "/link" in embed.description
