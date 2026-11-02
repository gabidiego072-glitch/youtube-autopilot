"""Procedural meadow environment: terrain, trees, rocks, flowers, hills, sky and light."""

from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Vector

from render_engines.core.blender import lights, materials, objects
from render_engines.core.blender.animation import add_noise, key
from render_engines.core.blender.scene import set_sky
from render_engines.core.noise import fbm

TIME_OF_DAY = {
    # sun elevation, azimuth, sun colour, sun strength, sky strength, fill colour, fill power
    "dawn": (6, 70, "#ffb070", 2.5, 0.5, "#8fa8ff", 120),
    "day": (45, 140, "#fff2dc", 4.0, 1.0, "#cfe0ff", 60),
    "dusk": (1.5, 235, "#ff8a40", 1.6, 0.22, "#6a7cff", 150),
}


def flat_radius_height(x: float, y: float, seed: int, flat_radius: float, amplitude: float) -> float:
    d = math.hypot(x, y)
    blend = max(0.0, min(1.0, (d - flat_radius) / (flat_radius * 1.2)))
    blend = blend * blend * (3 - 2 * blend)
    return (fbm(x * 0.06, y * 0.06, seed, octaves=4) - 0.35) * amplitude * blend


def build_terrain(
    seed: int,
    size: float = 80.0,
    resolution: int = 140,
    flat_radius: float = 9.0,
    amplitude: float = 6.0,
    colors=("#4f7a2a", "#8aa040"),
):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=resolution, y_segments=resolution, size=size / 2)
    for v in bm.verts:
        v.co.z = flat_radius_height(v.co.x, v.co.y, seed, flat_radius, amplitude)
    mat = materials.noise_ground("ground", colors[0], colors[1], scale=0.15, bump=0.15)
    return objects.mesh_object("Terrain", bm, mat, smooth=True)


def _pine(name, location, height, rng, mats, col):
    trunk = materials.principled("bark", "#4a3324", roughness=0.9)
    objects.mesh_object(
        f"{name}_trunk",
        objects.cone(0.12 * height / 4, 0.08 * height / 4, height * 0.35, 8),
        trunk,
        True,
        location,
        col=col,
    )
    leaf = rng.choice(mats)
    for i in range(3):
        r = height * (0.33 - i * 0.08)
        z = height * (0.22 + i * 0.22)
        objects.mesh_object(
            f"{name}_leaves_{i}",
            objects.cone(r, 0.0, height * 0.42, 10),
            leaf,
            False,
            (location[0], location[1], location[2] + z),
            rotation=(0, 0, rng.uniform(0, 6.28)),
            col=col,
        )


def _round_tree(name, location, height, rng, mats, col):
    trunk = materials.principled("bark", "#4a3324", roughness=0.9)
    objects.mesh_object(f"{name}_trunk", objects.cone(0.15, 0.1, height * 0.55, 8), trunk, True, location, col=col)
    leaf = rng.choice(mats)
    for i in range(3):
        offset = Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), height * (0.6 + rng.uniform(0, 0.25))))
        blob = objects.icosphere(height * rng.uniform(0.22, 0.3), 2)
        for v in blob.verts:
            v.co *= 1 + rng.uniform(-0.08, 0.08)
        objects.mesh_object(f"{name}_crown_{i}", blob, leaf, True, Vector(location) + offset, col=col)


def _rock(name, location, size, rng, mat, col):
    bm = objects.icosphere(size, 1)
    for v in bm.verts:
        v.co *= 1 + rng.uniform(-0.25, 0.25)
        v.co.z *= 0.6
    objects.mesh_object(name, bm, mat, False, location, rotation=(0, 0, rng.uniform(0, 6.28)), col=col)


def _segment_distance(px, py, a, b) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def keep_clear(x: float, y: float, paths=()) -> bool:
    """Leave the stage, the foreground (towards -Y) and every walk path open."""
    if math.hypot(x, y) < 6.5 or (y < 3 and abs(x) < 15):
        return True
    return any(_segment_distance(x, y, a, b) < 3.0 for a, b in paths)


def scatter(env: dict, seed: int, flat_radius: float, amplitude: float, paths=()) -> None:
    rng = random.Random(seed)
    col = objects.collection("Environment")
    leaf_mats = [
        materials.principled(f"leaves_{i}", c, roughness=0.8)
        for i, c in enumerate(("#2f5a2a", "#3d6b2c", "#4c7a33", "#2a4d33"))
    ]
    rock_mat = materials.principled("rock", "#7d7a72", roughness=0.9)

    def ground(x, y):
        return flat_radius_height(x, y, seed, flat_radius, amplitude)

    placed = 0
    while placed < env.get("trees", 30):
        x, y = rng.uniform(-36, 36), rng.uniform(-20, 36)
        if keep_clear(x, y, paths):
            continue
        builder = _pine if rng.random() < 0.6 else _round_tree
        builder(f"tree_{placed}", (x, y, ground(x, y) - 0.1), rng.uniform(3.5, 7.0), rng, leaf_mats, col)
        placed += 1
    for i in range(env.get("rocks", 20)):
        x, y = rng.uniform(-20, 20), rng.uniform(-12, 20)
        if math.hypot(x, y) < 3 or any(_segment_distance(x, y, a, b) < 1.2 for a, b in paths):
            continue
        _rock(f"rock_{i}", (x, y, ground(x, y)), rng.uniform(0.15, 0.7), rng, rock_mat, col)

    petal_colors = ("#f2d64b", "#e86f9a", "#f5f2e8", "#9a7fe0")
    stem = materials.principled("stem", "#3f6b2a", roughness=0.8)
    for i in range(env.get("flowers", 60)):
        x, y = rng.uniform(-10, 10), rng.uniform(-6, 10)
        z = ground(x, y)
        objects.mesh_object(f"stem_{i}", objects.cone(0.012, 0.01, 0.22, 5), stem, False, (x, y, z), col=col)
        petal = materials.principled(f"petal_{i % 4}", petal_colors[i % 4], roughness=0.5)
        objects.mesh_object(
            f"flower_{i}", objects.sphere(0.045, 8, 6), petal, True, (x, y, z + 0.23), scale=(1, 1, 0.5), col=col
        )

    hill = materials.principled("far_hills", "#3b5534", roughness=0.95)
    for i in range(7):
        x = -90 + i * 30 + rng.uniform(-8, 8)
        bm = objects.icosphere(rng.uniform(25, 40), 3)
        objects.mesh_object(f"hill_{i}", bm, hill, True, (x, rng.uniform(80, 110), -12), scale=(1.4, 1, 0.45), col=col)


def fireflies(count: int, center, radius: float, ctx, seed: int) -> None:
    rng = random.Random(seed + 99)
    col = objects.collection("Fireflies")
    glow = materials.principled("firefly", "#d8ff8a", emission="#d8ff6a", emission_strength=40.0)
    span = ctx.frame_end - ctx.frame_start
    for i in range(count):
        base = Vector(
            (
                center[0] + rng.uniform(-radius, radius),
                center[1] + rng.uniform(-radius * 0.3, radius),
                rng.uniform(0.8, 2.8),
            )
        )
        fly = objects.mesh_object(f"firefly_{i}", objects.sphere(0.025, 8, 6), glow, True, base, col=col)
        drift = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.3, 0.3)))
        key(fly, "location", ctx.frame_start, base)
        key(fly, "location", ctx.frame_start + span, base + drift)
        add_noise(fly, "location", strength=0.25, scale=25, phase=i * 3.1)


def build_environment(env: dict, ctx, scene: bpy.types.Scene, paths=()) -> dict:
    seed = ctx.seed
    flat, amp = env.get("flat_radius", 9.0), env.get("hill_height", 6.0)
    build_terrain(seed, flat_radius=flat, amplitude=amp)
    scatter(env, seed, flat, amp, paths)

    elevation, azimuth, sun_color, sun_strength, sky_strength, fill_color, fill_power = TIME_OF_DAY[
        env.get("time_of_day", "day")
    ]
    set_sky(scene, elevation, azimuth, strength=sky_strength, dust=2.0, sun_disc=True)
    lights.sun("Sun", elevation, azimuth, sun_color, sun_strength, softness_deg=3)
    lights.area("Fill", (-6, -10, 6), (math.radians(60), 0, math.radians(-30)), fill_color, fill_power, size=8)
    return {"ground_height": lambda x, y: flat_radius_height(x, y, seed, flat, amp)}
