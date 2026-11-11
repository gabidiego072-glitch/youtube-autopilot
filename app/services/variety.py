"""Variety between videos, so the channel never looks mass-produced or templated.

YouTube does not monetise "inauthentic" content (mass-produced, repetitive, made from a template).
Each new video is steered away from the last ones at three points:

- topic:      prefer a category not used in the last two videos and a premise unlike recent titles;
- script:     the writer sees recent titles and hooks and must not reuse their wording or structure;
- storyboard: the planner sees which places, times of day and camera styles were used recently.

Music also varies: every video gets its own key, chord progression and tempo (see audio.synth).
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import VideoProject
from app.services.ideas.generator import normalize

RECENT = 8  # videos to compare against
SIMILAR_TITLE = 0.6  # premises this close to a recent title count as repetitive


@dataclass
class RecentVideos:
    titles: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)  # newest first
    environments: Counter = field(default_factory=Counter)
    times_of_day: Counter = field(default_factory=Counter)
    recipes: Counter = field(default_factory=Counter)  # scene recipes and choices the last videos used
    objects: list[str] = field(default_factory=list)

    def script_note(self) -> str | None:
        if not self.titles:
            return None
        lines = [f"- {t} | gancho: {h}" for t, h in zip(self.titles, self.hooks, strict=False)]
        return (
            "Recent videos on this channel (do NOT reuse their wording, hook structure or ending question; "
            "this video must feel clearly different):\n" + "\n".join(lines)
        )

    def recipe_note(self) -> str | None:
        """For the recipe director: what the last videos already showed, so this one shows something else."""
        if not self.recipes:
            return None
        used = ", ".join(f"{k} x{v}" for k, v in self.recipes.most_common())
        note = f"NOVELTY: the last videos of this channel already showed: {used}."
        if self.objects:
            note += f" Objects already built: {', '.join(sorted(set(self.objects)))}."
        return note + (
            " Viewers notice repeats: use those recipes only where the line really needs them, prefer the ones "
            "not listed (or other choices of people, room, time of day, item, hands), and add one new object."
        )

    def storyboard_note(self) -> str | None:
        if not self.environments:
            return None
        env = ", ".join(f"{k} x{v}" for k, v in self.environments.most_common())
        times = ", ".join(f"{k} x{v}" for k, v in self.times_of_day.most_common())
        return (
            f"Variety: the last videos used these places: {env}; times of day: {times}. "
            "Where the script allows it, choose other places (another room type or street style), times of day, "
            "camera heights and lenses, so this video does not look like the previous ones."
        )


def recent_videos(db: Session, channel_id: uuid.UUID, limit: int = RECENT) -> RecentVideos:
    projects = db.scalars(
        select(VideoProject)
        .where(VideoProject.channel_id == channel_id)
        .order_by(VideoProject.created_at.desc())
        .limit(limit)
    )
    recent = RecentVideos()
    for project in projects:
        script = project.scripts[-1] if project.scripts else None
        recent.titles.append((script.title_question if script else None) or project.working_title)
        recent.hooks.append(script.hook if script else "")
        if project.category:
            recent.categories.append(project.category.value)
        for spec in (script.scene_specs or []) if script else []:
            env = spec.get("environment", {})
            place = env.get("type", "?")
            detail = env.get("room") or env.get("style")
            recent.environments[f"{place}/{detail}" if detail else place] += 1
            recent.times_of_day[env.get("time_of_day", "day")] += 1
            if spec.get("recipe"):
                pick = spec.get("pick") or {}
                key = spec["recipe"]
                if key == "room_view" and pick.get("room"):
                    key += f"/{pick['room']}"
                if pick.get("people") not in (None, "busy"):
                    key += f"/{pick['people']}"
                recent.recipes[key] += 1
            if spec.get("object_name"):
                recent.objects.append(spec["object_name"])
    return recent


def too_similar(premise: str, titles: list[str], threshold: float = SIMILAR_TITLE) -> bool:
    candidate = normalize(premise)
    return any(SequenceMatcher(None, candidate, normalize(t)).ratio() >= threshold for t in titles)


def pick_idea(ideas: list, recent: RecentVideos):
    """Best-scored idea that does not repeat the last two categories or look like a recent title.
    Falls back gradually so a run is never blocked for lack of variety."""
    last_two = set(recent.categories[:2])
    rules = (
        lambda i: i.category.value not in last_two and not too_similar(i.premise, recent.titles),
        lambda i: not too_similar(i.premise, recent.titles),
        lambda i: True,
    )
    for rule in rules:
        for idea in ideas:  # already sorted best first
            if rule(idea):
                return idea
    return None
