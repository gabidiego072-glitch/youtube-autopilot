"""'What if you filled your house with BOUNCY BALLS?' (Nov 27, the owner: hypothetical ideas like the ramp, a
different one on each channel). ONE room, ONE house, ONE street, and the balls go where the last scene left them:

  one bag -> knee deep -> full to the ceiling -> the windows give way -> the street -> a river of balls down the road
  -> the whole neighbourhood is a ball pit -> the lake -> one ball bounces all the way back home (loops to the start).

params: stage (one of STAGES). The town, the house and the sky are the balloon video's (balloons.py), the bedroom
is parts.bedroom(); thousands of balls are batched with parts.ball_batch().
"""

from __future__ import annotations

import math
import random

from mathutils import Vector

from render_engines.core.blender.animation import key
from render_engines.custom import balloons as B
from render_engines.custom import parts as P
from render_engines.custom.ramp import _camera, _hero

SEED = 2712
STAGES = ("hook", "bag", "knees", "ceiling", "burst", "street", "river", "town", "lake", "home")
ROOM = Vector((3000.0, 0.0, 0.0))  # the bedroom set, far from the town
TOYS = ["#ff3b30", "#ffcc00", "#34c759", "#0a84ff", "#af52de", "#ff9500", "#ff2d92"]
FRONT_Y = B.D / 2  # the front wall of your house (it faces the street, +y)
RIVER_Y = 60.0  # the next street up (y = 60): the balls run along it toward the lake
SHORE = Vector((B.LAKE.x, B.LAKE.y - 38.0, 0.0))  # the south shore of the lake, where the balls pour in
NEAR, FAR = 2, 1  # ico subdivisions: 80-face round balls near the cameras, 20-face ones far away (memory)


def _grid(x0, x1, y0, y1, z0, z1, step, rng, jitter=0.25):
    pts, z = [], z0
    while z <= z1:
        x = x0
        while x <= x1:
            y = y0
            while y <= y1:
                pts.append((x + rng.uniform(-jitter, jitter), y + rng.uniform(-jitter, jitter), z))
                y += step
            x += step
        z += step * 0.82
    return pts


def _rise(objs, frame: int, depth: float, frames: int = 10) -> None:
    """A layer of balls rises into place from below (hidden under the floor or the street) on `frame`."""
    for obj in objs:
        key(obj, "location", frame - 1, (0, 0, -depth))
        key(obj, "location", frame + frames, (0, 0, 0))


def _pile(name, area, top, radius, rng, start, end, seed, sub=NEAR, step=None):
    """A heap that fills `area` (x0, x1, y0, y1) from the ground up to `top` between two frames, layer by layer."""
    step = step or radius * 2.0
    layers, z = [], radius
    while z <= top:
        layers.append(z)
        z += step * 0.82
    for k, z in enumerate(layers):
        pts = _grid(area[0], area[1], area[2], area[3], z, z, step, rng)
        objs = P.ball_batch(f"{name}{k}_", pts, radius, TOYS, seed=seed + k, subdivisions=sub)
        if start is not None:
            _rise(objs, start + round((end - start) * k / max(1, len(layers))), z + radius + 0.3)
    return layers


def _bouncer(name: str, start, direction, frame: int, fps: int, hops: int = 4, height: float = 1.2, reach: float = 3.0,
             radius: float = 0.3, colour: int = 0):  # fmt: skip
    """One ball that bounces away from `start` along `direction`, each hop lower (a real superball)."""
    ball = P.instance(name, P.ball_mesh("toyball", 1.0, 1.0), P.mat(f"toyball{colour}", TOYS[colour], rough=0.3),
                      start, radius)  # fmt: skip
    p, f, h, d = Vector(start), frame, height, reach
    dirn = Vector(direction).normalized()
    key(ball, "location", f, tuple(p))
    for _ in range(hops):
        t = math.sqrt(8 * h / 9.81)  # time of one hop of height h
        mid = p + dirn * d / 2
        key(ball, "location", f + int(t * fps / 2), (mid.x, mid.y, p.z + h))
        p = p + dirn * d
        f += max(2, int(t * fps))
        key(ball, "location", f, tuple(p))
        h *= 0.65
        d *= 0.75
    return ball


def _road(rng, start, end, near=(-15.0, 25.0)) -> None:
    """Your street full of balls: two layers of round ones by the camera, one cheap layer further away."""
    y0, y1 = B.STREET_Y - 9, B.STREET_Y + 9
    _pile("road_near", (near[0], near[1], y0, y1), 1.2, 0.45, rng, start, end, SEED + 150, sub=NEAR)
    for k, (x0, x1) in enumerate(((-210, near[0] - 0.9), (near[1] + 0.9, 210))):
        _pile(f"road_far{k}", (x0, x1, y0, y1), 0.5, 0.45, rng, start, end, SEED + 160 + 10 * k, sub=FAR)


def _road_from_above(rng) -> None:
    _pile("road", (-210, 210, B.STREET_Y - 9, B.STREET_Y + 9), 0.9, 0.9, rng, None, None, SEED + 150, sub=FAR)


def _lawn(rng, start, end) -> None:
    _pile("lawn", (-7, 7, FRONT_Y + 1, FRONT_Y + 9), 1.4, 0.35, rng, start, end, SEED + 100, sub=NEAR)


def _carpet(rng, start: int | None, end: int | None) -> None:
    """The whole neighbourhood under one layer of big balls (houses stick out), spreading north band by band."""
    bands = 6
    x0, x1, y0, y1, r = -150.0, 200.0, 27.0, 250.0, 1.2
    for k in range(bands):
        ya, yb = y0 + (y1 - y0) * k / bands, y0 + (y1 - y0) * (k + 1) / bands
        pts = [
            p
            for p in _grid(x0, x1, ya, yb, r, r, 2.4, rng, jitter=0.5)
            if not (B.LAKE.x - 50 < p[0] < B.LAKE.x + 50 and B.LAKE.y - 40 < p[1] < B.LAKE.y + 40)
        ]
        objs = P.ball_batch(f"carpet{k}_", pts, r, TOYS, seed=SEED + 600 + k, subdivisions=FAR)
        if start is not None:
            _rise(objs, start + round((end - start) * k / bands), 2 * r + 0.3, frames=12)


def _river(rng, start: int | None = None, end: int | None = None) -> None:
    """Up the gap between two houses (x ~ 63) to the next street, then along it toward the lake."""
    run = (59.5, 66.5, B.STREET_Y + 9, RIVER_Y - 3)
    lane = (59.5, SHORE.x + 10, RIVER_Y - 3, RIVER_Y + 3)
    if start is None:
        _pile("run", run, 0.9, 0.6, rng, None, None, SEED + 200, sub=FAR)
        _pile("lane", lane, 0.9, 0.6, rng, None, None, SEED + 300, sub=FAR)
        return
    _pile("run", run, 0.9, 0.6, rng, start, start + (end - start) // 3, SEED + 200, sub=FAR)
    segments = 8
    for k in range(segments):  # the front rolls on toward the lake
        xa = lane[0] + (lane[1] - lane[0]) * k / segments
        xb = lane[0] + (lane[1] - lane[0]) * (k + 1) / segments
        fa = start + (end - start) // 3 + (end - start) * 2 // 3 * k // segments
        _pile(f"lane{k}", (xa, xb, lane[2], lane[3]), 0.9, 0.6, rng, fa, fa + 6, SEED + 300 + 10 * k, sub=FAR)


def _street_cars(rng) -> None:
    cols = ["#d63a2f", "#2f7fd6", "#ecf0f1", "#2ecc71"]
    for i, x in enumerate((-26, 14, 34, -48)):
        P.car(f"parked{i}", (x, B.STREET_Y - 2.2, 0), 0.0, "sedan", cols[i])


def build(spec: dict, ctx, scene, params: dict) -> None:
    stage = params.get("stage", "bag")
    stage = stage if stage in STAGES else "bag"
    f0, f1 = ctx.frame_start, ctx.frame_end
    fps = scene.render.fps or 24
    rng = random.Random(SEED + STAGES.index(stage))

    def at(fr: float) -> int:
        return f0 + int((f1 - f0) * fr)

    B._sky(scene, "low")
    B._ground(random.Random(B.SEED))
    B._house()

    if stage in ("bag", "knees", "ceiling"):
        P.bedroom("room", ROOM, seed=SEED)
        floor = (ROOM.x - 2.7, ROOM.x + 2.7, ROOM.y - 1.4, ROOM.y + 2.3)
        cam_loc, aim = (ROOM.x + 2.4, ROOM.y - 2.3, 1.75), (ROOM.x - 0.2, ROOM.y + 0.6, 1.1)
        if stage == "bag":
            hero = _hero((ROOM.x + 0.2, ROOM.y + 0.2, 0), -math.pi / 2, f0)
            hero.raise_arm(f0, f0 + 6, "R", hold=20)
            for i in range(26):  # the first bag: balls everywhere
                a = rng.uniform(0, 2 * math.pi)
                _bouncer(f"b{i}", (ROOM.x + 0.5, ROOM.y + 0.1, 1.3), (math.cos(a), math.sin(a), 0),
                         f0 + 8 + i // 2, fps, hops=4, height=rng.uniform(0.8, 1.6), reach=rng.uniform(0.6, 1.2),
                         radius=0.09, colour=i % len(TOYS))  # fmt: skip
            _camera(scene, cam_loc, aim, 20, f0, f1, 0.04)
        elif stage == "knees":
            hero = _hero((ROOM.x + 0.2, ROOM.y + 0.2, 0), -math.pi / 2, f0)
            hero.raise_arm(at(0.4), at(0.5), "L", hold=40)
            _pile("knee", floor, 0.55, 0.12, rng, f0, at(0.7), SEED)
            _camera(scene, cam_loc, aim, 20, f0, f1, 0.04)
        else:  # full to the ceiling: you rise with the balls until only your arms stick out
            _pile("low", floor, 0.55, 0.12, rng, None, None, SEED)
            _pile("high", floor, 2.7, 0.16, rng, f0, at(0.85), SEED + 50)
            hero = _hero((ROOM.x + 0.2, ROOM.y + 0.2, 0.4), -math.pi / 2, f0)
            key(hero.root, "location", f0, (ROOM.x + 0.2, ROOM.y + 0.2, 0.4))
            key(hero.root, "location", at(0.85), (ROOM.x + 0.2, ROOM.y + 0.2, 1.3))
            for side in ("L", "R"):
                hero.raise_arm(at(0.2), at(0.3), side, hold=f1 - f0)
            _camera(scene, (ROOM.x + 2.4, ROOM.y - 2.35, 2.1), (ROOM.x - 0.2, ROOM.y + 0.6, 1.6), 18, f0, f1, 0.03)

    elif stage in ("burst", "hook"):
        hit = at(0.2 if stage == "burst" else 0.05)
        glass = P.mat("bld_glass", "#33475c", rough=0.2)
        for dx in (-3.6, 3.6):  # the windows give way: glass flies out
            for i in range(10):
                shard = P._mesh_object(f"shard{dx}_{i}", [(glass, [((0, 0, 0), (0.4, 0.06, 0.3))])])
                a = rng.uniform(-0.6, 0.6)
                key(shard, "location", hit, (dx + rng.uniform(-1, 1), FRONT_Y + 0.1, 2.4 + rng.uniform(-0.8, 0.8)))
                key(shard, "location", hit + 14, (dx + 6 * a, FRONT_Y + rng.uniform(3, 6), 0.1))
                key(shard, "rotation_euler", hit + 14, (rng.uniform(2, 6), rng.uniform(2, 6), 0))
        for i in range(140):  # streams of balls out of both windows and the door, falling onto the lawn
            src = (rng.choice((-3.6, 3.6, 0.0)), FRONT_Y + 0.3, 2.6 if i % 3 else 1.2)
            out = Vector((rng.uniform(-0.5, 0.5), 1, 0))
            _bouncer(f"out{i}", src, out, hit + i // 4, fps, hops=3, height=rng.uniform(0.6, 1.6),
                     reach=rng.uniform(2.5, 5.0), radius=0.25, colour=i % len(TOYS))  # fmt: skip
        _lawn(rng, hit + 10, f1)
        if stage == "hook":  # ...and already up to the cars on the street
            _street_cars(rng)
            _road(rng, f0, at(0.6))
        for x in (-12, 10):
            _hero((x, B.STREET_Y + 5.5, 0.18), -math.pi / 2, f0).look_at(f0, (0, 0, 3))
        _camera(scene, (9, B.STREET_Y + 4, 3.5), (0, 2, 2.6), 20, f0, f1, 0.05)

    elif stage == "street":
        _street_cars(rng)
        _lawn(rng, None, None)
        _road(rng, f0, at(0.8), near=(-36.0, 4.0))
        for x in (-22, 2):
            n = _hero((x, B.STREET_Y + 5.5, 0.6), -math.pi / 2, f0)
            for side in ("L", "R"):
                n.raise_arm(at(0.3), at(0.4), side, hold=40)
        _camera(scene, (-40, B.STREET_Y + 2, 7), (10, B.STREET_Y - 2, 0.5), 22, f0, f1, 0.05)

    elif stage == "river":
        _road_from_above(rng)
        _river(rng, f0, at(0.9))
        front = P._empty("front", (63, B.STREET_Y + 10, 0))
        key(front, "location", f0, (63, B.STREET_Y + 10, 0))
        key(front, "location", at(0.3), (63, RIVER_Y, 0))
        key(front, "location", at(0.9), (SHORE.x, RIVER_Y, 0))
        _camera(scene, (-30, -38, 30), (12, 10, 0), 22, f0, f1, follow=front)

    elif stage == "town":
        _road_from_above(rng)
        _river(rng)
        _carpet(rng, f0, at(0.75))
        _camera(scene, (-30, -70, 120), (60, 140, 0), 22, f0, f1, 0.06)

    elif stage == "lake":  # the wave of balls pours into the lake from its south shore
        _carpet(rng, None, None)
        hit = at(0.3)
        _pile("shore", (SHORE.x - 40, SHORE.x + 40, SHORE.y - 24, SHORE.y - 2), 1.4, 0.6, rng, f0, hit, SEED + 500,
              sub=FAR)  # fmt: skip
        water = P._soft("splash", "#d6eefc")
        for i in range(16):  # a ring of spray where the balls hit the water (the balls stay the show)
            a = i / 16 * math.pi
            p = P._sphere(f"sp{i}", 0.8, water, tuple(SHORE + Vector((0, 4, 0))))
            p.visible_shadow = False
            P._appear(p, hit)
            key(p, "scale", hit, (1.0, 1.0, 1.0))
            key(p, "location", hit, tuple(SHORE + Vector((math.cos(a) * 20, 4 + math.sin(a) * 3, 0.5))))
            key(p, "location", hit + int(fps * 0.8),
                tuple(SHORE + Vector((math.cos(a) * 26, 10 + 8 * math.sin(a), rng.uniform(8, 18)))))  # fmt: skip
            key(p, "scale", hit + int(fps * 0.8), (1.8, 1.8, 1.8))
            key(p, "scale", hit + int(fps * 1.4), (0.001, 0.001, 0.001))
        for i in range(160):  # and the balls fly out over the water
            a = rng.uniform(-0.8, 0.8)
            _bouncer(f"lb{i}", tuple(SHORE + Vector((rng.uniform(-30, 30), -1, 1.0))), (math.sin(a), math.cos(a), 0),
                     hit + i // 6, fps, hops=2, height=rng.uniform(4, 12), reach=rng.uniform(8, 22), radius=0.5,
                     colour=i % len(TOYS))  # fmt: skip
        cam = _camera(scene, (SHORE.x + 16, SHORE.y + 34, 7), (SHORE.x, SHORE.y, 4), 22, f0, f1, 0.05)  # over the water
        P.shake(cam, hit, fps, strength=0.25)

    elif stage == "home":
        # one last ball bounces all the way back up the street and in through your window
        _street_cars(rng)
        _road(rng, None, None)
        _lawn(rng, None, None)
        ball = P.instance("last", P.ball_mesh("toyball", 1.0, 1.0), P.mat("toyball3", TOYS[3], rough=0.3),
                          (60, B.STREET_Y, 1.6), 0.45)  # fmt: skip
        path = [
            Vector(p)
            for p in ((60, B.STREET_Y, 1.6), (38, B.STREET_Y, 1.6), (20, B.STREET_Y - 1, 1.6), (8, B.STREET_Y - 4, 1.6),
                      (3.6, FRONT_Y + 4, 1.5), (3.6, FRONT_Y - 0.5, 2.6))
        ]  # fmt: skip
        f = f0
        for a, b in zip(path, path[1:], strict=False):
            span = max(8, int((b - a).length * 0.9))
            mid = a.lerp(b, 0.5)
            key(ball, "location", f, tuple(a))
            key(ball, "location", f + span // 2, (mid.x, mid.y, max(a.z, b.z) + 2.0 + 0.1 * (b - a).length))
            f += span
            key(ball, "location", f, tuple(b))
        _camera(scene, (6, B.STREET_Y - 2, 7), (3, FRONT_Y - 1, 2.5), 20, f0, f1, 0.04)

    if params.get("outlines") is False:
        scene.render.use_freestyle = False
