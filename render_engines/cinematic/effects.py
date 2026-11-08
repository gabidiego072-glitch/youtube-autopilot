"""Visual events that match what the narration says: fire and smoke, cracks, rising water, a collapse.

All cheap for Cycles at low sample counts: flames are emissive meshes that flicker, smoke and dust are
semi-transparent puffs that rise and grow, cracks are thin dark strips that grow segment by segment,
water is a glossy slab that rises. No volumetrics, no simulation caches.
"""

from __future__ import annotations

import math
import random

import bpy
from mathutils import Matrix, Vector

from render_engines.core.blender import lights, materials, objects
from render_engines.core.blender.animation import add_noise, key
from render_engines.core.colors import hex_to_linear


def soft_puff_material(name: str, color: str, alpha: float):
    """Wispy steam/smoke: see-through, densest in the middle of each puff and fading to nothing at its edges,
    so overlapping puffs read as one soft cloud instead of solid balls."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    mix = nodes.new("ShaderNodeMixShader")
    clear = nodes.new("ShaderNodeBsdfTransparent")
    body = nodes.new("ShaderNodeBsdfDiffuse")
    body.inputs["Color"].default_value = hex_to_linear(color)
    facing = nodes.new("ShaderNodeLayerWeight")
    facing.inputs["Blend"].default_value = 0.5
    edge = nodes.new("ShaderNodeMath")
    edge.operation = "SUBTRACT"
    edge.inputs[0].default_value = 1.0
    links.new(facing.outputs["Facing"], edge.inputs[1])
    dens = nodes.new("ShaderNodeMath")
    dens.operation = "MULTIPLY"
    dens.inputs[1].default_value = alpha
    links.new(edge.outputs[0], dens.inputs[0])
    links.new(dens.outputs[0], mix.inputs["Fac"])
    links.new(clear.outputs[0], mix.inputs[1])
    links.new(body.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], out.inputs["Surface"])
    mat.diffuse_color = hex_to_linear(color)
    return mat


def _puff_material(name: str, color: str, alpha: float):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = hex_to_linear(color)
    bsdf.inputs["Roughness"].default_value = 1.0
    bsdf.inputs["Alpha"].default_value = alpha
    mat.diffuse_color = hex_to_linear(color)
    return mat


def _hidden_until(obj, frame: int) -> None:
    """Invisible (scale 0) before `frame`."""
    key(obj, "scale", max(0, frame - 1), (0.001, 0.001, 0.001))


def puffs(
    name: str,
    origin,
    start: int,
    end: int,
    fps: int,
    *,
    color: str = "#2f2f33",
    alpha: float = 0.55,
    count: int = 14,
    rise: float = 2.2,
    spread: float = 0.6,
    size: float = 0.35,
    life: float = 2.2,
    seed: int = 0,
    col=None,
    soft: bool = False,
) -> list:
    """Puffs that are born at `origin`, rise, drift and grow, staggered between start and end."""
    rng = random.Random(seed)
    mat = (soft_puff_material if soft else _puff_material)(f"{name}_mat", color, alpha)
    out = []
    span = max(1, end - start)
    life_f = max(6, int(life * fps))
    for i in range(count):
        born = start + int(span * i / max(1, count))
        dead = born + life_f
        puff = objects.mesh_object(f"{name}_{i}", objects.icosphere(size, 2), mat, smooth=True, col=col)
        puff.visible_shadow = False
        ox = origin[0] + rng.uniform(-0.15, 0.15)
        oy = origin[1] + rng.uniform(-0.15, 0.15)
        _hidden_until(puff, born)
        key(puff, "location", born, (ox, oy, origin[2]))
        key(puff, "scale", born, (0.3, 0.3, 0.3))
        drift = (rng.uniform(-spread, spread), rng.uniform(-spread, spread))
        key(puff, "location", dead, (ox + drift[0], oy + drift[1], origin[2] + rise * rng.uniform(0.8, 1.2)))
        grow = rng.uniform(1.6, 2.4)
        key(puff, "scale", dead, (grow, grow, grow))
        key(puff, "scale", dead + 1, (0.001, 0.001, 0.001))
        out.append(puff)
    return out


def fire(name: str, location, start: int, end: int, fps: int, size: float = 1.0, seed: int = 0, col=None) -> None:
    """Flames that flicker and grow in, a flickering warm light, and dark smoke rising above."""
    rng = random.Random(seed)
    x, y, z = location
    flame_mats = [
        materials.principled(f"{name}_core", "#ffd27a", emission="#ffcc55", emission_strength=18.0),
        materials.principled(f"{name}_outer", "#ff6a1a", emission="#ff5a10", emission_strength=12.0),
    ]
    grow_end = start + max(2, int(0.6 * fps))
    for i in range(9):
        radius = size * rng.uniform(0.08, 0.16)
        height = size * rng.uniform(0.35, 0.8)
        # A teardrop: a smooth sphere stretched upwards, wider at the base.
        drop = objects.icosphere(1.0, 3)
        for v in drop.verts:
            t = (v.co.z + 1.0) / 2.0  # 0 at the bottom, 1 at the top
            v.co.x *= radius * (1.0 - 0.85 * t)
            v.co.y *= radius * (1.0 - 0.85 * t)
            v.co.z = t * height
        flame = objects.mesh_object(
            f"{name}_flame_{i}",
            drop,
            flame_mats[i % 2],
            smooth=True,
            location=(x + rng.uniform(-0.25, 0.25) * size, y + rng.uniform(-0.25, 0.25) * size, z),
            col=col,
        )
        flame.visible_shadow = False
        _hidden_until(flame, start)
        key(flame, "scale", start, (0.2, 0.2, 0.2))
        key(flame, "scale", grow_end, (1.0, 1.0, 1.0))
        key(flame, "scale", end, (1.0, 1.0, 1.0))
        add_noise(flame, "scale", strength=0.25, scale=4.0, phase=i * 7.1)
        add_noise(flame, "rotation_euler", strength=0.12, scale=5.0, phase=i * 3.3)
    glow = lights.point(f"{name}_light", (x, y, z + 0.5 * size), "#ff8a3a", 0.0, radius=0.2 * size)
    key(glow.data, "energy", max(0, start - 1), 0.0)
    key(glow.data, "energy", grow_end, 900.0 * size)
    key(glow.data, "energy", end, 900.0 * size)
    add_noise(glow.data, "energy", strength=300.0 * size, scale=3.0)
    puffs(
        f"{name}_smoke",
        (x, y, z + 0.8 * size),
        start + int(0.3 * fps),
        end,
        fps,
        color="#1c1c1f",
        alpha=0.45,
        count=max(8, int((end - start) / fps * 5)),
        rise=2.4 * size,
        size=0.3 * size,
        seed=seed,
        col=col,
    )


def crack(
    name: str, location, start: int, end: int, surface: str = "wall", length: float = 2.0, seed: int = 0, col=None
) -> None:
    """A jagged dark crack that grows across a wall (facing -y) or the floor, segment by segment."""
    rng = random.Random(seed)
    mat = materials.principled(f"{name}_mat", "#141210", roughness=0.9)
    segments = 9
    point = Vector(location)
    heading = rng.uniform(-0.6, 0.6) + (math.pi / 2 if surface == "wall" else 0.0)
    step = length / segments
    frames = max(segments, end - start)
    for i in range(segments):
        heading += rng.uniform(-0.7, 0.7)
        if surface == "wall":  # the wall plane is x-z
            direction = Vector((math.cos(heading), 0.0, -abs(math.sin(heading)) if i % 3 else math.sin(heading)))
        else:  # floor / ground plane x-y
            direction = Vector((math.cos(heading), math.sin(heading), 0.0))
        direction.normalize()
        width = 0.06 * (1.0 - i / (segments + 2))
        seg = objects.mesh_object(
            f"{name}_{i}", objects.box(step, width, width, base_at_origin=False), mat, location=point.copy(), col=col
        )
        # Grow from its starting point: the segment's local x points along `direction`.
        seg.rotation_mode = "QUATERNION"
        seg.rotation_quaternion = Vector((1, 0, 0)).rotation_difference(direction)
        appear = start + int(frames * i / segments)
        seg.location = point + direction * (step / 2)
        _hidden_until(seg, appear)
        key(seg, "scale", appear, (0.05, 1, 1))
        key(seg, "scale", appear + max(1, frames // segments), (1, 1, 1))
        point = point + direction * step


def rising_water(name: str, center, size, start: int, end: int, height: float, col=None):
    """A glossy, slightly murky water slab that rises from the floor/road to `height` metres."""
    mat = materials.principled(f"{name}_mat", "#3b5a5e", roughness=0.05, coat=0.6)
    slab = objects.mesh_object(
        name, objects.box(size[0], size[1], 1.0, base_at_origin=True), mat, location=tuple(center), col=col
    )
    slab.visible_shadow = False
    key(slab, "scale", max(0, start - 1), (1, 1, 0.001))
    key(slab, "scale", end, (1, 1, max(0.01, height)))
    add_noise(slab, "location", strength=0.01, scale=8.0)
    return slab


def collapse(building, start: int, end: int, fps: int, seed: int = 0, col=None) -> None:
    """A building sinks and tilts into a cloud of dust."""
    rng = random.Random(seed)
    # Buildings are built with their geometry offset from the origin: move the origin to the base centre so
    # the building sinks and tilts in place instead of swinging around the scene origin.
    corners = [building.matrix_world @ Vector(c) for c in building.bound_box]
    base = Vector((sum(c.x for c in corners) / 8, sum(c.y for c in corners) / 8, min(c.z for c in corners)))
    building.data.transform(Matrix.Translation(-(base - building.location)))
    building.location = base
    loc = building.location.copy()
    height = building.dimensions.z
    key(building, "location", start, tuple(loc))
    key(building, "rotation_euler", start, (0, 0, 0))
    key(building, "location", end, (loc.x, loc.y + rng.uniform(0.5, 1.5), loc.z - height * 0.95))
    key(building, "rotation_euler", end, (math.radians(rng.uniform(-8, -4)), math.radians(rng.uniform(-6, 6)), 0))
    add_noise(building, "location", strength=0.08, scale=2.0)
    base = (loc.x, loc.y - building.dimensions.y / 2, 0.5)
    for k in range(3):
        offset = (k - 1) * building.dimensions.x / 3
        puffs(
            f"{building.name}_dust_{k}",
            (base[0] + offset, base[1], base[2]),
            start,
            end + fps,
            fps,
            color="#b7aa96",
            alpha=0.5,
            count=10,
            rise=height * 0.4,
            spread=3.0,
            size=1.2,
            life=2.5,
            seed=seed + k,
            col=col,
        )
