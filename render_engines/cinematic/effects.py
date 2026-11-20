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
from render_engines.core.blender.animation import add_noise, key, set_interpolation
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


def fire(
    name: str, location, start: int, end: int, fps: int, size: float = 1.0, seed: int = 0, col=None, smoke: float = 1.0
) -> None:
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
        size=0.3 * size * smoke,
        spread=0.6 * smoke,
        seed=seed,
        col=col,
    )


def crack(
    name: str,
    location,
    start: int,
    end: int,
    surface: str = "wall",
    length: float = 2.0,
    seed: int = 0,
    col=None,
    thick: float = 1.0,
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
        width = thick * 0.06 * (1.0 - i / (segments + 2))
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


def snow(
    name: str, center, start: int, end: int, fps: int, area: float = 6.0, count: int = 160, seed: int = 0, col=None
) -> None:
    """Snowflakes falling (and drifting) through the view, looping until `end`: the cold the line talks about."""
    rng = random.Random(seed)
    mat = materials.principled(f"{name}_flake", "#ffffff", emission="#eef6ff", emission_strength=1.5)
    cx, cy, cz = center
    top = cz + 3.2
    fall = max(1.0, top - 0.0)
    for i in range(count):
        flake = objects.mesh_object(f"{name}_{i}", objects.icosphere(rng.uniform(0.07, 0.11), 1), mat, col=col)
        flake.visible_shadow = False
        x, y = cx + rng.uniform(-area / 2, area / 2), cy + rng.uniform(-area / 2, area / 2)
        speed = rng.uniform(0.7, 1.2)  # metres a second
        period = max(6, int(fall / speed * fps))
        offset = rng.randrange(period)
        _hidden_until(flake, start)
        frame = start
        while frame < end:
            phase = ((frame - start + offset) % period) / period
            z = top - phase * fall
            drift = 0.15 * math.sin((frame + i * 13) / fps * 1.7)
            key(flake, "location", frame, (x + drift, y + drift * 0.5, z))
            frame += 4
        set_interpolation(flake, "LINEAR")


def frost(name: str, center, start: int, end: int, size: float = 7.0, seed: int = 0, col=None) -> None:
    """Frost spreading over the ground in icy patches (pale blue-white, a little shiny), not one white sheet."""
    rng = random.Random(seed)
    mat = materials.principled(f"{name}_mat", "#dcecf7", roughness=0.25, emission="#cfe6f7", emission_strength=0.25)
    span = max(1, end - start)
    for i in range(26):
        r = rng.uniform(0.4, 1.3) * size / 7.0
        x = center[0] + rng.uniform(-size / 2, size / 2)
        y = center[1] + rng.uniform(-size / 2, size / 2)
        patch = objects.mesh_object(
            f"{name}_{i}",
            objects.cone(r, r, 0.006, 9, base_at_origin=True),
            mat,
            location=(x, y, 0.01 + i * 0.0004),
            col=col,
        )
        patch.visible_shadow = False
        born = start + int(span * rng.uniform(0, 0.7))
        key(patch, "scale", start, (0.001, 0.001, 1.0))
        key(patch, "scale", born, (0.001, 0.001, 1.0))
        key(patch, "scale", min(end, born + int(span * 0.4)), (1.0, rng.uniform(0.6, 1.0), 1.0))


def explosion(name: str, location, start: int, fps: int, size: float = 2.0, seed: int = 0, col=None) -> None:
    """A blast: a flash, a ball of fire that grows and fades fast, and a big cloud of dark smoke."""
    x, y, z = location
    flash = lights.point(f"{name}_flash", (x, y, z + size), "#ffd29a", 0.0, radius=size)
    key(flash.data, "energy", max(0, start - 1), 0.0)
    key(flash.data, "energy", start + 2, 9000.0 * size)
    key(flash.data, "energy", start + int(0.8 * fps), 0.0)
    ball = objects.mesh_object(
        f"{name}_ball",
        objects.icosphere(1.0, 3),
        materials.principled(f"{name}_ballmat", "#ffb347", emission="#ff7a1a", emission_strength=25.0),
        smooth=True,
        location=(x, y, z + size * 0.5),
        col=col,
    )
    ball.visible_shadow = False
    _hidden_until(ball, start)
    key(ball, "scale", start, (0.1, 0.1, 0.1))
    key(ball, "scale", start + int(0.35 * fps), (size, size, size * 0.8))
    key(ball, "scale", start + int(0.9 * fps), (0.001, 0.001, 0.001))
    fire(f"{name}_fire", location, start + int(0.3 * fps), start + int(6 * fps), fps, size * 0.8, seed, col=col)
    puffs(
        f"{name}_cloud",
        (x, y, z + size * 0.6),
        start + 2,
        start + int(3 * fps),
        fps,
        color="#5a5a5e",
        alpha=0.4,
        count=14,
        rise=size * 2.5,
        spread=size * 0.8,
        size=size * 0.5,
        life=3.0,
        seed=seed,
        col=col,
    )


def levitate(obj, start: int, end: int, fps: int, height: float = 1.2, seed: int = 0) -> None:
    """Something loses its weight: it lifts slowly off where it was and turns in the air."""
    rng = random.Random(seed)
    x, y, z = obj.location
    rx, ry, rz = obj.rotation_euler
    key(obj, "location", start, (x, y, z))
    key(obj, "rotation_euler", start, (rx, ry, rz))
    key(obj, "location", end, (x + rng.uniform(-0.2, 0.2), y + rng.uniform(-0.2, 0.2), z + height))
    key(obj, "rotation_euler", end, (rx + rng.uniform(-0.8, 0.8), ry + rng.uniform(-0.8, 0.8), rz + rng.uniform(-1, 1)))


def meteor(
    name: str,
    impact,
    start: int,
    hit: int,
    fps: int,
    size: float = 3.0,
    seed: int = 0,
    lands: bool = True,
    col=None,
    origin=None,
    to=None,
) -> None:
    """A burning rock crosses the sky and, if it lands, hits at `impact`: flash, fireball, cracks and fire.

    The rock is a library rock (Quaternius, CC0) glowing orange, with a trail of fire and smoke behind it.
    `lands` False: it only crosses the sky high up and leaves the frame (seen from far away, still coming).
    """
    from render_engines.cinematic import assets

    rng = random.Random(seed)
    ix, iy, iz = impact
    direction = Vector((rng.uniform(-0.6, 0.6), 1.0, 0.0)).normalized()  # comes from behind the impact point
    # origin/to: points chosen in front of the camera, so the whole fall is in the frame (Nov 20 test: the
    # rock came from outside the view and only the blast was seen)
    sky = Vector(origin) if origin else Vector((ix, iy, iz)) + direction * 140.0 + Vector((0.0, 0.0, 110.0))
    end = Vector((ix, iy, iz)) if lands else (Vector(to) if to else sky + (Vector((ix, iy, 40.0)) - sky) * 0.9)
    rocks = [m for m in assets.available("simple_nature") if m.startswith("Rock")] or []
    hot = materials.principled(f"{name}_hot", "#7a2e10", emission="#ff5a14", emission_strength=2.2)
    if rocks:
        rock = assets.place("simple_nature", rng.choice(rocks), f"{name}_rock", sky, size, 0.0, col)
        rock.data = rock.data.copy()
        rock.data.materials.clear()
        rock.data.materials.append(hot)
    else:
        rock = objects.mesh_object(f"{name}_rock", objects.icosphere(size * 0.5, 2), hot, False, sky, col=col)
    rock.visible_shadow = False
    glow = objects.mesh_object(
        f"{name}_glow",
        objects.icosphere(size * 1.3, 2),
        materials.principled(f"{name}_glowmat", "#ff8a2a", emission="#ff7a1a", emission_strength=1.6),
        True,
        sky,
        col=col,
    )
    glow.visible_shadow = False
    glow.parent = rock
    glow.location = (0.0, 0.0, size * 0.4)
    glow.scale = (1.0 / rock.scale[0],) * 3
    key(rock, "location", start, sky)
    key(rock, "location", hit, end)
    key(rock, "rotation_euler", start, (0.0, 0.0, 0.0))
    key(rock, "rotation_euler", hit, (rng.uniform(4, 8), rng.uniform(4, 8), 0.0))
    set_interpolation(rock, "LINEAR")
    _hidden_until(rock, start)
    light = lights.point(f"{name}_light", sky, "#ffa04a", 0.0, radius=size)
    light.parent = rock
    light.location = (0.0, 0.0, 0.0)
    key(light.data, "energy", start, 60000.0 * size)
    # the trail: fire balls left along the path, each shrinking and turning to smoke
    steps = max(6, (hit - start) // 2)
    trail_mats = {
        "f": materials.principled(f"{name}_trailf", "#ff9a2a", emission="#ff6a10", emission_strength=1.8),
        "s": materials.principled(f"{name}_smoke", "#3e3a37", roughness=1.0),  # "smoke": the toon look leaves it dark
    }
    for k in range(steps):
        t = k / steps
        f = start + int((hit - start) * t)
        p = sky + (end - sky) * t
        for kind, life, grow in (("f", 0.5, 1.4), ("s", 2.5, 3.0)):
            ball = objects.mesh_object(
                f"{name}_trail{kind}{k}",
                objects.icosphere(size * (0.6 if kind == "f" else 0.5), 2),
                trail_mats[kind],
                True,
                tuple(p),
                col=col,
            )
            ball.visible_shadow = False
            key(ball, "scale", start, (0.001, 0.001, 0.001))
            key(ball, "scale", max(start, f - 1), (0.001, 0.001, 0.001))
            key(ball, "scale", f + 1, (1.0, 1.0, 1.0))
            key(ball, "scale", f + int(life * fps), (grow, grow, grow) if kind == "s" else (0.001, 0.001, 0.001))
            if kind == "s":
                key(ball, "scale", f + int((life + 1.0) * fps), (0.001, 0.001, 0.001))
    if not lands:
        key(rock, "scale", hit, tuple(rock.scale))
        key(rock, "scale", hit + 1, (0.001, 0.001, 0.001))
        return
    key(rock, "scale", hit, tuple(rock.scale))
    key(rock, "scale", hit + 1, (0.001, 0.001, 0.001))
    key(light.data, "energy", hit, 60000.0 * size)
    key(light.data, "energy", hit + 2, 0.0)
    explosion(f"{name}_blast", (ix, iy, iz), hit, fps, size * 2.5, seed, col=col)
    crack(f"{name}_crack", (ix, iy - 4.0, 0.01), hit, hit + int(1.2 * fps), "floor", 9.0, seed, thick=6.0)
