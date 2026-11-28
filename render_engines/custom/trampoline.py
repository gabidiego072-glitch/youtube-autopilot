"""'¿Qué pasaría si tu cama fuera una CAMA ELÁSTICA?' (Nov 27, the owner: hypothetical ideas like the ramp, a
different one on each channel). ONE bed, ONE house, ONE kid, and every bounce higher than the last:

  half a metre -> the ceiling -> through the roof -> over the street -> over the town -> through the clouds -> a plane
  -> the fall -> straight back into bed... which is still a trampoline (the ending loops into the opening).

params: stage (one of STAGES). The town, the house and the sky are the balloon video's (balloons.py), the bedroom
is parts.bedroom(); built from render_engines/custom/parts.py.
"""

from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

from render_engines.core.blender.animation import key
from render_engines.custom import balloons as B
from render_engines.custom import parts as P
from render_engines.custom.ramp import _camera, _hero

SEED = 2711
STAGES = ("hook", "bed", "ceiling", "roof", "street", "town", "clouds", "plane", "fall", "land")
ROOM = Vector((3000.0, 0.0, 0.0))  # the bedroom set, far from the town
YOU = Vector((0.0, 1.2, 0.0))  # where you go up through your roof (house space = world: the house is at the origin)
SLOPE = math.atan2(4.0, B.D / 2 + 0.6)  # the front pitch of the roof


def _roof_hole(frame: int | None = None):
    """The hole you leave in the front pitch of the roof (appears on `frame`)."""
    y = YOU.y + 0.4
    z = B.H + 4 - y * math.tan(SLOPE) + 0.06
    hole = P._mesh_object("roof_hole", [(P.mat("hole", "#1a1410", 1.0), [((0, 0, -0.02), (2.2, 1.8, 0.04))])])
    hole.location = (YOU.x, y, z)
    hole.rotation_euler = (-SLOPE, 0, 0)
    if frame is not None:
        P._appear(hole, frame)
        key(hole, "scale", frame, (1, 1, 1))
    return Vector((YOU.x, y, z))


def _burst(name: str, at, frame: int, fps: int, colour: str, n: int = 26, up=(6, 12), out=(2, 6), seed: int = 0):
    """Bits thrown up and out from `at` on `frame` (roof tiles, plaster), falling back under gravity."""
    rng = random.Random(seed)
    material = P.mat(f"{name}_bits", colour, rough=0.8)
    g = 9.81
    at = Vector(at)
    for i in range(n):
        bit = P._mesh_object(f"{name}{i}", [(material, [((0, 0, -0.5), (1, 1, 1))])])
        s = rng.uniform(0.15, 0.45)
        a, v_up, v_out = rng.uniform(0, 2 * math.pi), rng.uniform(*up), rng.uniform(*out)
        P._appear(bit, frame)
        key(bit, "scale", frame, (s, s * 0.7, s * 0.25))
        flight = 2 * v_up / g + 0.6
        for k in range(9):
            t = k / 8 * flight
            p = at + Vector((math.cos(a) * v_out * t, math.sin(a) * v_out * t, v_up * t - g * t * t / 2))
            p.z = max(p.z, 0.05)
            key(bit, "location", frame + int(t * fps), tuple(p))
            key(bit, "rotation_euler", frame + int(t * fps), (t * 7, t * 5, t * 3))


def _dust(name: str, at, frame: int, fps: int, size: float = 1.0, n: int = 10, seed: int = 0) -> None:
    rng = random.Random(seed)
    soft = P._soft(f"{name}_dust", "#e8e1d4")
    for i in range(n):
        p = P._sphere(f"{name}{i}", size * 0.5, soft, tuple(at))
        p.visible_shadow = False
        P._appear(p, frame)
        key(p, "scale", frame, (0.3, 0.3, 0.3))
        a = rng.uniform(0, 2 * math.pi)
        end = Vector(at) + Vector((math.cos(a), math.sin(a), rng.uniform(0.2, 0.8))) * size * 1.8
        key(p, "location", frame + int(fps * 1.2), tuple(end))
        key(p, "scale", frame + int(fps * 1.2), (1.6, 1.6, 1.3))
        key(p, "scale", frame + int(fps * 1.2) + 1, (0.001, 0.001, 0.001))


def _arc(root, f0: int, f1: int, xy, z0: float, apex: float, z1: float | None = None, n: int = 12) -> None:
    """A ballistic hop from z0 up to apex and down to z1 (default z0) between two frames, at (x, y)."""
    z1 = z0 if z1 is None else z1
    # time of the top so that both halves are parabolas with the same gravity
    up, down = math.sqrt(max(apex - z0, 1e-4)), math.sqrt(max(apex - z1, 1e-4))
    top = up / (up + down)
    for i in range(n + 1):
        t = i / n
        if t <= top:
            u = t / top
            z = z0 + (apex - z0) * (1 - (1 - u) ** 2)
        else:
            u = (t - top) / (1 - top)
            z = apex - (apex - z1) * u * u
        key(root, "location", f0 + round((f1 - f0) * t), (xy[0], xy[1], z))


def _flight(hero, f0: int, f1: int, arms_up: bool = True) -> None:
    for side in ("L", "R"):
        if arms_up:
            hero.raise_arm(f0, f0 + 4, side, hold=max(1, f1 - f0))
        else:
            hero.wave(f0, f1, side)


def _rise(root, f0: int, f1: int, z0: float, z1: float, xy=YOU) -> None:
    """Going up and slowing down (the top of a huge bounce is after f1)."""
    for i in range(9):
        t = i / 8
        key(root, "location", f0 + round((f1 - f0) * t), (xy[0], xy[1], z0 + (z1 - z0) * (1 - (1 - t) ** 1.6)))


def _neighbours(frame: int, look, n: int = 3) -> None:
    for i in range(n):
        x = -12 + 11 * i
        p = _hero((x, B.STREET_Y - 5.5, 0.18), math.pi / 2, frame)
        p.look_at(frame, look)
        if i == 1:
            p.raise_arm(frame + 10, frame + 18, "R", hold=60)


def build(spec: dict, ctx, scene, params: dict) -> None:
    stage = params.get("stage", "bed")
    stage = stage if stage in STAGES else "bed"
    f0, f1 = ctx.frame_start, ctx.frame_end
    fps = scene.render.fps or 24

    def at(fr: float) -> int:
        return f0 + int((f1 - f0) * fr)

    level = {"plane": "high", "clouds": "mid", "fall": "mid"}
    B._sky(scene, level.get(stage, "low"))
    B._ground(random.Random(B.SEED))
    B._house()
    if stage in ("clouds", "plane", "fall"):
        P.clouds("cl", (0, 0), 1400, 260, 300, 360, seed=SEED + 2)

    if stage in ("bed", "ceiling", "land"):
        room = P.bedroom("room", ROOM, seed=SEED)
        bed, lamp = room["bed"], room["lamp"]
        hero = _hero(bed, -math.pi / 2, f0)  # facing the camera
        root = hero.root
        cam_loc, aim = (ROOM.x + 2.4, ROOM.y - 2.3, 1.75), (bed.x + 0.3, bed.y, 1.3)
        if stage == "bed":
            hops = [(0.0, 0.32, 0.25), (0.32, 0.66, 0.4), (0.66, 1.0, 0.55)]
            for a, b, apex in hops:
                _arc(root, at(a), at(b), bed.xy, bed.z, bed.z + apex)
            hero.raise_arm(at(0.6), at(0.68), "R", hold=30)
            _camera(scene, cam_loc, aim, 20, f0, f1, 0.04)
        elif stage == "ceiling":
            hit = at(0.62)
            _arc(root, f0, at(0.3), bed.xy, bed.z, bed.z + 0.6)
            ceiling_root = room["size"][2] - 1.72  # the head touches the ceiling
            _arc(root, at(0.3), hit, bed.xy, bed.z, ceiling_root, ceiling_root)
            key(root, "location", f1, (bed.x, bed.y, bed.z + 0.05))
            _flight(hero, at(0.3), hit)
            for k, f in enumerate(range(hit, hit + 40, 5)):  # the lamp swings
                key(lamp, "rotation_euler", f, (0.35 * (0.8**k) * (-1) ** k, 0, 0))
            P._mesh_object(
                "crack", [(P.mat("crack", "#5b5148"), [((bed.x, bed.y, room["size"][2] - 0.03), (1.0, 0.9, 0.02))])]
            )
            P._appear(bpy.data.objects["crack"], hit)
            key(bpy.data.objects["crack"], "scale", hit, (1, 1, 1))
            _dust("plaster", (bed.x, bed.y, room["size"][2] - 0.2), hit, fps, 0.5, 8, SEED)
            cam = _camera(scene, cam_loc, aim, 20, f0, f1, 0.04)
            P.shake(cam, hit, fps, strength=0.12)
        else:  # land: straight down through the ceiling, into bed, and up again
            hit = at(0.42)
            hole = (bed.x, bed.y, room["size"][2] - 0.02)
            P._mesh_object(
                "ceiling_hole",
                [(P.mat("hole", "#1a1410", 1.0), [((bed.x, bed.y, room["size"][2] - 0.04), (1.3, 1.2, 0.03))])],
            )
            key(root, "location", f0, (bed.x, bed.y, 5.0))
            key(root, "location", hit, (bed.x, bed.y, bed.z - 0.12))
            key(root, "rotation_euler", f0, (0.6, 0, -math.pi / 2))
            key(root, "rotation_euler", hit, (0, 0, -math.pi / 2))
            _arc(root, hit, f1 + int(fps * 0.8), bed.xy, bed.z - 0.12, bed.z + 1.0)
            _flight(hero, f0, hit + 6, arms_up=False)
            bed_obj = bpy.data.objects["room_bed"]
            key(bed_obj, "scale", hit - 1, (1, 1, 1))
            key(bed_obj, "scale", hit + 2, (1.02, 1.02, 0.7))
            key(bed_obj, "scale", hit + 8, (1, 1, 1))
            _burst("plaster", hole, at(0.3), fps, "#f4efe6", n=14, up=(0, 1), out=(0.5, 1.5), seed=SEED + 4)
            _dust("landing", (bed.x, bed.y, bed.z + 0.2), hit, fps, 0.35, 8, SEED + 5)
            cam = _camera(scene, (ROOM.x + 2.4, ROOM.y - 2.3, 1.9), (bed.x + 0.2, bed.y, 1.6), 18, f0, f1, 0.03)
            P.shake(cam, hit, fps, strength=0.18)

    elif stage in ("hook", "roof"):
        burst = at(0.25 if stage == "hook" else 0.2)
        hole = _roof_hole(burst)
        hero = _hero(YOU + Vector((0, 0, 6.0)), math.pi / 2, f0)
        key(hero.root, "location", f0, tuple(YOU + Vector((0, 0, 6.0))))
        if stage == "hook":
            _rise(hero.root, burst - 2, f1 + int(fps * 0.5), hole.z - 1.0, 22)
            _neighbours(f0, (0, 0, 20))
            loc, target = (9, 10, 8.5), (0, 1.6, 13)  # beside the roof: you shoot up past it
        else:
            _arc(hero.root, burst - 2, f1 + int(fps * 0.6), YOU.xy, hole.z - 1.0, 20, hole.z - 1.0)
            loc, target = (-8, 10, 9), (0, 1.6, 14)
        _flight(hero, burst - 6, f1)
        _burst("tiles", hole, burst, fps, "#b03a2e", n=30, seed=SEED + 1)
        _dust("roofdust", hole, burst, fps, 2.0, 12, SEED + 3)
        cam = _camera(scene, loc, target, 18, f0, f1, 0.04)
        P.shake(cam, burst, fps, strength=0.2)

    elif stage == "street":
        hole = _roof_hole()
        hero = _hero(hole, math.pi / 2, f0)
        _rise(hero.root, f0, f1 + int(fps * 0.4), 24, 42)
        _flight(hero, f0, f1)
        _neighbours(f0, (0, 0, 35), 3)
        _camera(scene, (2, 4, 4), (0, -1, -8), 20, f0, f1, follow=hero.root)  # you, and the street far below

    elif stage == "town":
        _roof_hole()
        hero = _hero((0, 1.2, 60), math.pi / 2, f0)
        _rise(hero.root, f0, f1 + int(fps * 0.3), 60, 104)
        _flight(hero, f0, f1)
        _camera(scene, (3, 5, 6), (0, -1, -14), 22, f0, f1, follow=hero.root)

    elif stage == "clouds":
        hero = _hero((0, 1.2, 285), math.pi / 2, f0)
        _rise(hero.root, f0, f1, 285, 352)
        _flight(hero, f0, f1)
        _camera(scene, (7, -11, -1.5), (0, 0, 1.0), 22, f0, f1, follow=hero.root)

    elif stage == "plane":
        hero = _hero((0, 1.2, 896), math.pi / 2, f0)
        _arc(hero.root, f0, f1 + int(fps * 0.5), YOU.xy, 896, 903, 897)
        hero.raise_arm(f0, f0 + 4, "L", hold=f1 - f0)
        hero.wave(at(0.35), f1, "R")
        B._plane(at(0.05), f1 + int(fps * 0.4), 0, YOU.y + 22, 890)  # right under your feet
        _camera(scene, (-4, -9, 1.0), (1, 6, -3), 20, f0, f1, follow=hero.root)

    elif stage == "fall":
        hero = _hero((0, 1.2, 380), math.pi / 2, f0)
        key(hero.root, "location", f0, (0, 1.2, 380))
        key(hero.root, "location", f1, (0, 1.2, 250))
        for k, f in enumerate(range(f0, f1 + 1, 6)):  # tumbling
            key(hero.root, "rotation_euler", f, (0.9 * k, 0.3 * k, math.pi / 2))
        _flight(hero, f0, f1, arms_up=False)
        cam = _camera(scene, (3, -4.5, -2), (0, 0, 0.8), 20, f0, f1, follow=hero.root)
        P.shake(cam, f0 + 2, fps, strength=0.12, seconds=float(f1 - f0) / fps)

    if params.get("outlines") is False:
        scene.render.use_freestyle = False
