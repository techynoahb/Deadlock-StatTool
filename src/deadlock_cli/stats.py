"""Turns raw API data into the numbers the CLI shows. No network calls in here."""

from __future__ import annotations

from dataclasses import dataclass

STEAM_ID64_BASE = 76561197960265728

# player_match_outcome values from the API
OUTCOME_WIN = 1
OUTCOME_LOSS = 2


def to_account_id(steam_id: int | str) -> int:
    """Accept a SteamID64 (7656119...) or a SteamID3/account ID and return the account ID."""
    value = int(str(steam_id).strip())
    return value - STEAM_ID64_BASE if value >= STEAM_ID64_BASE else value


def is_win(match: dict) -> bool:
    outcome = match.get("player_match_outcome")
    if outcome == OUTCOME_WIN:
        return True
    if outcome == OUTCOME_LOSS:
        return False
    # Older rows: the winning team number is stored in match_result
    return match.get("match_result") == match.get("player_team")


def kda(kills: float, deaths: float, assists: float) -> float:
    """(kills + assists) / deaths, treating 0 deaths as 1 like most trackers."""
    return (kills + assists) / max(deaths, 1)


def souls_per_min(match: dict) -> float:
    minutes = match.get("match_duration_s", 0) / 60
    return match.get("net_worth", 0) / minutes if minutes else 0.0


def rank_label(badge: int | None, rank_names: dict[int, str]) -> str | None:
    """Badges encode tier and subtier: 114 = tier 11, subtier 4."""
    if not badge:
        return None
    tier, sub = divmod(badge, 10)
    name = rank_names.get(tier, f"Tier {tier}")
    return f"{name} {sub}" if sub else name


@dataclass
class Summary:
    matches: int
    wins: int
    avg_kills: float
    avg_deaths: float
    avg_assists: float
    avg_souls_per_min: float
    avg_duration_min: float

    @property
    def win_rate(self) -> float:
        return self.wins / self.matches * 100 if self.matches else 0.0

    @property
    def kda(self) -> float:
        return kda(self.avg_kills, self.avg_deaths, self.avg_assists)


def summarize(matches: list[dict]) -> Summary:
    n = len(matches)
    if n == 0:
        return Summary(0, 0, 0, 0, 0, 0, 0)

    def avg(values) -> float:
        return sum(values) / n

    return Summary(
        matches=n,
        wins=sum(is_win(m) for m in matches),
        avg_kills=avg(m["player_kills"] for m in matches),
        avg_deaths=avg(m["player_deaths"] for m in matches),
        avg_assists=avg(m["player_assists"] for m in matches),
        avg_souls_per_min=avg(souls_per_min(m) for m in matches),
        avg_duration_min=avg(m["match_duration_s"] / 60 for m in matches),
    )


def most_played(matches: list[dict], top: int = 3) -> list[tuple[int, int, int]]:
    """[(hero_id, games, wins), ...] sorted by games played."""
    counts: dict[int, list[int]] = {}
    for m in matches:
        games_wins = counts.setdefault(m["hero_id"], [0, 0])
        games_wins[0] += 1
        games_wins[1] += is_win(m)
    ranked = sorted(counts.items(), key=lambda kv: kv[1][0], reverse=True)
    return [(hero, g, w) for hero, (g, w) in ranked[:top]]


def current_rank_badge(matches: list[dict]) -> int | None:
    """Most recent ranked badge in the history (matches are newest first)."""
    for m in matches:
        if m.get("ranked_display_badge"):
            return m["ranked_display_badge"]
    return None


def find_hero(query: str, names: dict[int, str]) -> int | None:
    """Match a hero by name, case-insensitive. Exact match wins, then a unique prefix."""
    q = query.strip().lower()
    for hero_id, name in names.items():
        if name.lower() == q:
            return hero_id
    matches = [hero_id for hero_id, name in names.items() if name.lower().startswith(q)]
    return matches[0] if len(matches) == 1 else None


def badge_range(badge: int) -> tuple[int, int]:
    """All subtiers of the badge's tier: 84 (Ascendant 4) -> (80, 89)."""
    tier = badge // 10
    return tier * 10, tier * 10 + 9


def per_match(row: dict) -> dict[str, float]:
    """Turn an analytics hero-stats row (totals) into per-match averages."""
    n = row.get("matches", 0)
    if not n:
        return {}
    shots = row.get("total_shots_hit", 0) + row.get("total_shots_missed", 0)
    return {
        "win_rate": row.get("wins", 0) / n * 100,
        "kills": row.get("total_kills", 0) / n,
        "deaths": row.get("total_deaths", 0) / n,
        "assists": row.get("total_assists", 0) / n,
        "souls": row.get("total_net_worth", 0) / n,
        "last_hits": row.get("total_last_hits", 0) / n,
        "denies": row.get("total_denies", 0) / n,
        "hero_damage": row.get("total_player_damage", 0) / n,
        "damage_taken": row.get("total_player_damage_taken", 0) / n,
        "objective_damage": row.get("total_boss_damage", 0) / n,
        "accuracy": row.get("total_shots_hit", 0) / shots * 100 if shots else 0.0,
    }


# (key, label, higher_is_better, format)
COACH_METRICS = [
    ("win_rate", "Win rate", True, "{:.0f}%"),
    ("kills", "Kills", True, "{:.1f}"),
    ("deaths", "Deaths", False, "{:.1f}"),
    ("assists", "Assists", True, "{:.1f}"),
    ("souls", "Souls", True, "{:,.0f}"),
    ("last_hits", "Last hits", True, "{:.0f}"),
    ("denies", "Denies", True, "{:.1f}"),
    ("hero_damage", "Hero damage", True, "{:,.0f}"),
    ("damage_taken", "Damage taken", False, "{:,.0f}"),
    ("objective_damage", "Objective damage", True, "{:,.0f}"),
    ("accuracy", "Accuracy", True, "{:.0f}%"),
]


def compare(mine: dict[str, float], average: dict[str, float]) -> list[dict]:
    """Side-by-side rows with a % difference and whether the gap is good or bad for you."""
    rows = []
    for key, label, higher_better, fmt in COACH_METRICS:
        you, avg = mine.get(key, 0.0), average.get(key, 0.0)
        diff_pct = (you - avg) / avg * 100 if avg else 0.0
        good = diff_pct >= 0 if higher_better else diff_pct <= 0
        rows.append({"key": key, "label": label, "you": you, "avg": avg,
                     "diff_pct": diff_pct, "good": good, "fmt": fmt})
    return rows


TIPS = {
    "souls": "You're behind on souls. Clear more creeps and jungle camps between fights.",
    "last_hits": "Fewer last hits than average. Focus on securing the creep kill and orb in lane.",
    "denies": "Deny more. Shooting enemy orbs takes souls away from your lane opponent.",
    "deaths": "You die more than average. Back off when low and track where enemies are.",
    "hero_damage": "Below-average hero damage. Look for more fights or rethink your damage items.",
    "objective_damage": "Low objective damage. Push guardians and walkers after winning fights.",
    "accuracy": "Accuracy is below average. Try aiming for heads and practice in the sandbox.",
    "assists": "Fewer assists than average. Group up with your team for fights more often.",
}


def coach_tips(rows: list[dict], threshold: float = 10.0, limit: int = 3) -> list[str]:
    """Plain-language advice for your biggest weaknesses (more than `threshold`% off)."""
    weak = [r for r in rows if not r["good"] and abs(r["diff_pct"]) >= threshold and r["key"] in TIPS]
    weak.sort(key=lambda r: abs(r["diff_pct"]), reverse=True)
    return [TIPS[r["key"]] for r in weak[:limit]]


def purchasable_items(items: list[dict]) -> dict[int, dict]:
    """Keep only shop items (the assets endpoint also returns abilities and weapons)."""
    return {
        i["id"]: {"name": i["name"], "slot": i.get("item_slot_type", ""), "tier": i.get("item_tier", 0)}
        for i in items
        if i.get("type") == "upgrade"
    }


def item_rows(item_stats: list[dict], items: dict[int, dict], min_matches: int = 30) -> list[dict]:
    """Clean per-item rows from the item-stats endpoint, best win rate first."""
    rows = []
    for row in item_stats:
        item = items.get(row["item_id"])
        if item is None or row.get("matches", 0) < min_matches:
            continue
        rows.append({
            "item_id": row["item_id"],
            "name": item["name"],
            "slot": item["slot"],
            "tier": item["tier"],
            "win_rate": row["wins"] / row["matches"] * 100,
            "matches": row["matches"],
            "players": row.get("players", 0),
        })
    return sorted(rows, key=lambda r: r["win_rate"], reverse=True)


def hero_rows(hero_stats: list[dict], min_games: int = 1) -> list[dict]:
    """Clean per-hero rows from the hero-stats endpoint, most played first."""
    rows = []
    for h in hero_stats:
        games = h.get("matches_played", 0)
        if games < min_games:
            continue
        rows.append({
            "hero_id": h["hero_id"],
            "games": games,
            "win_rate": h.get("wins", 0) / games * 100,
            "kda": kda(h.get("kills", 0), h.get("deaths", 0), h.get("assists", 0)),
            "souls_per_min": h.get("networth_per_min", 0.0),
            "damage_per_min": h.get("damage_per_min", 0.0),
            "accuracy": h.get("accuracy", 0.0) * 100,
            "last_played": h.get("last_played", 0),
        })
    return sorted(rows, key=lambda r: r["games"], reverse=True)
