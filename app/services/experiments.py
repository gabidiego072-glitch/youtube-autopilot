"""Learning what works: every video tries one option per dimension, results decide the next ones.

Dimensions: narrator voice, music mood, video length and hook style (topics are already steered by
category weights). For each dimension the choice is epsilon-greedy:

- options with fewer than MIN_TRIES results are tried first (systematic exploration);
- afterwards, most videos (1 - EPSILON) use the best-scoring option so far and the rest explore.

A video's score mixes retention (how much of it people watch), the stayed-to-watch ratio (engaged views /
views: who did not swipe away in the first seconds) and reach (its views ranked against the channel's other
videos), all 0..1. Without engaged views the score is retention and reach only.
YouTube Analytics data arrives with a delay of ~2-3 days, so a
video only counts once it has a snapshot.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from statistics import mean

from sqlalchemy.orm import Session

from app.services.analytics.metrics import derive
from app.services.reporting.builder import latest_snapshots

MIN_TRIES = 2
EPSILON = 0.25


@dataclass(frozen=True)
class Voice:
    model: str  # Piper model file name in the voices folder
    speaker: int | None = None
    credit: str | None = None  # attribution the voice's licence asks for (goes into the description)


VOICES = {
    # All of them allow commercial use (CC0, CC BY 3.0, Apache-2.0, Unlicense, CC BY-SA 4.0).
    "davefx": Voice("es_ES-davefx-medium.onnx"),
    "sharvard_m": Voice(
        "es_ES-sharvard-medium.onnx", 0, "Voz: Piper sharvard (Sharvard corpus, CC BY 3.0, Univ. of Edinburgh)"
    ),
    "sharvard_f": Voice(
        "es_ES-sharvard-medium.onnx", 1, "Voz: Piper sharvard (Sharvard corpus, CC BY 3.0, Univ. of Edinburgh)"
    ),
    "claude_mx": Voice("es_MX-claude-high.onnx"),
    "ald_mx": Voice("es_MX-ald-medium.onnx"),
    "daniela_ar": Voice("es_AR-daniela-high.onnx", None, "Voz: Piper daniela (OpenSLR 61, CC BY-SA 4.0)"),
}

MUSIC = ("wistful", "tense", "bright", "curious", "rising")  # index = audio.synth PROGRESSIONS index

LENGTHS = ("32", "45", "58")  # Short target duration in seconds

HOOKS = {
    "question": "Open with a direct, intriguing question to the viewer.",
    "number": "Open with one striking number (a speed, a size, a time) that sounds impossible.",
    "you": "Open by putting the viewer inside the situation, in second person ('Estás en...').",
    "consequence": "Open with the most dramatic consequence first, then explain how we get there.",
}

DIMENSIONS: dict[str, tuple[str, ...]] = {
    "voice": tuple(VOICES),
    "music": MUSIC,
    "length": LENGTHS,
    "hook": tuple(HOOKS),
}


def _scores(db: Session, channel_id: uuid.UUID) -> list[tuple[dict, float]]:
    """(features, score) for every video of the channel that has analytics."""
    latest = [(p, s) for p, s in latest_snapshots(db, channel_id) if p.features]
    rows = [(project, derive(snapshot, project.target_duration_seconds)) for project, snapshot in latest]
    engaged = {
        p.id: min(1.0, s.engaged_views / s.views)
        for p, s in latest
        if getattr(s, "engaged_views", None) is not None and s.views
    }
    if not rows:
        return []
    views_sorted = sorted(m.views for _, m in rows)
    out = []
    for project, metrics in rows:
        reach = (views_sorted.index(metrics.views) + 1) / len(views_sorted) if len(rows) > 1 else 0.5
        retention = min(1.0, metrics.retention_ratio) if metrics.retention_ratio is not None else 0.5
        stayed = engaged.get(project.id)
        with_stayed = 0.35 * retention + 0.35 * (stayed or 0) + 0.3 * reach
        score = 0.5 * retention + 0.5 * reach if stayed is None else with_stayed
        out.append((project.features, round(score, 4)))
    return out


def standings(history: list[tuple[dict, float]]) -> dict[str, dict[str, dict]]:
    """Per dimension and option: tries and mean score."""
    table: dict[str, dict[str, dict]] = {}
    for dim, options in DIMENSIONS.items():
        table[dim] = {}
        for option in options:
            scores = [score for features, score in history if features.get(dim) == option]
            table[dim][option] = {"tries": len(scores), "score": round(mean(scores), 3) if scores else None}
    return table


def choose(history: list[tuple[dict, float]], rng: random.Random) -> dict[str, str]:
    choice = {}
    table = standings(history)
    for dim, options in DIMENSIONS.items():
        stats = table[dim]
        untried = [o for o in options if stats[o]["tries"] < MIN_TRIES]
        if untried:
            fewest = min(stats[o]["tries"] for o in untried)
            choice[dim] = rng.choice([o for o in untried if stats[o]["tries"] == fewest])
        elif rng.random() < EPSILON:
            choice[dim] = rng.choice(options)
        else:
            choice[dim] = max(options, key=lambda o: stats[o]["score"])
    return choice


def choose_for_channel(db: Session, channel_id: uuid.UUID, seed: int) -> dict[str, str]:
    return choose(_scores(db, channel_id), random.Random(seed))


def channel_standings(db: Session, channel_id: uuid.UUID) -> dict:
    history = _scores(db, channel_id)
    return {"videos_with_results": len(history), "dimensions": standings(history)}
