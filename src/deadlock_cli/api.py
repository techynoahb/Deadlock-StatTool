"""Small client for the community Deadlock API (https://api.deadlock-api.com/docs).

Every function here only fetches data. All the math lives in stats.py, so it can be
tested without the network and reused later by the coach and ML commands.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://api.deadlock-api.com"
CACHE_DIR = Path.home() / ".cache" / "deadlock-cli"
ASSET_CACHE_SECONDS = 24 * 60 * 60  # hero and rank names rarely change


class APIError(Exception):
    """Raised when the API can't be reached or returns an error."""


class DeadlockAPI:
    def __init__(self, base_url: str = BASE_URL, client: httpx.Client | None = None):
        self.client = client or httpx.Client(
            base_url=base_url,
            timeout=20,
            headers={"User-Agent": "deadlock-cli/0.1"},
        )

    def _get(self, path: str, **params: Any) -> Any:
        try:
            response = self.client.get(path, params=params or None)
        except httpx.HTTPError as e:
            raise APIError(f"Couldn't reach the Deadlock API ({e}).") from e
        if response.status_code == 429:
            raise APIError("Rate limited by the Deadlock API. Wait a minute and try again.")
        if response.status_code >= 400:
            detail = response.text.strip()[:200]
            raise APIError(f"API returned {response.status_code} for {path}: {detail}")
        return response.json()

    def _cached(self, name: str, path: str, **params: Any) -> Any:
        """Fetch rarely-changing asset data, reusing a local copy for a day."""
        cache_file = CACHE_DIR / f"{name}.json"
        if cache_file.exists() and time.time() - cache_file.stat().st_mtime < ASSET_CACHE_SECONDS:
            try:
                return json.loads(cache_file.read_text())
            except json.JSONDecodeError:
                pass
        data = self._get(path, **params)
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data))
        except OSError:
            pass  # caching is a nice-to-have
        return data

    # ---- players -------------------------------------------------------------

    def match_history(self, account_id: int) -> list[dict]:
        """Every stored match for a player, newest first."""
        return self._get(f"/v1/players/{account_id}/match-history")

    def hero_stats(self, account_id: int) -> list[dict]:
        """Lifetime per-hero totals and per-minute averages for a player."""
        return self._get("/v1/players/hero-stats", account_ids=account_id)

    def search_players(self, name: str, limit: int = 10) -> list[dict]:
        """Find Steam profiles by name (only players with recent Deadlock matches)."""
        return self._get("/v1/players/steam-search", search_query=name, limit=limit)

    # ---- analytics -----------------------------------------------------------

    def analytics_hero_stats(
        self,
        account_id: int | None = None,
        min_badge: int | None = None,
        max_badge: int | None = None,
        since_unix: int | None = None,
    ) -> list[dict]:
        """Per-hero totals (kills, souls, damage, shots...) for a player or a rank bracket.

        With account_id: only that player's matches. With min/max_badge: every match whose
        average team badge falls in that range. Both use the same time window, so the
        numbers line up for comparison.
        """
        params: dict[str, Any] = {}
        if account_id is not None:
            params["account_ids"] = account_id
        if min_badge is not None:
            params["min_average_badge"] = min_badge
        if max_badge is not None:
            params["max_average_badge"] = max_badge
        if since_unix is not None:
            params["min_unix_timestamp"] = since_unix
        return self._get("/v1/analytics/hero-stats", **params)

    def hero_counter_stats(self, min_matches: int = 50, since_unix: int | None = None) -> list[dict]:
        """Win rate for every (hero, enemy hero) pair that's faced off enough. Bulk data, cached a day."""
        params: dict[str, Any] = {"min_matches": min_matches}
        if since_unix is not None:
            params["min_unix_timestamp"] = since_unix
        return self._cached("hero_counter_stats", "/v1/analytics/hero-counter-stats", **params)

    def item_stats(
        self,
        hero_id: int,
        enemy_hero_ids: list[int] | None = None,
        min_matches: int = 30,
        since_unix: int | None = None,
    ) -> list[dict]:
        """Win rate per item for a hero, optionally narrowed to a specific enemy matchup."""
        params: dict[str, Any] = {"hero_ids": hero_id, "min_matches": min_matches}
        if enemy_hero_ids:
            params["enemy_hero_ids"] = ",".join(str(h) for h in enemy_hero_ids)
        if since_unix is not None:
            params["min_unix_timestamp"] = since_unix
        return self._get("/v1/analytics/item-stats", **params)

    # ---- assets --------------------------------------------------------------

    def hero_names(self) -> dict[int, str]:
        heroes = self._cached("heroes", "/v1/assets/heroes")
        return {h["id"]: h["name"] for h in heroes}

    def rank_names(self) -> dict[int, str]:
        ranks = self._cached("ranks", "/v1/assets/ranks")
        return {r["tier"]: r["name"] for r in ranks}

    def items(self) -> list[dict]:
        """Every game asset (heroes' abilities and weapons too). Filter to purchasable items in stats.py."""
        return self._cached("items", "/v1/assets/items")
