"""Tests run on fake API data shaped like the real responses, so they never need the network."""

import pytest
from typer.testing import CliRunner

from deadlock_cli import config, draft, main, stats


def make_match(match_id, hero_id, won, kills=5, deaths=3, assists=8, net_worth=30000, minutes=30, badge=None):
    return {
        "account_id": 123,
        "match_id": match_id,
        "hero_id": hero_id,
        "hero_level": 30,
        "start_time": 1_760_000_000 - match_id * 3600,
        "game_mode": 1,
        "match_mode": 4,
        "player_team": 0,
        "player_kills": kills,
        "player_deaths": deaths,
        "player_assists": assists,
        "denies": 10,
        "net_worth": net_worth,
        "last_hits": 200,
        "match_duration_s": minutes * 60,
        "match_result": 0 if won else 1,
        "player_match_outcome": 1 if won else 2,
        "ranked_display_badge": badge,
    }


# newest first, like the API: 25 matches, recent 10 all wins
MATCHES = [make_match(i, 1 if i % 3 else 7, won=(i < 10 or i % 2 == 0), badge=84 if i == 2 else None) for i in range(25)]

HERO_STATS = [
    {"hero_id": 1, "matches_played": 40, "wins": 24, "kills": 200, "deaths": 120, "assists": 300,
     "networth_per_min": 1050.4, "damage_per_min": 900.0, "accuracy": 0.47, "last_played": 1_760_000_000},
    {"hero_id": 7, "matches_played": 2, "wins": 0, "kills": 3, "deaths": 9, "assists": 4,
     "networth_per_min": 800.0, "damage_per_min": 600.0, "accuracy": 0.3, "last_played": 1_759_000_000},
]


def analytics_row(hero_id, matches, wins, kills, deaths, assists, souls, last_hits, damage, hit, miss):
    return {"hero_id": hero_id, "matches": matches, "wins": wins, "losses": matches - wins,
            "total_kills": kills, "total_deaths": deaths, "total_assists": assists,
            "total_net_worth": souls, "total_last_hits": last_hits, "total_denies": matches * 10,
            "total_player_damage": damage, "total_player_damage_taken": damage,
            "total_boss_damage": matches * 5000, "total_shots_hit": hit, "total_shots_missed": miss}


# Me on Infernus (10 games): fewer souls and more deaths than the bracket average
MY_ANALYTICS = [analytics_row(1, 10, 6, 60, 70, 90, 250_000, 1500, 200_000, 400, 600)]
BRACKET_ANALYTICS = [
    analytics_row(1, 1000, 500, 5000, 5000, 9000, 30_000_000, 180_000, 20_000_000, 45_000, 55_000),
    analytics_row(7, 800, 420, 4000, 3500, 6000, 24_000_000, 140_000, 16_000_000, 30_000, 50_000),
]


# Item assets: two purchasable items plus one ability that should be filtered out
ITEMS = [
    {"id": 100, "name": "Extra Health", "type": "upgrade", "item_slot_type": "vitality", "item_tier": 1},
    {"id": 200, "name": "Bad Item", "type": "upgrade", "item_slot_type": "weapon", "item_tier": 1},
    {"id": 300, "name": "Some Ability", "type": "ability", "item_slot_type": "", "item_tier": 0},
]
ITEM_STATS = [
    {"item_id": 100, "wins": 60, "matches": 100, "players": 80},
    {"item_id": 200, "wins": 30, "matches": 100, "players": 90},
]

# Infernus (1) beats Wraith (3) 80% of the time
COUNTER_STATS = [
    {"hero_id": 1, "enemy_hero_id": 3, "wins": 80, "matches_played": 100},
    {"hero_id": 3, "enemy_hero_id": 1, "wins": 20, "matches_played": 100},
]


class FakeAPI:
    def analytics_hero_stats(self, account_id=None, min_badge=None, max_badge=None, since_unix=None):
        if account_id is not None:
            return MY_ANALYTICS
        assert (min_badge, max_badge) == (80, 89)  # bracket from badge 84
        return BRACKET_ANALYTICS

    def match_history(self, account_id):
        return MATCHES

    def hero_stats(self, account_id):
        return HERO_STATS

    def search_players(self, name, limit=10):
        return [{"account_id": 123, "personaname": "Noah", "profileurl": "https://steamcommunity.com/id/x/",
                 "matches_played_last_30d": 40}]

    def hero_names(self):
        return {1: "Infernus", 7: "Haze", 3: "Wraith"}

    def rank_names(self):
        return {8: "Ascendant"}

    def items(self):
        return ITEMS

    def item_stats(self, hero_id, enemy_hero_ids=None, min_matches=30, since_unix=None):
        return ITEM_STATS

    def hero_counter_stats(self, min_matches=50, since_unix=None):
        return COUNTER_STATS


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "get_api", FakeAPI)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    main.console.width = 140
    return CliRunner()


# ---- stats ----------------------------------------------------------------------

def test_steam_id64_converts_to_account_id():
    assert stats.to_account_id("76561198000000000") == 39734272
    assert stats.to_account_id(39734272) == 39734272


def test_is_win_uses_outcome_then_falls_back_to_team():
    assert stats.is_win({"player_match_outcome": 1})
    assert not stats.is_win({"player_match_outcome": 2})
    assert stats.is_win({"player_match_outcome": 0, "match_result": 1, "player_team": 1})


def test_kda_handles_zero_deaths():
    assert stats.kda(4, 0, 6) == 10


def test_summarize_and_rank():
    s = stats.summarize(MATCHES[:10])
    assert s.wins == 10 and s.win_rate == 100
    assert s.avg_souls_per_min == 1000
    assert stats.rank_label(stats.current_rank_badge(MATCHES), {8: "Ascendant"}) == "Ascendant 4"


def test_hero_rows_filters_and_sorts():
    rows = stats.hero_rows(HERO_STATS, min_games=3)
    assert [r["hero_id"] for r in rows] == [1]
    assert rows[0]["win_rate"] == 60


# ---- commands -------------------------------------------------------------------

def test_recent(runner):
    result = runner.invoke(main.app, ["recent", "123", "-n", "5"])
    assert result.exit_code == 0, result.output
    assert "Last 5 matches" in result.output and "Infernus" in result.output


def test_heroes(runner):
    result = runner.invoke(main.app, ["heroes", "123", "--min-games", "1"])
    assert result.exit_code == 0, result.output
    assert "Infernus" in result.output and "Haze" in result.output


def test_summary_with_saved_account(runner):
    assert runner.invoke(main.app, ["set-me", "123"]).exit_code == 0
    result = runner.invoke(main.app, ["summary"])
    assert result.exit_code == 0, result.output
    assert "Ascendant 4" in result.output and "Trend" in result.output


def test_search(runner):
    result = runner.invoke(main.app, ["search", "noah"])
    assert result.exit_code == 0 and "123" in result.output


def test_find_hero_and_badge_range():
    names = {1: "Infernus", 7: "Haze", 8: "Holliday"}
    assert stats.find_hero("haze", names) == 7
    assert stats.find_hero("inf", names) == 1
    assert stats.find_hero("h", names) is None  # ambiguous
    assert stats.badge_range(84) == (80, 89)


def test_compare_flags_weaknesses():
    rows = stats.compare(stats.per_match(MY_ANALYTICS[0]), stats.per_match(BRACKET_ANALYTICS[0]))
    by_key = {r["key"]: r for r in rows}
    assert by_key["souls"]["diff_pct"] < 0 and not by_key["souls"]["good"]
    assert not by_key["deaths"]["good"]          # more deaths is bad
    assert by_key["win_rate"]["good"]            # 60% vs 50%
    tips = stats.coach_tips(rows)
    assert any("souls" in t for t in tips) and any("die" in t for t in tips)


def test_item_rows_filters_abilities_and_sorts_by_win_rate():
    rows = stats.item_rows(ITEM_STATS, stats.purchasable_items(ITEMS))
    assert [r["item_id"] for r in rows] == [100, 200]  # best win rate first
    assert rows[0]["win_rate"] == 60


def test_item_rows_respects_min_matches():
    assert stats.item_rows(ITEM_STATS, stats.purchasable_items(ITEMS), min_matches=200) == []


# ---- draft ------------------------------------------------------------------------


def test_fit_hero_ratings_ranks_the_winner_higher():
    ratings = draft.fit_hero_ratings(COUNTER_STATS)
    assert ratings[1] > ratings[3]


def test_win_probability_favors_the_stronger_side():
    ratings = draft.fit_hero_ratings(COUNTER_STATS)
    assert draft.win_probability(ratings, [1], [3]) > 50
    assert draft.win_probability(ratings, [3], [1]) < 50


def test_unseen_hero_defaults_to_neutral_rating():
    ratings = draft.fit_hero_ratings(COUNTER_STATS)
    assert draft.win_probability(ratings, [1], [999]) > draft.win_probability(ratings, [999], [999])


def test_coach_defaults_to_most_played_and_own_rank(runner):
    result = runner.invoke(main.app, ["coach", "-a", "123"])
    assert result.exit_code == 0, result.output
    assert "Infernus" in result.output and "Ascendant" in result.output
    assert "What to work on" in result.output


def test_coach_unknown_and_unplayed_hero(runner):
    assert "Couldn't find" in runner.invoke(main.app, ["coach", "Nobody", "-a", "123"]).output
    assert "haven't played Haze" in runner.invoke(main.app, ["coach", "haze", "-a", "123"]).output


def test_missing_account_explains_what_to_do(runner):
    result = runner.invoke(main.app, ["summary"])
    assert result.exit_code == 1 and "set-me" in result.output


def test_items(runner):
    result = runner.invoke(main.app, ["items", "infernus"])
    assert result.exit_code == 0, result.output
    assert "Extra Health" in result.output and "Bad Item" in result.output
    assert "Some Ability" not in result.output


def test_items_unknown_hero(runner):
    result = runner.invoke(main.app, ["items", "nobody"])
    assert result.exit_code == 1 and "Couldn't find" in result.output


def test_draft(runner):
    result = runner.invoke(main.app, ["draft", "--allies", "infernus", "--enemies", "wraith"])
    assert result.exit_code == 0, result.output
    assert "Predicted win chance" in result.output
    assert "Infernus" in result.output and "Wraith" in result.output


def test_draft_unknown_hero(runner):
    result = runner.invoke(main.app, ["draft", "--allies", "nobody", "--enemies", "wraith"])
    assert result.exit_code == 1 and "Couldn't find" in result.output
