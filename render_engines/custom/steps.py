"""'Every step twice as long' (Nov 23): one person, one leap per scene, each leap starting where the last one
landed, over ONE world that grows below: the beach and the bakery, the promenade and the Ferris wheel, the city,
the bay, the clouds, the far coast. params: start (m along the path), stride (m), shop (show the bakery)."""

from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

from render_engines.cinematic.character import build_character
from render_engines.core.blender.animation import key, set_interpolation
from render_engines.core.colors import hex_to_linear

SEED = 2611  # the same world in every scene of the video
COAST_END = 1500.0  # land until here (beach, promenade, city), then the bay
FAR_COAST = 14000.0


def _mat(name: str, colour: str, emit: float = 0.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = hex_to_linear(colour)
    b.inputs["Roughness"].default_value = 0.9
    if emit:
        b.inputs["Emission Color"].default_value = hex_to_linear(colour)
        b.inputs["Emission Strength"].default_value = emit
    return m


def _boxes(name: str, boxes, material) -> None:
    """Many boxes in ONE mesh (a city of thousands of buildings renders fast)."""
    verts, faces = [], []
    for (x, y, z), (sx, sy, sz) in boxes:
        base = len(verts)
        for dz in (0, sz):
            for dx, dy in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)):
                verts.append((x + dx, y + dy, z + dz))
        faces += [
            (base, base + 1, base + 2, base + 3),
            (base + 4, base + 7, base + 6, base + 5),
            *[(base + i, base + 4 + i, base + 4 + (i + 1) % 4, base + (i + 1) % 4) for i in range(4)],
        ]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)


def _plane(name, x0, x1, y0, y1, z, material) -> None:
    _boxes(name, [(((x0 + x1) / 2, (y0 + y1) / 2, z), (x1 - x0, y1 - y0, 0.05))], material)


def _world(scene) -> None:
    rng = random.Random(SEED)
    water, sand = _mat("st_water", "#2f7fc4"), _mat("st_sand", "#ead8a8")
    grass, road = _mat("st_grass", "#6bbf59"), _mat("st_road", "#5d6066")
    _plane("sea", -60000, 120000, -60000, 60000, -0.3, water)
    _plane("beach", -400, COAST_END, -60, 0, -0.05, sand)  # the shore runs along x; the sea is at y < -60
    _plane("land", -400, COAST_END, 0, 4000, -0.06, grass)
    _plane("promenade", -400, 220, 6, 14, 0.0, road)
    _plane("far_land", FAR_COAST, 120000, -60000, 60000, -0.25, grass)
    # the street with the bakery, cars and palms (the first steps)
    cols = ["#e74c3c", "#3498db", "#f1c40f", "#2ecc71", "#ecf0f1"]
    cars = [((rng.uniform(-30, 200), rng.choice((8.5, 11.5)), 0.45), (4.2, 1.8, 0.9)) for _ in range(26)]
    for i, c in enumerate(cars):
        _boxes(f"car{i}", [c, ((c[0][0], c[0][1], 1.15), (2.2, 1.6, 0.6))], _mat(f"st_car{i % 5}", cols[i % 5]))
    trunk, leaf = _mat("st_trunk", "#8b5a2b"), _mat("st_leaf", "#3f9b3f")
    for i in range(40):
        x, y = rng.uniform(-60, 240), rng.choice((17.0, -24.0))  # never between the camera and the path
        _boxes(f"palm{i}", [((x, y, 0), (0.35, 0.35, 6)), ((x, y, 6), (3.2, 3.2, 0.5))], leaf)
        _boxes(f"trunk{i}", [((x, y, 0), (0.35, 0.35, 6))], trunk)
    shop = _mat("st_shop", "#f4e3c1")
    _boxes("bakery", [((6, 22, 0), (10, 8, 6))], shop)
    _boxes("awning", [((6, 17.6, 3.2), (10, 1.2, 0.25))], _mat("st_awning", "#d35400"))
    bpy.ops.object.text_add(location=(1.8, 17.9, 4.0), rotation=(math.radians(90), 0, 0))
    sign = bpy.context.object
    sign.data.body, sign.data.size = "PAN", 1.6
    sign.data.materials.append(_mat("st_sign", "#7a3b12"))
    # the Ferris wheel on the pier
    ring = _mat("st_wheel", "#bdc3c7")
    for k in range(24):
        a = k / 24 * 2 * math.pi
        _boxes(
            f"cab{k}",
            [((90 + 14 * math.cos(a), -20, 16 + 14 * math.sin(a)), (1.6, 1.6, 1.6))],
            _mat(f"st_cab{k % 5}", cols[k % 5]),
        )
    _boxes("wheel_legs", [((90, -20, 8), (1, 1, 16)), ((90, -20, 0.5), (12, 2, 1))], ring)
    _plane("pier", 70, 110, -60, -6, 0.2, _mat("st_pier", "#a0784f"))
    # the city: low near the beach, towers downtown
    blocks = []
    for gx in range(260, int(COAST_END) - 40, 46):
        for gy in range(30, 1400, 46):
            centre = math.exp(-(((gx - 800) / 380) ** 2 + ((gy - 500) / 420) ** 2))
            for ox, oy in ((-10, -10), (10, -10), (-10, 10), (10, 10)):
                h = 6 + 18 * rng.random() + 160 * centre * rng.random()
                blocks.append(((gx + ox, gy + oy, 0), (16, 16, h)))
    tones = ["#d9cbb5", "#b8c4cf", "#e0a37a", "#9aa7b4", "#cf8f6b"]
    for t in range(5):
        _boxes(f"city{t}", blocks[t::5], _mat(f"st_bld{t}", tones[t]))
    # a grid town on the far coast
    town = [
        ((x, y, 0), (30, 30, 8 + 20 * rng.random()))
        for x in range(int(FAR_COAST) + 300, int(FAR_COAST) + 4000, 90)
        for y in range(-1500, 1500, 90)
        if rng.random() < 0.6
    ]
    _boxes("far_town", town, _mat("st_town", "#e3b58c"))
    # clouds over the bay
    cloud = _mat("st_cloud", "#ffffff")
    for _i in range(90):
        x, y, z = rng.uniform(2500, 40000), rng.uniform(-6000, 6000), rng.uniform(1600, 2600)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1, location=(x, y, z))
        c = bpy.context.object
        c.scale = (rng.uniform(300, 700), rng.uniform(200, 450), rng.uniform(60, 120))
        c.data.materials.append(cloud)
    world = scene.world or bpy.data.worlds.new("st_world")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = hex_to_linear("#9fd3f5")
    bg.inputs[1].default_value = 1.0
    sun = bpy.data.objects.new("st_sun", bpy.data.lights.new("st_sun", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = (math.radians(50), 0, math.radians(35))
    scene.collection.objects.link(sun)


def _crack(at: Vector, size: float, frame: int) -> None:
    """Dark lines that spread from where the foot lands (the bigger the step, the bigger the crack)."""
    rng = random.Random(int(at.x))
    mat = _mat("st_crack", "#2b2b2b")
    for k in range(9):
        a = k / 9 * 2 * math.pi + rng.uniform(-0.2, 0.2)
        length = size * rng.uniform(0.6, 1.0)
        bpy.ops.mesh.primitive_cube_add(location=(at.x, at.y, 0.06))
        c = bpy.context.object
        c.dimensions = (length, max(0.04, size * 0.025), 0.02)
        c.rotation_euler = (0, 0, a)
        c.location = (at.x + math.cos(a) * length / 2, at.y + math.sin(a) * length / 2, 0.06)
        c.data.materials.append(mat)
        full = tuple(c.scale)
        key(c, "scale", frame - 1, (0.001, full[1], full[2]))
        key(c, "scale", frame + 6, full)


def build(spec: dict, ctx, scene, params: dict) -> None:
    start, stride = float(params.get("start", 0.0)), max(0.5, float(params.get("stride", 1.5)))
    _world(scene)
    f0, f1 = ctx.frame_start, ctx.frame_end
    take, land = f0 + int((f1 - f0) * 0.12), f0 + int((f1 - f0) * 0.86)
    hero = build_character(
        "hero", {"body": "#f07c22", "accent": "#1f2a44", "hair": "#2b1a10"}, (start, 2.0, 0), hat=False
    )
    hero.set_yaw(f0, -math.pi / 2, turn_frames=0)  # facing +x, the way of the path
    a, b = Vector((start, 2.0, 0.0)), Vector((start + stride, 2.0, 0.0))
    height = max(0.9, stride * 0.22)
    steps = 12
    for i in range(steps + 1):
        t = i / steps
        p = a.lerp(b, t)
        p.z = 4 * height * t * (1 - t)
        key(hero.root, "location", take + int((land - take) * t), tuple(p))
    key(hero.root, "location", f0, tuple(a))
    key(hero.root, "location", f1, tuple(b))
    # the leap pose: legs split, arms out
    for side, sign in (("L", 1), ("R", -1)):
        key(hero.legs[side], "rotation_euler", take, (0, 0, 0))
        key(hero.legs[side], "rotation_euler", take + 6, (math.radians(55 * sign), 0, 0))
        key(hero.legs[side], "rotation_euler", land - 4, (math.radians(55 * sign), 0, 0))
        key(hero.legs[side], "rotation_euler", land + 4, (0, 0, 0))
        key(hero.arms[side], "rotation_euler", take + 6, (math.radians(-40 * sign), 0, math.radians(70 * sign)))
        key(hero.arms[side], "rotation_euler", land, (math.radians(-40 * sign), 0, math.radians(70 * sign)))
    if stride >= 40:
        _crack(b, min(60.0, stride * 0.05 + 6), land)
    # the camera follows the person, a little behind and to the side; it pulls back as the steps grow
    rig = bpy.data.objects.new("st_rig", None)
    scene.collection.objects.link(rig)
    follow = rig.constraints.new("COPY_LOCATION")
    follow.target = hero.root
    cam = bpy.data.objects.new("st_cam", bpy.data.cameras.new("st_cam"))
    scene.collection.objects.link(cam)
    cam.parent = rig
    dist = 5.5 + min(3.0, stride * 0.01)  # always close: the person stays big, the world shrinks below
    cam.location = (-dist * 0.55, -dist, dist * 0.42)
    cam.data.lens = 26
    cam.data.clip_end = 200000
    look = cam.constraints.new("TRACK_TO")
    look.target = hero.torso
    look.track_axis, look.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    scene.camera = cam
    set_interpolation(hero.root, "BEZIER")
    if params.get("outlines") is False:
        scene.render.use_freestyle = False
