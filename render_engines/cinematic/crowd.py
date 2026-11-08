"""Crowds: hundreds of light people (6 primitives each, looping limb animation) so a street or a theatre
looks full without the cost of the detailed hero characters.

- walkers: people walking or running along a direction, with a cyclic stride;
- standers: people standing in groups, idling, some looking up at the screens;
- seated: theatre audience rows, merged into one mesh per row.
"""

from __future__ import annotations

import math
import random

from mathutils import Matrix

from render_engines.core.blender import materials, objects
from render_engines.core.blender.animation import fcurves, key

CLOTHES = (
    "#355c7d",
    "#6c5b7b",
    "#c06c84",
    "#4a7c59",
    "#8c6d46",
    "#2f3e46",
    "#d9a400",
    "#b3261e",
    "#e8e8e8",
    "#1f4e8c",
    "#7a4a3f",
    "#3f3f46",
    "#e07a3a",
    "#5e8c61",
)
SKINS = ("#e0ac85", "#c68642", "#8d5524", "#f1c27d", "#d9a27e", "#6b4226")
HAIR = ("#2d1e14", "#6b4423", "#1b1b1b", "#b89778", "#a33a1a")
TROUSERS = ("#22252b", "#3b4a5e", "#4b3f33", "#1d2f45", "#555a60")


def _mat(color: str, rough: float = 0.8):
    return materials.principled(f"crowd_{color}", color, roughness=rough)


def _cycle(obj) -> None:
    """Repeat the object's keyframes forever (a looping stride)."""
    for curve in fcurves(obj):
        curve.modifiers.new("CYCLES")


def _t(bm, at, scale=(1, 1, 1)):
    return objects.transform(bm, Matrix.Translation(at) @ Matrix.Diagonal((*scale, 1)))


def crowd_person(name: str, location, heading: float, rng, scale: float = 1.0, col=None, zombie: bool = False):
    """A light but well-formed person in 5 objects: body (torso, jacket, head, face, hair, bag) + 4 limbs
    (trouser leg + shoe, sleeve + hand). Outfits, hairstyles and silhouettes vary with the seed."""
    from render_engines.cinematic.urban import compound

    top = _mat("#4f5544" if zombie else rng.choice(CLOTHES))
    inner = _mat(rng.choice(("#f2efe9", "#2b2b30", "#c9c2b8", "#8a1f2b")))
    bottom = _mat("#2b2622" if zombie else rng.choice(TROUSERS + CLOTHES[:4]))
    skin = _mat("#8ea377" if zombie else rng.choice(SKINS), 0.55)
    hair = _mat(rng.choice(HAIR), 0.6)
    shoe = _mat(rng.choice(("#151515", "#f2f2f2", "#5a3a22", "#2a3a5a")), 0.5)
    dark = _mat("#141418", 0.3)
    wide = rng.uniform(0.9, 1.18)  # body build
    skirt = not zombie and rng.random() < 0.25
    root = objects.empty(f"{name}_root", location=location, col=col)
    root.rotation_euler = (0, 0, heading)
    root.scale = (scale, scale, scale)

    parts = [
        (_t(objects.capsule(0.19, 0.56), (0, 0, 1.46), (wide, 0.8, 1)), top),  # jacket / top
        (_t(objects.box(0.12, 0.02, 0.4), (0, 0.15, 1.2)), inner),  # shirt showing at the front
        (_t(objects.sphere(0.16, 16, 8), (0, 0, 0.93), (wide, 0.75, 0.6)), bottom),  # hips
        (_t(objects.sphere(0.07, 10, 6), (0, 0, 1.49), (1, 1, 1.2)), skin),  # neck
        (_t(objects.sphere(0.125, 16, 10), (0, 0, 1.62), (1, 1.05, 1.1)), skin),  # head
        (_t(objects.sphere(0.022, 8, 6), (-0.045, 0.115, 1.64)), dark),  # eyes
        (_t(objects.sphere(0.022, 8, 6), (0.045, 0.115, 1.64)), dark),
        (_t(objects.sphere(0.025, 8, 6), (0, 0.13, 1.6)), skin),  # nose
    ]
    style = rng.choice(("short", "short", "long", "bun", "cap", "bald", "curly"))
    if style in ("short", "curly", "bun", "long"):
        parts.append((_t(objects.sphere(0.132, 16, 8), (0, -0.02, 1.66), (1.02, 1.0, 0.8)), hair))
    if style == "curly":
        parts += [(_t(objects.sphere(0.06, 8, 6), (dx, -0.02, 1.74)), hair) for dx in (-0.08, 0, 0.08)]
    if style == "long":
        parts.append((_t(objects.sphere(0.12, 12, 8), (0, -0.08, 1.5), (1.05, 0.6, 1.4)), hair))
    if style == "bun":
        parts.append((_t(objects.sphere(0.06, 10, 6), (0, -0.1, 1.76)), hair))
    if style == "cap":
        cap = _mat(rng.choice(CLOTHES), 0.6)
        parts += [
            (_t(objects.sphere(0.135, 14, 8), (0, -0.01, 1.68), (1, 1, 0.6)), cap),
            (_t(objects.box(0.2, 0.14, 0.02), (0, 0.13, 1.68)), cap),
        ]
    if skirt:
        parts.append((_t(objects.cone(0.17, 0.27, 0.45, 16, base_at_origin=False), (0, 0, 0.72)), bottom))
    if not zombie and rng.random() < 0.35:  # a bag or a backpack
        bag = _mat(rng.choice(("#3a2a20", "#1f1f24", "#b3261e", "#d9a400")), 0.7)
        if rng.random() < 0.5:
            parts.append((_t(objects.box(0.28, 0.14, 0.36), (0, -0.2, 1.3)), bag))
        else:
            parts.append((_t(objects.box(0.06, 0.24, 0.22), (0.27 * wide, 0.02, 0.95)), bag))
    compound(f"{name}_body", parts, col=col, smooth=True).parent = root

    limbs = {}
    for side, sx in (("L", -1), ("R", 1)):
        hip = objects.empty(f"{name}_hip_{side}", location=(0.085 * sx, 0, 0.9), parent=root, col=col)
        leg_mat = skin if skirt else bottom
        leg = compound(
            f"{name}_leg_{side}",
            [
                (objects.capsule(0.06 if skirt else 0.075, 0.84), leg_mat),
                (_t(objects.sphere(0.07, 10, 6), (0, 0.05, -0.84), (1, 1.7, 0.6)), shoe),
            ],
            col=col,
            smooth=True,
        )
        leg.parent = hip
        shoulder = objects.empty(f"{name}_sh_{side}", location=(0.22 * sx * wide, 0, 1.4), parent=root, col=col)
        arm = compound(
            f"{name}_arm_{side}",
            [(objects.capsule(0.058, 0.56), top), (_t(objects.sphere(0.05, 10, 6), (0, 0, -0.6)), skin)],
            col=col,
            smooth=True,
        )
        arm.parent = shoulder
        limbs[f"leg_{side}"], limbs[f"arm_{side}"] = hip, shoulder
    if zombie:
        for side in ("L", "R"):
            limbs[f"arm_{side}"].rotation_euler = (math.radians(80), 0, 0)
    return root, limbs


def _stride(root, limbs, frame0: int, cycle_frames: int, swing: float, zombie: bool = False) -> None:
    """One looping stride cycle on the limbs and a bob on the root height."""
    half = cycle_frames // 2
    for f, sign in ((frame0, 1), (frame0 + half, -1), (frame0 + cycle_frames, 1)):
        key(limbs["leg_L"], "rotation_euler", f, (swing * sign, 0, 0))
        key(limbs["leg_R"], "rotation_euler", f, (-swing * sign, 0, 0))
        if not zombie:
            key(limbs["arm_L"], "rotation_euler", f, (-swing * 0.8 * sign, 0, 0))
            key(limbs["arm_R"], "rotation_euler", f, (swing * 0.8 * sign, 0, 0))
    for obj in limbs.values():
        _cycle(obj)


def walkers(
    count: int,
    area,
    direction_deg: float,
    speed,
    frame_start: int,
    frame_end: int,
    fps: int,
    seed: int,
    col=None,
    zombie: bool = False,
    keep_clear=None,
) -> list:
    """People moving across a rectangle area ((x0, x1), (y0, y1)) along a direction, at random speeds."""
    rng = random.Random(seed)
    heading = math.radians(direction_deg)
    duration = (frame_end - frame_start) / fps
    roots = []
    for i in range(count):
        x = rng.uniform(*area[0])
        y = rng.uniform(*area[1])
        if keep_clear and keep_clear(x, y):
            continue
        v = rng.uniform(*speed)
        root, limbs = crowd_person(
            f"cw_{seed}_{i}", (x, y, 0), heading - math.pi / 2, rng, rng.uniform(0.92, 1.08), col, zombie
        )
        dx, dy = math.cos(heading) * v * duration, math.sin(heading) * v * duration
        key(root, "location", frame_start, (x, y, 0))
        key(root, "location", frame_end, (x + dx, y + dy, 0))
        for curve in fcurves(root):
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
        running = v > 2.2
        cycle = max(8, round(fps / (2.6 if running else 1.7)))
        _stride(root, limbs, frame_start - rng.randint(0, cycle), cycle, math.radians(38 if running else 24), zombie)
        roots.append(root)
    return roots


def standers(
    count: int,
    area,
    frame_start: int,
    frame_end: int,
    fps: int,
    seed: int,
    col=None,
    look_up: float = 0.3,
    face_deg: float | None = None,
    keep_clear=None,
) -> list:
    """People standing around (idle sway); some look up at the screens, a few point."""
    rng = random.Random(seed)
    roots = []
    for i in range(count):
        x, y = rng.uniform(*area[0]), rng.uniform(*area[1])
        if keep_clear and keep_clear(x, y):
            continue
        heading = math.radians(face_deg if face_deg is not None else rng.uniform(0, 360))
        root, limbs = crowd_person(f"cs_{seed}_{i}", (x, y, 0), heading, rng, rng.uniform(0.92, 1.08), col)
        sway = rng.uniform(0.02, 0.05)
        period = rng.randint(round(fps * 2), round(fps * 4))
        for f in range(frame_start - rng.randint(0, period), frame_end + period, period):
            key(root, "rotation_euler", f, (0, sway, heading))
            key(root, "rotation_euler", f + period // 2, (0, -sway, heading))
        if rng.random() < look_up * 0.4:  # pointing at something
            limbs["arm_R"].rotation_euler = (math.radians(140), 0, math.radians(10))
        roots.append(root)
    return roots


def audience_row(name: str, x_range, y: float, z: float, step: float, fill: float, rng, col=None):
    """One theatre row of seated people, merged into a single mesh (torso + head + hair per person)."""
    from render_engines.cinematic.urban import compound

    parts = []
    x = x_range[0]
    while x <= x_range[1]:
        if rng.random() < fill:
            body = _mat(rng.choice(CLOTHES))
            skin = _mat(rng.choice(SKINS), 0.55)
            hair = _mat(rng.choice(HAIR), 0.6)
            lean = rng.uniform(-0.04, 0.04)
            parts += [
                (objects.transform(objects.capsule(0.18, 0.55), Matrix.Translation((x + lean, 0, 1.05))), body),
                (objects.transform(objects.sphere(0.12, 12, 8), Matrix.Translation((x + lean, 0, 1.17))), skin),
                (
                    objects.transform(
                        objects.sphere(0.125, 12, 8),
                        Matrix.Translation((x + lean, 0.02, 1.21)) @ Matrix.Diagonal((1, 1, 0.75, 1)),
                    ),
                    hair,
                ),
            ]
        x += step
    if not parts:
        return None
    return compound(name, parts, (0, y, z), col=col)
