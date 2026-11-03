"""Outer-space environment and planet props, all procedural (no textures)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import bpy

from render_engines.core.blender import lights, objects
from render_engines.core.blender.animation import key, set_interpolation
from render_engines.core.colors import hex_to_linear


def build_space(env: dict, scene: bpy.types.Scene) -> None:
    """Black sky with procedural stars and a single hard sun light."""
    world = bpy.data.worlds.new("Space")
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    coord = nodes.new("ShaderNodeTexCoord")
    stars = nodes.new("ShaderNodeTexVoronoi")
    stars.inputs["Scale"].default_value = 260.0
    ramp = nodes.new("ShaderNodeValToRGB")
    density = max(0.0, min(1.0, env.get("stars", 0.6)))
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (1, 1, 1, 1)
    ramp.color_ramp.elements[1].position = 0.02 + 0.05 * density
    ramp.color_ramp.elements[1].color = (0, 0, 0, 1)
    tint = nodes.new("ShaderNodeMix")
    tint.data_type = "RGBA"
    tint.inputs["A"].default_value = hex_to_linear("#03040a")
    tint.inputs["B"].default_value = (1, 1, 1, 1)
    background = nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = 1.0
    out = nodes.new("ShaderNodeOutputWorld")
    links.new(coord.outputs["Generated"], stars.inputs["Vector"])
    links.new(stars.outputs["Distance"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], tint.inputs["Factor"])
    links.new(tint.outputs["Result"], background.inputs["Color"])
    links.new(background.outputs["Background"], out.inputs["Surface"])
    lights.sun(
        "Sun",
        env.get("sun_elevation", 10),
        env.get("sun_azimuth", 200),
        "#fff6e8",
        env.get("sun", 4.0),
        softness_deg=0.6,
    )


def _node_material(name: str):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat, mat.node_tree.nodes, mat.node_tree.links


def _ramp(nodes, stops: list[tuple[float, str]]):
    ramp = nodes.new("ShaderNodeValToRGB")
    elements = ramp.color_ramp.elements
    elements[0].position, elements[0].color = stops[0][0], hex_to_linear(stops[0][1])
    elements[1].position, elements[1].color = stops[1][0], hex_to_linear(stops[1][1])
    for position, color in stops[2:]:
        element = elements.new(position)
        element.color = hex_to_linear(color)
    return ramp


def _unit_coords(nodes, links, radius: float):
    """Object coordinates divided by the radius, so patterns look the same at any planet size."""
    coord = nodes.new("ShaderNodeTexCoord")
    unit = nodes.new("ShaderNodeVectorMath")
    unit.operation = "SCALE"
    unit.inputs["Scale"].default_value = 1.0 / radius
    links.new(coord.outputs["Object"], unit.inputs[0])
    return unit.outputs["Vector"]


def _surface_material(name: str, kind: str, radius: float):
    mat, nodes, links = _node_material(name)
    bsdf = nodes["Principled BSDF"]
    coords = _unit_coords(nodes, links, radius)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = {"earth": 1.1, "mars": 2.2, "moon": 3.5}.get(kind, 2.0)
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = 0.55
    links.new(coords, noise.inputs["Vector"])
    palettes = {
        "earth": [
            (0.0, "#071f4d"),
            (0.52, "#155a9e"),
            (0.545, "#c8b98a"),
            (0.56, "#3d7a34"),
            (0.65, "#5d6b33"),
            (0.72, "#8a7a5c"),
        ],
        "mars": [(0.0, "#5a2412"), (0.45, "#a4482a"), (0.6, "#c8713f"), (0.8, "#e3a56e")],
        "moon": [(0.0, "#4b4b4f"), (0.5, "#8d8c88"), (0.8, "#bdbbb5")],
    }
    ramp = _ramp(nodes, palettes.get(kind, palettes["moon"]))
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    color_out = ramp.outputs["Color"]
    if kind == "earth":
        # Polar ice caps: whiten where |z| is high.
        sep = nodes.new("ShaderNodeSeparateXYZ")
        links.new(coords, sep.inputs["Vector"])
        absz = nodes.new("ShaderNodeMath")
        absz.operation = "ABSOLUTE"
        links.new(sep.outputs["Z"], absz.inputs[0])
        cap = nodes.new("ShaderNodeMapRange")
        cap.inputs["From Min"].default_value = 0.88
        cap.inputs["From Max"].default_value = 0.93
        links.new(absz.outputs["Value"], cap.inputs["Value"])
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["B"].default_value = hex_to_linear("#f2f6fa")
        links.new(cap.outputs["Result"], mix.inputs["Factor"])
        links.new(color_out, mix.inputs["A"])
        color_out = mix.outputs["Result"]
        bsdf.inputs["Roughness"].default_value = 0.45
    else:
        craters = nodes.new("ShaderNodeTexVoronoi")
        craters.inputs["Scale"].default_value = 9.0
        links.new(coords, craters.inputs["Vector"])
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.35
        links.new(craters.outputs["Distance"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        bsdf.inputs["Roughness"].default_value = 0.95
    links.new(color_out, bsdf.inputs["Base Color"])
    return mat


def _clouds_material(name: str, radius: float):
    mat, nodes, links = _node_material(name)
    nodes.remove(nodes["Principled BSDF"])
    out = nodes["Material Output"]
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.5
    noise.inputs["Detail"].default_value = 8.0
    links.new(_unit_coords(nodes, links, radius), noise.inputs["Vector"])
    ramp = _ramp(nodes, [(0.56, "#000000"), (0.7, "#ffffff")])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    white = nodes.new("ShaderNodeBsdfDiffuse")
    clear = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(ramp.outputs["Color"], mix.inputs["Fac"])
    links.new(clear.outputs["BSDF"], mix.inputs[1])
    links.new(white.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


def _atmosphere_material(name: str, color: str = "#4f9bff"):
    mat, nodes, links = _node_material(name)
    nodes.remove(nodes["Principled BSDF"])
    out = nodes["Material Output"]
    weight = nodes.new("ShaderNodeLayerWeight")
    weight.inputs["Blend"].default_value = 0.35
    power = nodes.new("ShaderNodeMath")
    power.operation = "POWER"
    power.inputs[1].default_value = 4.0
    links.new(weight.outputs["Facing"], power.inputs[0])
    glow = nodes.new("ShaderNodeEmission")
    glow.inputs["Color"].default_value = hex_to_linear(color)
    glow.inputs["Strength"].default_value = 0.9
    clear = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(power.outputs["Value"], mix.inputs["Fac"])
    links.new(clear.outputs["BSDF"], mix.inputs[1])
    links.new(glow.outputs["Emission"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


def _sun_material(name: str):
    mat, nodes, links = _node_material(name)
    nodes.remove(nodes["Principled BSDF"])
    out = nodes["Material Output"]
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6.0
    ramp = _ramp(nodes, [(0.35, "#ff7a1a"), (0.65, "#fff0b0")])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    glow = nodes.new("ShaderNodeEmission")
    glow.inputs["Strength"].default_value = 12.0
    links.new(ramp.outputs["Color"], glow.inputs["Color"])
    links.new(glow.outputs["Emission"], out.inputs["Surface"])
    return mat


@dataclass
class Planet:
    name: str
    location: tuple
    root: object
    spinner: object
    clouds: object | None
    spin_rate: float  # deg/s at the start
    focus_height: float = 0.0
    changes: list = field(default_factory=list)  # (start_frame, end_frame, rate_from, rate_to)

    def change_spin(self, start: int, end: int, rate_from: float, rate_to: float) -> None:
        self.changes.append((start, end, rate_from, rate_to))

    def rate_at(self, frame: float) -> float:
        rate = self.spin_rate
        for start, end, rate_from, rate_to in sorted(self.changes):
            if frame >= end:
                rate = rate_to
            elif frame >= start:
                t = (frame - start) / max(1, end - start)
                return rate_from + (rate_to - rate_from) * t
        return rate

    def bake_spin(self, frame_start: int, frame_end: int, fps: int, step: int = 2) -> None:
        """Integrate the rotation speed over time into keyframes (exact for any speed profile)."""
        angle = 0.0
        for frame in range(frame_start, frame_end + step, step):
            key(self.spinner, "rotation_euler", frame, (0, 0, math.radians(angle)))
            if self.clouds is not None:
                key(self.clouds, "rotation_euler", frame, (0, 0, math.radians(angle * 0.15)))
            angle += self.rate_at(frame + step / 2) * step / fps
        set_interpolation(self.spinner, "LINEAR")
        if self.clouds is not None:
            set_interpolation(self.clouds, "LINEAR")

    def scale_to(self, start: int, end: int, factor: float, current: float) -> None:
        key(self.root, "scale", start, (current,) * 3)
        key(self.root, "scale", end, (factor,) * 3)


def planet(
    name: str, location, radius: float = 1.0, kind: str = "earth", spin_rate: float = 0.0, tilt: float = 23.4
) -> Planet:
    col = objects.collection(name)
    root = objects.empty(f"{name}_root", location=location, col=col)
    root.rotation_euler = (math.radians(tilt if kind == "earth" else 0), 0, 0)
    spinner = objects.empty(f"{name}_spin", parent=root, col=col)
    if kind == "sun":
        objects.mesh_object(
            f"{name}_body", objects.sphere(radius, 64, 32), _sun_material(f"{name}_sun"), True, parent=spinner, col=col
        )
        lights.point(f"{name}_glow", (0, 0, 0), "#ffd9a0", 2000 * radius * radius, radius=radius, parent=root)
        return Planet(name, tuple(location), root, spinner, None, spin_rate)
    objects.mesh_object(
        f"{name}_body",
        objects.sphere(radius, 96, 48),
        _surface_material(f"{name}_surface", kind, radius),
        True,
        parent=spinner,
        col=col,
    )
    clouds = None
    if kind == "earth":
        clouds = objects.empty(f"{name}_clouds_spin", parent=spinner, col=col)
        objects.mesh_object(
            f"{name}_clouds",
            objects.sphere(radius * 1.012, 96, 48),
            _clouds_material(f"{name}_c", radius),
            True,
            parent=clouds,
            col=col,
        )
        objects.mesh_object(
            f"{name}_atmosphere",
            objects.sphere(radius * 1.035, 96, 48),
            _atmosphere_material(f"{name}_a"),
            True,
            parent=root,
            col=col,
        )
    return Planet(name, tuple(location), root, spinner, clouds, spin_rate)
