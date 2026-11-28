"""'¿Qué pasaría si tu ascensor no parara en el último piso?' (Nov 28; the owner: "haz lo que veas"). The reverse of
the channel's free-fall elevator video: ONE glass lift on ONE tower, going up and never stopping:

  you press 40 -> it climbs the outside of the tower -> floor 40... and it doesn't stop -> through the roof -> over the
  city -> through the clouds -> past a flock of birds -> the cable runs out -> it falls... straight back into the
  shaft, down to the ground floor. Doors open. "Planta baja."

params: stage (one of STAGES). The street and the city are the ramp video's (ramp.py), the sky the balloon
video's (balloons.py); the tower, the glass shaft and the lift are built here from parts.py.
"""

from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

from render_engines.core.blender.animation import key
from render_engines.custom import balloons as B
from render_engines.custom import parts as P
from render_engines.custom import ramp as R
from render_engines.custom.ramp import _camera, _hero

SEED = 2813
STAGES = ("hook", "button", "climb", "top", "roof", "city", "clouds", "birds", "fall", "ground")
TOWER = Vector((93.0, -33.0, 0.0))  # by the cross street, behind the street buildings
TOWER_H = 120.0  # 40 floors
SHAFT = Vector((TOWER.x, TOWER.y + 8.6, 0.0))  # the glass shaft on the tower's street side
CAB = (2.6, 2.6, 2.9)  # the lift's size
CABIN = Vector((4000.0, 0.0, 0.0))  # the inside of the lift, a set far from the city


def _tower() -> None:
    glass = P.mat("tw_glass", "#5f88a8", rough=0.15, metal=0.3)
    frame = P.mat("tw_frame", "#d7dde3", rough=0.5)
    bands = [((TOWER.x, TOWER.y, z), (16.2, 16.2, 0.35)) for z in range(3, int(TOWER_H), 3)]
    P._mesh_object(
        "tower",
        [
            (glass, [((TOWER.x, TOWER.y, 0), (16, 16, TOWER_H))]),
            (frame, bands + [((TOWER.x, TOWER.y, TOWER_H), (16.6, 16.6, 1.2))]),
            (P.mat("tw_roof", "#8d969e", 0.8), [((TOWER.x - 3, TOWER.y - 3, TOWER_H + 1.2), (5, 4, 3))]),
        ],
    )
    rails = [((SHAFT.x + sx * 1.6, SHAFT.y + 1.4, 0), (0.25, 0.25, TOWER_H + 1.2)) for sx in (-1, 1)]
    P._mesh_object("shaft", [(P.mat("rail", "#3a3f45", 0.4, metal=0.6), rails)])
    shaft_glass = P.clear_glass("shaft_glass", "#d7eef9")
    P._mesh_object("shaft_glass", [(shaft_glass, [((SHAFT.x, SHAFT.y + 1.6, 0), (3.6, 0.06, TOWER_H))])])


def _lift(with_you: bool = True):
    """The glass lift on a rig at its floor: frame, glass, roof with the cable drum, and you inside."""
    rig = P._empty("lift")
    frame = P.mat("lift_frame", "#f2c14e", rough=0.4, metal=0.3)
    glass = P.clear_glass("lift_glass")
    w, d, h = CAB
    body = P._mesh_object(
        "lift_body",
        [
            (frame, [((0, 0, 0), (w, d, 0.25)), ((0, 0, h), (w, d, 0.25))]
             + [((sx * w / 2, sy * d / 2, 0), (0.12, 0.12, h)) for sx in (-1, 1) for sy in (-1, 1)]),
            (glass, [((0, d / 2, 0.25), (w - 0.2, 0.04, h - 0.25)), ((w / 2, 0, 0.25), (0.04, d - 0.2, h - 0.25)),
                     ((-w / 2, 0, 0.25), (0.04, d - 0.2, h - 0.25))]),
            (P.mat("lift_back", "#c9a227", rough=0.5), [((0, -d / 2 + 0.05, 0.25), (w - 0.2, 0.08, h - 0.25))]),
        ],
    )  # fmt: skip
    body.parent = rig
    out = {"rig": rig}
    if with_you:
        you = _hero((0.3, -0.2, 0.25), math.pi / 2, 1)  # facing the street (+y), through the glass
        you.root.parent = rig
        out["you"] = you
    return out


def _ride(rig, f0: int, f1: int, z0: float, z1: float, ease: float = 1.0, xy=None) -> None:
    xy = xy or (SHAFT.x, SHAFT.y)
    for i in range(11):
        t = i / 10
        key(rig, "location", f0 + round((f1 - f0) * t), (xy[0], xy[1], z0 + (z1 - z0) * (t**ease)))


def _debris(name: str, at, frame: int, fps: int, colour: str, n: int = 24, seed: int = 0) -> None:
    rng = random.Random(seed)
    material = P.mat(f"{name}_bits", colour, rough=0.8)
    for i in range(n):
        bit = P._mesh_object(f"{name}{i}", [(material, [((0, 0, -0.5), (1, 1, 1))])])
        s = rng.uniform(0.2, 0.6)
        P._appear(bit, frame)
        key(bit, "scale", frame, (s, s, s * 0.4))
        a, up, out = rng.uniform(0, 2 * math.pi), rng.uniform(5, 14), rng.uniform(2, 7)
        for k in range(7):
            t = k / 6 * 2.2
            p = Vector(at) + Vector((math.cos(a) * out * t, math.sin(a) * out * t, up * t - 4.9 * t * t))
            key(bit, "location", frame + int(t * fps), tuple(p))
            key(bit, "rotation_euler", frame + int(t * fps), (t * 6, t * 4, 0))


def _birds(f0: int, f1: int, centre, n: int = 14, seed: int = 0) -> None:
    """A flock in a V, flapping, flying across."""
    rng = random.Random(seed)
    wing = P.mat("bird", "#2f3237", rough=0.7)
    for i in range(n):
        side = 1 if i % 2 else -1
        row = (i + 1) // 2
        b = P._mesh_object(
            f"bird{i}", [(wing, [((0, 0, 0), (0.5, 0.25, 0.2)), ((0, 0.55, 0.05), (0.3, 0.9, 0.05)),
                                 ((0, -0.55, 0.05), (0.3, 0.9, 0.05))])]
        )  # fmt: skip
        off = Vector((-row * 2.2, side * row * 2.0, rng.uniform(-0.6, 0.6)))
        start = Vector(centre) + Vector((-40, 6, 0)) + off
        key(b, "location", f0, tuple(start))
        key(b, "location", f1, tuple(start + Vector((80, -4, 2))))
        for k, f in enumerate(range(f0, f1 + 1, 3)):  # flapping
            key(b, "rotation_euler", f, (0.5 * (-1) ** k, 0, 0))


def _cabin_set(f0: int, f1: int, frame_press: int):
    """The inside of the lift: mirror, rail, a panel of floor buttons (40 lights up), you."""
    o = CABIN
    wall, rail = P.mat("cab_wall", "#d9c9a3", rough=0.6), P.mat("cab_rail", "#c0c6cc", rough=0.2, metal=0.8)
    mirror = P.mat("cab_mirror", "#9fb4c4", rough=0.02, metal=0.9)
    P._mesh_object(
        "cabin",
        [
            (P.mat("cab_floor", "#5b4a3a", 0.7), [((o.x, o.y, o.z - 0.1), (2.6, 2.6, 0.1))]),
            (wall, [((o.x, o.y + 1.35, o.z), (2.8, 0.1, 2.8)), ((o.x - 1.35, o.y, o.z), (0.1, 2.8, 2.8)),
                    ((o.x + 1.35, o.y, o.z), (0.1, 2.8, 2.8)), ((o.x, o.y, o.z + 2.8), (2.8, 2.8, 0.1))]),
            (mirror, [((o.x, o.y + 1.29, o.z + 0.9), (1.6, 0.02, 1.5))]),
            (rail, [((o.x, o.y + 1.2, o.z + 0.95), (2.4, 0.06, 0.06))]),
            (P.mat("cab_panel", "#2b2f33", 0.4), [((o.x + 1.29, o.y - 0.5, o.z + 0.9), (0.02, 0.5, 0.9))]),
        ],
    )  # fmt: skip
    lit = P.mat("button_on", "#ffb300", emit=6.0)
    off = P.mat("button_off", "#e8e8e8", rough=0.3)
    for r in range(5):
        for c in range(2):
            P._mesh_object(
                f"btn{r}{c}", [(off, [((o.x + 1.27, o.y - 0.62 + c * 0.24, o.z + 1.0 + r * 0.16), (0.02, 0.1, 0.1))])]
            )
            if r == 4 and c == 1:  # the top button: 40
                on = P._mesh_object("btn40", [(lit, [((o.x + 1.26, o.y - 0.38, o.z + 1.64), (0.025, 0.11, 0.11))])])
                P._appear(on, frame_press)
                key(on, "scale", frame_press, (1, 1, 1))
    light = bpy.data.objects.new("cab_light", bpy.data.lights.new("cab_light", "AREA"))
    light.data.energy, light.data.size = 120, 1.8
    light.location = (o.x, o.y, o.z + 2.7)
    bpy.context.scene.collection.objects.link(light)
    you = _hero((o.x - 0.2, o.y + 0.1, o.z), 0.0, f0)  # facing the panel (+x)
    you.reach(frame_press - 8, frame_press, "R", hold=10)
    return you


def build(spec: dict, ctx, scene, params: dict) -> None:
    stage = params.get("stage", "button")
    stage = stage if stage in STAGES else "button"
    f0, f1 = ctx.frame_start, ctx.frame_end
    fps = scene.render.fps or 24

    def at(fr: float) -> int:
        return f0 + int((f1 - f0) * fr)

    level = {"city": "mid", "clouds": "mid", "birds": "high", "fall": "mid", "hook": "low"}
    B._sky(scene, level.get(stage, "low"))
    R._streets()
    R._city(random.Random(R.SEED))
    _tower()

    if stage == "button":
        you = _cabin_set(f0, f1, at(0.45))
        _camera(scene, (CABIN.x - 1.1, CABIN.y - 1.15, 1.75), (CABIN.x + 1.2, CABIN.y - 0.3, 1.25), 16, f0, f1, 0.03)
        you.look_at(at(0.2), (CABIN.x + 1.3, CABIN.y - 0.4, 1.6))
        return _end(scene, params)

    lift = _lift()
    rig = lift["rig"]
    roof_z = TOWER_H + 1.2

    if stage == "climb":  # up the outside of the tower, floors flashing past
        _ride(rig, f0, f1, 6.0, 78.0, ease=1.2)
        _camera(scene, (6, 7, 1.0), (0, -2, 1.6), 22, f0, f1, follow=rig)

    elif stage == "top":  # floor 40... and it doesn't stop
        _ride(rig, f0, f1 + int(fps * 0.4), TOWER_H - 22, TOWER_H + 6, ease=1.0)
        cam = (SHAFT.x + 16, SHAFT.y + 18, TOWER_H - 2)
        _camera(scene, cam, (SHAFT.x, SHAFT.y, TOWER_H - 1), 22, f0, f1, 0.03)

    elif stage in ("roof", "hook"):  # through the top of the shaft and out into the sky
        hit = at(0.25 if stage == "roof" else 0.1)
        _ride(rig, f0, f1 + int(fps * 0.3), roof_z - 8, roof_z + (24 if stage == "roof" else 40), ease=1.0)
        _debris("roofbits", (SHAFT.x, SHAFT.y, roof_z + 0.5), hit, fps, "#8d969e", 26, SEED)
        lift["you"].raise_arm(hit, hit + 5, "L", hold=50)
        lift["you"].raise_arm(hit, hit + 5, "R", hold=50)
        if stage == "roof":
            cam = _camera(scene, (SHAFT.x + 12, SHAFT.y + 12, roof_z + 8), (SHAFT.x, SHAFT.y, roof_z + 9), 22, f0, f1)
        else:
            cam = _camera(scene, (7, 10, 1.0), (0, 0, 1.2), 20, f0, f1, follow=rig)  # level with you, through the glass
        P.shake(cam, hit, fps, strength=0.2)

    elif stage == "city":  # over the whole city
        _ride(rig, f0, f1, 160, 230)
        _camera(scene, (5, 8, 4), (0, -1, -12), 22, f0, f1, follow=rig)

    elif stage == "clouds":
        P.clouds("cl", (SHAFT.x, SHAFT.y), 900, 200, 300, 360, seed=SEED + 2)
        _ride(rig, f0, f1, 285, 372)
        _camera(scene, (5, 7, -1), (0, 0, 1.5), 22, f0, f1, follow=rig)

    elif stage == "birds":  # higher than the birds
        P.clouds("cl", (SHAFT.x, SHAFT.y), 900, 200, 300, 360, seed=SEED + 2)
        _ride(rig, f0, f1, 520, 560)
        _birds(f0, f1, (SHAFT.x, SHAFT.y + 6, 538), 14, SEED + 3)
        _camera(scene, (6, 9, 0.5), (0, 0, 1.5), 22, f0, f1, follow=rig)

    elif stage == "fall":  # the cable runs out... and down it goes
        P.clouds("cl", (SHAFT.x, SHAFT.y), 900, 200, 300, 360, seed=SEED + 2)
        snap = at(0.25)
        _ride(rig, f0, snap, 566, 570)
        _ride(rig, snap, f1 + int(fps * 0.4), 570, 300, ease=2.0)
        for k, f in enumerate(range(snap, f1 + 1, 6)):  # it tumbles a little
            key(rig, "rotation_euler", f, (0.12 * math.sin(k), 0.1 * math.cos(k * 1.3), 0.2 * k))
        for side in ("L", "R"):
            lift["you"].raise_arm(snap, snap + 4, side, hold=f1 - snap)
        cam = _camera(scene, (6, 9, -4), (0, 0, 1.0), 22, f0, f1, follow=rig)
        P.shake(cam, snap, fps, strength=0.15, seconds=float(f1 - snap) / fps)

    elif stage == "ground":  # straight back into the shaft, down to the ground floor: ding
        stop = at(0.45)
        _ride(rig, f0, stop, 40, 0.3, ease=0.6)
        key(rig, "location", stop + 4, (SHAFT.x, SHAFT.y, 0.15))
        key(rig, "location", stop + 9, (SHAFT.x, SHAFT.y, 0.3))
        doors = [
            P._mesh_object(f"door{s}", [(P.mat("lift_frame", "#f2c14e"), [((0, 0, 0), (1.25, 0.1, 2.6))])])
            for s in (-1, 1)
        ]
        for s, door in zip((-1, 1), doors, strict=True):  # the doors slide open on the street side
            door.parent = rig
            key(door, "location", stop + 10, (s * 0.65, CAB[1] / 2 + 0.06, 0.25))
            key(door, "location", stop + 22, (s * 1.85, CAB[1] / 2 + 0.06, 0.25))
        lift["you"].wave(stop + 24, f1, "R")
        _camera(scene, (SHAFT.x + 2, SHAFT.y + 9, 1.8), (SHAFT.x, SHAFT.y, 1.6), 22, f0, f1, 0.04)  # from the street

    return _end(scene, params)


def _end(scene, params: dict) -> None:
    if params.get("outlines") is False:
        scene.render.use_freestyle = False
