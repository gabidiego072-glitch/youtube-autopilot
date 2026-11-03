"""Explanatory elements: 3D arrows, labels, magnetic field lines, wind streaks and debris.
Each one exists to make a point of the narration visible."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import bpy
from mathutils import Vector

from render_engines.core.blender import materials, objects
from render_engines.core.blender.animation import key, set_interpolation
from render_engines.core.colors import hex_to_linear


def _emissive(name: str, color: str, strength: float = 2.0, alpha_fade: bool = False):
    """Flat glowing material; with alpha_fade the 'Fade' value node blends it to transparent."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.remove(nodes["Principled BSDF"])
    out = nodes["Material Output"]
    glow = nodes.new("ShaderNodeEmission")
    glow.inputs["Color"].default_value = hex_to_linear(color)
    glow.inputs["Strength"].default_value = strength
    if not alpha_fade:
        links.new(glow.outputs["Emission"], out.inputs["Surface"])
        return mat
    fade = nodes.new("ShaderNodeValue")
    fade.name = "Fade"
    fade.outputs[0].default_value = 1.0
    clear = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(fade.outputs[0], mix.inputs["Fac"])
    links.new(clear.outputs["BSDF"], mix.inputs[1])
    links.new(glow.outputs["Emission"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


@dataclass
class Explainer:
    """Common hooks: appear (scale in), fade (opacity) and an optional billboard."""

    name: str
    location: tuple
    root: object
    material: object | None = None
    focus_height: float = 0.0
    billboard: bool = False
    shown_scale: float = 1.0
    hidden_from_start: bool = False
    extra: dict = field(default_factory=dict)

    def appear(self, start: int, end: int) -> None:
        key(self.root, "scale", 1, (0.001,) * 3)
        key(self.root, "scale", start, (0.001,) * 3)
        key(self.root, "scale", end, (self.shown_scale,) * 3)

    def fade(self, start: int, end: int, to: float) -> None:
        if self.material is None or "Fade" not in self.material.node_tree.nodes:
            return
        socket = self.material.node_tree.nodes["Fade"].outputs[0]
        socket.keyframe_insert("default_value", frame=start)
        # A small flicker reads as "unstable" rather than a plain dissolve.
        steps = [(0.35, 0.6), (0.5, 0.85), (0.7, 0.45), (1.0, to)]
        for t, level in steps:
            socket.default_value = level if t < 1.0 else to
            socket.keyframe_insert("default_value", frame=round(start + (end - start) * t))

    def scale_to(self, start: int, end: int, factor: float, current: float) -> None:
        key(self.root, "scale", start, (current,) * 3)
        key(self.root, "scale", end, (factor,) * 3)


def arrow(
    name: str,
    location,
    facing_deg: float = 0.0,
    *,
    direction=(1, 0, 0),
    length: float = 1.0,
    thickness: float = 0.06,
    color: str = "#ffcc33",
    **_,
) -> Explainer:
    """Arrow from `location` along `direction` (world). Grows from its tail when it appears."""
    col = objects.collection(name)
    root = objects.empty(f"{name}_root", location=location, col=col)
    root.rotation_mode = "QUATERNION"
    root.rotation_quaternion = Vector(direction).normalized().to_track_quat("X", "Z")
    mat = _emissive(f"{name}_mat", color, 2.5, alpha_fade=True)
    head = min(length * 0.35, thickness * 5)
    shaft = objects.cone(thickness, thickness, length - head, 12, base_at_origin=True)
    objects.mesh_object(f"{name}_shaft", shaft, mat, True, rotation=(0, math.pi / 2, 0), parent=root, col=col)
    tip = objects.cone(thickness * 2.6, 0.0, head, 16, base_at_origin=True)
    objects.mesh_object(
        f"{name}_head",
        tip,
        mat,
        True,
        location=(length - head, 0, 0),
        rotation=(0, math.pi / 2, 0),
        parent=root,
        col=col,
    )
    return Explainer(name, tuple(location), root, mat)


def label(
    name: str, location, facing_deg: float = 0.0, *, text: str = "", size: float = 0.5, color: str = "#ffffff", **_
) -> Explainer:
    """3D text that always faces the camera (numbers and short facts, never full sentences)."""
    col = objects.collection(name)
    root = objects.empty(f"{name}_root", location=location, col=col)
    curve = bpy.data.curves.new(f"{name}_text", "FONT")
    curve.body = text
    curve.align_x, curve.align_y = "CENTER", "CENTER"
    curve.size = size
    curve.extrude = size * 0.04
    curve.bevel_depth = size * 0.01
    mat = _emissive(f"{name}_mat", color, 3.0, alpha_fade=True)
    curve.materials.append(mat)
    text_obj = objects.link(bpy.data.objects.new(f"{name}_obj", curve), col)
    text_obj.parent = root
    # Dark outline plate behind the text keeps it readable on any background.
    plate = materials.principled(f"{name}_plate", "#0b0f1a", roughness=1.0)
    plate_box = objects.box(size * 0.62 * max(1, len(text)), size * 1.5, size * 0.02)
    plate_obj = objects.mesh_object(
        f"{name}_plate", plate_box, plate, False, location=(0, 0, -size * 0.06), parent=root, col=col
    )
    plate_obj.visible_shadow = False
    return Explainer(name, tuple(location), root, mat, billboard=True)


def magnetic_field(
    name: str,
    location,
    facing_deg: float = 0.0,
    *,
    radius: float = 1.0,
    color: str = "#41d9ff",
    shells=(1.7, 2.4, 3.3),
    longitudes: int = 8,
    **_,
) -> Explainer:
    """Dipole field lines r = L sin^2(theta) around a planet of `radius`."""
    col = objects.collection(name)
    root = objects.empty(f"{name}_root", location=location, col=col)
    root.rotation_euler = (math.radians(11), 0, 0)  # magnetic axis is tilted ~11 degrees
    mat = _emissive(f"{name}_mat", color, 2.2, alpha_fade=True)
    curve = bpy.data.curves.new(f"{name}_lines", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = radius * 0.012
    curve.bevel_resolution = 2
    for shell in shells:
        L = shell * radius
        theta_min = math.asin(math.sqrt(radius / L))
        for k in range(longitudes):
            phi = 2 * math.pi * k / longitudes
            points = []
            for i in range(41):
                theta = theta_min + (math.pi - 2 * theta_min) * i / 40
                r = L * math.sin(theta) ** 2
                points.append(
                    (r * math.sin(theta) * math.cos(phi), r * math.sin(theta) * math.sin(phi), r * math.cos(theta))
                )
            spline = curve.splines.new("POLY")
            spline.points.add(len(points) - 1)
            for point, co in zip(spline.points, points, strict=True):
                point.co = (*co, 1.0)
    curve.materials.append(mat)
    lines = objects.link(bpy.data.objects.new(f"{name}_obj", curve), col)
    lines.parent = root
    lines.visible_shadow = False
    return Explainer(name, tuple(location), root, mat)


def wind(
    name: str,
    location,
    facing_deg: float = 0.0,
    *,
    direction_deg: float = 0.0,
    count: int = 60,
    area: float = 14.0,
    height: float = 4.0,
    debris: int = 24,
    seed: int = 0,
    **_,
) -> Explainer:
    """Wind streaks and flying debris, hidden until `start_wind` is called."""
    rng = random.Random(seed + 404)
    col = objects.collection(name)
    root = objects.empty(f"{name}_root", location=location, col=col)
    root.rotation_euler = (0, 0, math.radians(direction_deg))
    streak_mat = _emissive(f"{name}_streak", "#e8f4ff", 1.4, alpha_fade=True)
    streak_mat.node_tree.nodes["Fade"].outputs[0].default_value = 0.0
    rock = materials.principled("debris_rock", "#7d7a72", roughness=0.9)
    leaf = materials.principled("debris_leaf", "#4c7a33", roughness=0.8)
    streaks, pieces = [], []
    for i in range(count):
        length = rng.uniform(0.8, 2.6)
        bm = objects.box(length, 0.05, 0.05)
        obj = objects.mesh_object(
            f"{name}_s{i}",
            bm,
            streak_mat,
            False,
            parent=root,
            col=col,
            location=(rng.uniform(-area, area), rng.uniform(-area / 2, area / 2), rng.uniform(0.2, height)),
        )
        obj.visible_shadow = False
        streaks.append(obj)
    for i in range(debris):
        bm = objects.icosphere(rng.uniform(0.05, 0.16), 1) if i % 2 else objects.box(0.18, 0.12, 0.01)
        obj = objects.mesh_object(
            f"{name}_d{i}",
            bm,
            rock if i % 2 else leaf,
            False,
            parent=root,
            col=col,
            location=(rng.uniform(-area * 0.6, 0), rng.uniform(-3, 3), 0.05),
        )
        pieces.append(obj)
    return Explainer(
        name,
        tuple(location),
        root,
        streak_mat,
        extra={"streaks": streaks, "debris": pieces, "area": area, "seed": seed},
    )


def start_wind(explainer: Explainer, start: int, end: int, fps: int, speed: float = 22.0) -> None:
    """Streaks race along +X (in the wind's frame) and debris is swept away from `start`."""
    rng = random.Random(explainer.extra["seed"] + 9)
    area = explainer.extra["area"]
    socket = explainer.material.node_tree.nodes["Fade"].outputs[0]
    socket.default_value = 0.0
    socket.keyframe_insert("default_value", frame=start)
    socket.default_value = 0.9
    socket.keyframe_insert("default_value", frame=start + 4)
    for obj in explainer.extra["streaks"]:
        x0 = obj.location.x
        travel = speed * (end - start) / fps
        key(obj, "location", start, (x0 - area, obj.location.y, obj.location.z))
        key(obj, "location", end, (x0 - area + travel, obj.location.y, obj.location.z))
        set_interpolation(obj, "LINEAR")
    for obj in explainer.extra["debris"]:
        delay = rng.randint(0, 6)
        x0, y0, z0 = obj.location
        vx, vz = rng.uniform(speed * 0.4, speed * 0.8), rng.uniform(2.0, 6.0)
        key(obj, "location", start + delay, (x0, y0, z0))
        key(obj, "rotation_euler", start + delay, (0, 0, 0))
        for f in range(2, end - start - delay + 2, 2):
            t = f / fps
            key(
                obj,
                "location",
                start + delay + f,
                (x0 + vx * t, y0 + rng.uniform(-0.05, 0.05), max(0.05, z0 + vz * t - 2.0 * t * t)),
            )
            key(obj, "rotation_euler", start + delay + f, (t * 9, t * 6, t * 4))


EXPLAINER_BUILDERS = {"arrow": arrow, "label": label, "magnetic_field": magnetic_field, "wind": wind}
