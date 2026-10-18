"""Draft win predictor.

The community API has no endpoint that returns a full match's draft (all 12 heroes +
outcome), only aggregated pairwise stats. So instead of training on raw matches, this
fits a Bradley-Terry style model: a single "power rating" per hero, learned from real
hero-vs-enemy-hero win/loss counts via logistic regression. A draft's win probability is
sigmoid(sum of ally ratings - sum of enemy ratings). It can't see team synergy or how good
you personally are with a hero - it only knows which heroes tend to beat which.
"""

from __future__ import annotations

import math

from sklearn.linear_model import LogisticRegression


def fit_hero_ratings(counter_stats: list[dict]) -> dict[int, float]:
    """One scalar rating per hero_id, fit on real (hero_id, enemy_hero_id, wins, matches_played) rows."""
    hero_ids = sorted({row["hero_id"] for row in counter_stats} | {row["enemy_hero_id"] for row in counter_stats})
    if not hero_ids:
        return {}
    index = {hero_id: i for i, hero_id in enumerate(hero_ids)}

    features, labels, weights = [], [], []
    for row in counter_stats:
        matches = row.get("matches_played", 0)
        wins = row.get("wins", 0)
        losses = matches - wins
        if matches <= 0:
            continue
        vec = [0.0] * len(hero_ids)
        vec[index[row["hero_id"]]] = 1.0
        vec[index[row["enemy_hero_id"]]] = -1.0
        if wins > 0:
            features.append(vec)
            labels.append(1)
            weights.append(wins)
        if losses > 0:
            features.append(vec)
            labels.append(0)
            weights.append(losses)

    if len(set(labels)) < 2:
        return {hero_id: 0.0 for hero_id in hero_ids}

    model = LogisticRegression(fit_intercept=False)
    model.fit(features, labels, sample_weight=weights)
    return {hero_id: model.coef_[0][i] for hero_id, i in index.items()}


def win_probability(ratings: dict[int, float], allies: list[int], enemies: list[int]) -> float:
    """Predicted chance (0-100) that `allies` beats `enemies`."""
    score = sum(ratings.get(h, 0.0) for h in allies) - sum(ratings.get(h, 0.0) for h in enemies)
    return 1 / (1 + math.exp(-score)) * 100


def rating_breakdown(ratings: dict[int, float], allies: list[int], enemies: list[int]) -> list[dict]:
    """Per-hero rows (hero_id, side, rating), strongest ally and weakest enemy first."""
    rows = [{"hero_id": h, "side": "ally", "rating": ratings.get(h, 0.0)} for h in allies]
    rows += [{"hero_id": h, "side": "enemy", "rating": ratings.get(h, 0.0)} for h in enemies]
    return sorted(rows, key=lambda r: r["rating"] if r["side"] == "ally" else -r["rating"], reverse=True)
