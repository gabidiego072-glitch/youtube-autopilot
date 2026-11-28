"""'¿Qué pasaría si le pusieras RUEDAS a tu casa?' (Nov 28, the owner: "haz lo que veas"; hypothetical ideas like the
ramp, a different one on each channel). ONE house on ONE hill, ONE trip down to school, each part caused by the last:

  your house is on top of the hill, school is at the bottom -> four giant wheels -> the brake comes off -> down the
  hill, faster and faster -> through the park -> across the road -> it floats across the river -> through the town
  -> it stops right at the school door. On time.

params: stage (one of STAGES). The hill, the park, the road, the river, the town and the school are the zipline
video's (zipline.py); the house on wheels is built here from render_engines/custom/parts.py.
"""

from __future__ import annotations

import math
import random

import bmesh
import bpy

from render_engines.core.blender.animation import key
from render_engines.custom import parts as P
from render_engines.custom import zipline as Z
from render_engines.custom.ramp import _camera, _hero

SEED = 2811
STAGES = ("hook", "top", "wheels", "roll", "hill", "park", "road", "river", "town", "school")
WHEEL_R = 2.0
LIFT = WHEEL_R + 0.3  # from the ground to the floor of the house
WATER_Z = -0.07
STOP_X = Z.SCHOOL_X - 8.0  # the front wall stops right at the school door


def ground_z(x: float) -> float:
    """The ground under the path (y = 0): the round hill around x = 0, flat everywhere else."""
    r = abs(x)
    if r < 80:
        return max(0.0, (Z.HILL_TOP - 60 * 0.36) + 60 * 0.36 * math.sqrt(max(0.0, 1 - (r / 80) ** 2)))
    return 0.0


def _cylinder(name: str, radius: float, depth: float, material, segments: int = 20):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=radius, radius2=radius, depth=depth)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _house(wheels: bool = True):
    """Your house on a rig at its floor centre: walls, roof, windows, door, porch, chimney and (optional) wheels.
    Returns (rig, [wheel objects])."""
    rig = P._empty("home")
    wall, roof = P.mat("wh_wall", "#f6e7cf", rough=0.9), P.mat("wh_roof", "#2f6db5", rough=0.8)
    glass, door = P.mat("bld_glass", "#33475c", rough=0.2), P.mat("bld_door", "#3b2a1e")
    body = P._mesh_object(
        "wh_house",
        [
            (wall, [((0, 0, 0), (12, 10, 6.5))]),
            (glass, [((dx, 5.06, 3.2), (2.4, 0.12, 2.0)) for dx in (-3.6, 3.6)]
             + [((6.06, dy, 3.2), (0.12, 2.4, 2.0)) for dy in (-2.4, 2.4)]),
            (door, [((0, 5.07, 0), (1.8, 0.14, 3.0))]),
            (P.mat("wh_trim", "#ffffff", rough=0.7), [((0, 6.4, 0), (5.0, 2.6, 0.35))]),
            (P.mat("house_brick", "#8e4b32"), [((3.0, -1.6, 6.5), (1.4, 1.4, 5.0))]),
            (P.mat("wh_base", "#6d5a44", 1.0), [((0, 0, -0.5), (12.6, 10.6, 0.5))]),
        ],
    )  # fmt: skip
    body.parent = rig
    verts = [(-6.6, -5.6, 6.5), (6.6, -5.6, 6.5), (6.6, 5.6, 6.5), (-6.6, 5.6, 6.5), (-6.6, 0, 10.5), (6.6, 0, 10.5)]
    mesh = bpy.data.meshes.new("wh_roof")
    mesh.from_pydata(verts, [], [(0, 1, 5, 4), (3, 4, 5, 2), (0, 4, 3), (1, 2, 5), (0, 3, 2, 1)])
    mesh.materials.append(roof)
    r = bpy.data.objects.new("wh_roof", mesh)
    bpy.context.scene.collection.objects.link(r)
    r.parent = rig
    out = []
    if wheels:
        tyre, hub = P.mat("tyre", "#1d1d1f", rough=0.8), P.mat("hub", "#c9ced6", rough=0.3, metal=0.6)
        for i, (x, y) in enumerate(((-4.2, -5.9), (4.2, -5.9), (-4.2, 5.9), (4.2, 5.9))):
            w = _cylinder(f"wheel{i}", WHEEL_R, 1.0, tyre)
            h = _cylinder(f"hub{i}", WHEEL_R * 0.45, 1.06, hub, 12)
            h.parent = w
            for s in (-1, 1):  # spokes, so the turning shows
                sp = P._mesh_object(f"spoke{i}{s}", [(hub, [((0, 0, -WHEEL_R * 0.85), (0.3, 1.08, WHEEL_R * 1.7))])])
                sp.parent = w
                sp.rotation_euler = (0, math.pi / 4 * (2 + s), 0)
            w.rotation_euler = (math.pi / 2, 0, 0)  # axle along y
            w.location = (x, y, -LIFT + WHEEL_R)
            w.parent = rig
            out.append(w)
    return rig, out


def _drive(rig, wheels, frames, xs, floating=False) -> None:
    """Move the house along y = 0 through the x positions at those frames, on the ground (or the water), wheels
    turning with the distance and the house pitching with the slope."""
    for f, x in zip(frames, xs, strict=True):
        z = (WATER_Z - 1.2) if floating else ground_z(x)
        dz = ground_z(x + 4.0) - ground_z(x - 4.0)  # the slope under the whole house, not one point
        pitch = 0.0 if floating else max(-0.5, min(0.5, math.atan2(-dz, 8.0)))
        key(rig, "location", f, (x, 0.0, z + LIFT))
        key(rig, "rotation_euler", f, (0.0, pitch, 0.0))
        for w in wheels:
            key(w, "rotation_euler", f, (math.pi / 2, x / WHEEL_R, 0))


def _path(f0: int, f1: int, x0: float, x1: float, ease: float = 1.0, n: int = 12):
    """n+1 (frame, x) pairs from x0 to x1; ease > 1 speeds up, < 1 slows down."""
    frames, xs = [], []
    for i in range(n + 1):
        t = i / n
        frames.append(f0 + round((f1 - f0) * t))
        xs.append(x0 + (x1 - x0) * (t**ease))
    return frames, xs


def _you(rig, frame: int, wave: bool = False):
    """You, on the porch, riding with the house."""
    hero = _hero((2.0, 6.6, 0.35), math.pi / 2, frame)
    hero.root.parent = rig
    if wave:
        hero.wave(frame + 4, frame + 60, "R")
    return hero


def _dust(rig_x: float, frame: int, fps: int, seed: int) -> None:
    rng = random.Random(seed)
    soft = P._soft("roll_dust", "#e2d6bf")
    for i in range(8):
        x = rig_x + rng.uniform(-6, 6)
        p = P._sphere(f"rd{seed}_{i}", 0.6, soft, (x, rng.choice((-6.5, 6.5)), ground_z(x) + 0.4))
        p.visible_shadow = False
        P._appear(p, frame + i)
        key(p, "scale", frame + i, (0.4, 0.4, 0.4))
        key(p, "scale", frame + i + int(fps * 0.9), (2.0, 2.0, 1.4))
        key(p, "scale", frame + i + int(fps * 0.9) + 1, (0.001, 0.001, 0.001))


def build(spec: dict, ctx, scene, params: dict) -> None:
    stage = params.get("stage", "top")
    stage = stage if stage in STAGES else "top"
    f0, f1 = ctx.frame_start, ctx.frame_end
    fps = scene.render.fps or 24
    rng = random.Random(SEED + STAGES.index(stage))

    def at(fr: float) -> int:
        return f0 + int((f1 - f0) * fr)

    Z._sky(scene)
    Z._town(random.Random(Z.SEED))
    Z._hill()
    Z._school()
    rig, wheels = _house(wheels=stage != "top")

    if stage == "top":  # your house on the hill, the school far away down there
        key(rig, "location", f0, (0, 0, ground_z(0) + 0.5))  # no wheels yet: on its foundations
        hero = _hero((8.0, -7.5, ground_z(10.6) + 0.05), 0.0, f0)
        hero.look_at(f0, (Z.SCHOOL_X, 0, 8))
        hero.raise_arm(at(0.35), at(0.45), "R", hold=50)
        _camera(scene, (-30, -10, Z.HILL_TOP + 14), (60, 2, 6), 22, f0, f1, 0.05)  # behind it: the town below

    elif stage == "wheels":  # four giant wheels appear, one after the other
        key(rig, "location", f0, (0, 0, ground_z(0) + 0.5))
        key(rig, "location", at(0.2), (0, 0, ground_z(0) + 0.5))
        key(rig, "location", at(0.8), (0, 0, ground_z(0) + LIFT))  # the wheels lift it off its foundations
        for i, w in enumerate(wheels):
            s = at(0.12 + 0.17 * i)
            key(w, "scale", s - 1, (0.001, 0.001, 0.001))
            key(w, "scale", s + 6, (1.15, 1.15, 1.15))
            key(w, "scale", s + 10, (1, 1, 1))
        _you(rig, f0).raise_arm(at(0.75), at(0.85), "R", hold=30)
        _camera(scene, (22, -26, Z.HILL_TOP + 7), (0, 0, Z.HILL_TOP + 4), 22, f0, f1, 0.05)

    elif stage == "roll":  # the brake comes off: it creaks, then starts rolling
        frames, xs = _path(at(0.3), f1 + int(fps * 0.3), 0.0, 16.0, ease=2.2)
        _drive(rig, wheels, [f0] + frames, [0.0] + xs)
        _you(rig, f0).raise_arm(at(0.25), at(0.35), "L", hold=40)
        _dust(4.0, at(0.35), fps, SEED)
        _camera(scene, (24, -24, Z.HILL_TOP + 3), (6, 0, Z.HILL_TOP + 3), 22, f0, f1, 0.04)

    elif stage in ("hill", "hook"):  # down the hill, faster every second
        x0, x1 = (16.0, 82.0) if stage == "hill" else (34.0, 92.0)
        frames, xs = _path(f0, f1, x0, x1, ease=1.5)
        _drive(rig, wheels, frames, xs)
        _you(rig, f0, wave=stage == "hook")
        _dust(x0 + 10, f0 + 6, fps, SEED + 1)
        if stage == "hook":
            cam = _camera(scene, (86, -22, 5.5), (44, 0, 14), 20, f0, f1, 0.02)  # at the foot of the hill
        else:
            cam = _camera(scene, (-12, -30, 9), (8, 0, 1), 22, f0, f1, follow=rig)
        P.shake(cam, f0 + 4, fps, strength=0.06, seconds=float(f1 - f0) / fps)

    elif stage == "park":  # through the park; people jump out of the way
        frames, xs = _path(f0, f1, 92.0, 230.0)
        _drive(rig, wheels, frames, xs)
        _you(rig, f0)
        for i, x in enumerate((140, 170, 205)):
            p = _hero((x, 9.0 * (1 if i % 2 else -1), 0.18), math.pi / 2, f0)
            p.look_at(f0, (x - 40, 0, 4))
            p.raise_arm(at(0.25 + 0.2 * i), at(0.32 + 0.2 * i), "R", hold=30)
        _camera(scene, (-16, -20, 16), (8, 0, 2), 22, f0, f1, follow=rig)

    elif stage == "road":  # across the road; the cars brake hard
        frames, xs = _path(f0, f1, 285.0, 352.0)
        _drive(rig, wheels, frames, xs)
        _you(rig, f0)
        cross = at(0.5)
        cols = ["#d63a2f", "#ecf0f1", "#2ecc71", "#f6c21a"]
        for i, (y, lane) in enumerate(((-60, -3.0), (-35, -3.0), (55, 3.0), (32, 3.0))):
            yaw = math.pi / 2 if lane < 0 else -math.pi / 2
            c = P.car(f"rc{i}", (Z.ROAD_X + lane, y, 0), yaw, "sedan", cols[i])
            stop = -14 - 7 * (i % 2) if lane < 0 else 14 + 7 * (i % 2)
            key(c, "location", f0, (Z.ROAD_X + lane, y, 0))
            key(c, "location", cross - 4, (Z.ROAD_X + lane, stop, 0))
            key(c, "rotation_euler", cross - 6, (0, 0, yaw))
            key(c, "rotation_euler", cross - 2, (0.08 if lane < 0 else -0.08, 0, yaw))  # nose dips: hard braking
            key(c, "rotation_euler", cross + 4, (0, 0, yaw))
        _camera(scene, (Z.ROAD_X - 22, -34, 6), (Z.ROAD_X, 0, 4), 22, f0, f1, 0.05)

    elif stage == "river":  # it reaches the river... and floats across
        frames, xs = _path(at(0.2), f1 + int(fps * 0.6), Z.RIVER[0] - 6, Z.RIVER[1] - 6, ease=0.8)
        _drive(rig, wheels, [f0, at(0.12)], [Z.RIVER[0] - 22, Z.RIVER[0] - 8])
        _drive(rig, wheels, frames, xs, floating=True)
        _you(rig, f0).raise_arm(at(0.25), at(0.32), "L", hold=40)
        water = P._soft("splash", "#d6eefc")
        hit = at(0.2)
        for i in range(18):
            a = i / 18 * 2 * math.pi
            p = P._sphere(f"sp{i}", 0.8, water, (Z.RIVER[0] - 6, 0, 0))
            p.visible_shadow = False
            P._appear(p, hit)
            key(p, "scale", hit, (1.0, 1.0, 1.0))
            key(p, "location", hit, (Z.RIVER[0] - 6 + math.cos(a) * 6, math.sin(a) * 6, 0.3))
            key(
                p,
                "location",
                hit + int(fps * 0.7),
                (Z.RIVER[0] - 6 + math.cos(a) * 11, math.sin(a) * 10, rng.uniform(4, 9)),
            )
            key(p, "scale", hit + int(fps * 0.7), (2.0, 2.0, 2.0))
            key(p, "scale", hit + int(fps * 1.3), (0.001, 0.001, 0.001))
        _camera(scene, (Z.RIVER[1] + 10, -30, 6), (Z.RIVER[0] + 25, 0, 3), 22, f0, f1, 0.04)  # from the far bank

    elif stage == "town":  # out of the river and down the street to school, full speed
        frames, xs = _path(f0, f1, 482.0, 640.0, ease=1.1)
        _drive(rig, wheels, frames, xs)
        _you(rig, f0, wave=True)
        for i, x in enumerate((530, 575, 615)):
            p = _hero((x, -11.0 if i % 2 else 13.0, 0.18), math.pi / 2, f0)
            p.look_at(f0, (x - 30, 0, 4))
            p.raise_arm(at(0.2 + 0.25 * i), at(0.27 + 0.25 * i), "R", hold=30)
        _camera(scene, (-18, -9, 7), (8, 0, 3), 22, f0, f1, follow=rig)

    elif stage == "school":  # it stops right at the door. On time.
        frames, xs = _path(f0, at(0.55), 646.0, STOP_X - 6.0, ease=0.55)
        _drive(rig, wheels, frames, xs)
        key(rig, "rotation_euler", at(0.55) + 3, (0, 0.06, 0))  # it rocks forward when it stops
        key(rig, "rotation_euler", at(0.55) + 9, (0, 0, 0))
        hero = _you(rig, f0)
        hero.wave(at(0.65), f1, "R")
        for k in range(5):  # classmates at the door
            _hero((Z.SCHOOL_X - 3, -9 + 4.5 * k, 0.18), math.pi, f0).look_at(f0, (STOP_X - 6, 0, 3))
        _camera(scene, (668, -24, 4), (STOP_X - 4, 0, 4), 22, f0, f1, 0.04)

    if params.get("outlines") is False:
        scene.render.use_freestyle = False
