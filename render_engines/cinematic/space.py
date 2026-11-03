"""Outer-space environment and planet props, all procedural (no textures)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import bpy

from render_engines.core.blender import lights, objects
from render_engines.core.blender.animation import key, set_interpolation
from render_engines.core.colors import hex_to_linear


def _star_image(seed: int, width: int = 4096, height: int = 2048, density: float = 0.6):
    """Equirectangular star field generated once with numpy (cheap to sample, unlike a 3D noise sky)."""
    import numpy as np

    rng = np.random.default_rng(seed)
    pixels = np.zeros((height, width, 4), dtype=np.float32)
    pixels[..., :3] = (0.006, 0.008, 0.016)  # deep blue-black
    pixels[..., 3] = 1.0
    count = int(9000 * max(0.05, density))
    ys = rng.integers(0, height, count)
    xs = rng.integers(0, width, count)
    brightness = rng.power(4.0, count) * 1.6 + 0.15
    tint = rng.uniform(0.85, 1.0, (count, 3))
    tint[:, 2] = 1.0
    pixels[ys, xs, :3] = tint * brightness[:, None]
    image = bpy.data.images.new("Stars", width, height, float_buffer=True)
    image.pixels.foreach_set(pixels.ravel())
    return image


def build_space(env: dict, scene: bpy.types.Scene, seed: int = 0) -> None:
    """Black sky with a procedural star field and a single hard sun light."""
    world = bpy.data.worlds.new("Space")
    scene.world = world
    world.use_nodes = True
    world.cycles.sampling_method = "NONE"  # the sky does not light the scene; the sun lamp does
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    stars = nodes.new("ShaderNodeTexEnvironment")
    stars.image = _star_image(seed, density=env.get("stars", 0.6))
    stars.interpolation = "Closest"
    background = nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = 1.0
    out = nodes.new("ShaderNodeOutputWorld")
    links.new(stars.outputs["Color"], background.inputs["Color"])
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
    fac = noise.outputs["Fac"]
    shift_socket = None
    if kind == "earth":
        # Ocean migration: shift > 0 pushes water towards the poles and raises land at the equator.
        sep0 = nodes.new("ShaderNodeSeparateXYZ")
        links.new(coords, sep0.inputs["Vector"])
        lat = nodes.new("ShaderNodeMath")
        lat.operation = "ABSOLUTE"
        links.new(sep0.outputs["Z"], lat.inputs[0])
        band = nodes.new("ShaderNodeMath")
        band.operation = "SUBTRACT"
        band.inputs[0].default_value = 0.42
        links.new(lat.outputs["Value"], band.inputs[1])
        shift = nodes.new("ShaderNodeValue")
        shift.name = "OceanShift"
        shift.outputs[0].default_value = 0.0
        weighted = nodes.new("ShaderNodeMath")
        weighted.operation = "MULTIPLY"
        links.new(band.outputs["Value"], weighted.inputs[0])
        links.new(shift.outputs[0], weighted.inputs[1])
        scaled_shift = nodes.new("ShaderNodeMath")
        scaled_shift.operation = "MULTIPLY"
        scaled_shift.inputs[1].default_value = 1.15
        links.new(weighted.outputs["Value"], scaled_shift.inputs[0])
        total = nodes.new("ShaderNodeMath")
        total.operation = "ADD"
        total.use_clamp = True
        links.new(fac, total.inputs[0])
        links.new(scaled_shift.outputs["Value"], total.inputs[1])
        fac = total.outputs["Value"]
        shift_socket = shift.outputs[0]
    links.new(fac, ramp.inputs["Fac"])
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
        # Clouds painted on the surface (a transparent cloud shell doubled the render time).
        cloud_noise = nodes.new("ShaderNodeTexNoise")
        cloud_noise.inputs["Scale"].default_value = 2.5
        cloud_noise.inputs["Detail"].default_value = 6.0
        links.new(coords, cloud_noise.inputs["Vector"])
        cloud_ramp = _ramp(nodes, [(0.56, "#000000"), (0.7, "#ffffff")])
        links.new(cloud_noise.outputs["Fac"], cloud_ramp.inputs["Fac"])
        clouds_mix = nodes.new("ShaderNodeMix")
        clouds_mix.data_type = "RGBA"
        clouds_mix.inputs["B"].default_value = hex_to_linear("#f4f7fb")
        links.new(cloud_ramp.outputs["Color"], clouds_mix.inputs["Factor"])
        links.new(color_out, clouds_mix.inputs["A"])
        color_out = clouds_mix.outputs["Result"]
        bsdf.inputs["Roughness"].default_value = 0.45
        # Atmosphere: blue glow towards the limb, painted on the surface (a transparent shell was 2x slower).
        rim = nodes.new("ShaderNodeLayerWeight")
        rim.inputs["Blend"].default_value = 0.4
        rim_power = nodes.new("ShaderNodeMath")
        rim_power.operation = "POWER"
        rim_power.inputs[1].default_value = 3.0
        links.new(rim.outputs["Facing"], rim_power.inputs[0])
        bsdf.inputs["Emission Color"].default_value = hex_to_linear("#4f9bff")
        rim_strength = nodes.new("ShaderNodeMath")
        rim_strength.operation = "MULTIPLY"
        rim_strength.inputs[1].default_value = 1.4
        links.new(rim_power.outputs["Value"], rim_strength.inputs[0])
        links.new(rim_strength.outputs["Value"], bsdf.inputs["Emission Strength"])
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
    mat["ocean_shift"] = shift_socket is not None
    return mat, shift_socket


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
    ocean_shift: object | None = None
    radius: float = 1.0
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

    def migrate_oceans(self, start: int, end: int, amount: float = 1.0) -> None:
        if self.ocean_shift is None:
            raise ValueError(f"'{self.name}' has no oceans to move (only kind=earth).")
        self.ocean_shift.default_value = 0.0
        self.ocean_shift.keyframe_insert("default_value", frame=start)
        self.ocean_shift.default_value = amount
        self.ocean_shift.keyframe_insert("default_value", frame=end)

    def set_oceans(self, amount: float) -> None:
        """Start the scene with oceans already moved (continuity with a previous scene)."""
        if self.ocean_shift is not None:
            self.ocean_shift.default_value = amount


def planet(
    name: str,
    location,
    radius: float = 1.0,
    kind: str = "earth",
    spin_rate: float = 0.0,
    tilt: float = 23.4,
    oceans_moved: float = 0.0,
    atmosphere: bool = True,
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
        return Planet(name, tuple(location), root, spinner, None, spin_rate, None, radius)
    material, shift_socket = _surface_material(f"{name}_surface", kind, radius)
    objects.mesh_object(f"{name}_body", objects.sphere(radius, 96, 48), material, True, parent=spinner, col=col)
    result = Planet(name, tuple(location), root, spinner, None, spin_rate, shift_socket, radius)
    result.set_oceans(oceans_moved)
    return result
