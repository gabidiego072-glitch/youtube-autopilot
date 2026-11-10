"""Dinosaurs for the city: a Tyrannosaurus rex and a long-necked sauropod, hand-built from smooth shapes on
pivots (like the people), with scaly skin, a walk cycle, a swaying tail, a roar and a neck that feeds.

Local axes: +Y is the animal's front, +Z up, the feet on the ground at z = 0. Real sizes: the T-rex is about
12 m long with its hips 3.2 m high; the sauropod's head reaches about 12 m.
Spec (a prop): {"type": "dinosaur", "kind": "trex" | "sauropod", "location": [x, y, 0], "facing": deg,
"walk_to": [x, y] (optional), "walk_start": s, "walk_end": s, "roars": [s, ...], "feeds": true}.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from render_engines.core.blender import objects
from render_engines.core.blender.animation import key, set_interpolation

KINDS = ("trex", "sauropod")


def _skin(name: str, light: str, dark: str, belly: str | None = None):
    """Scaly skin: two-tone mottling, small scales in the bump, a paler belly."""
    import bpy

    from render_engines.core.colors import hex_to_linear

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.72
    coord = nodes.new("ShaderNodeTexCoord")
    mottle = nodes.new("ShaderNodeTexNoise")
    mottle.inputs["Scale"].default_value = 1.6
    mottle.inputs["Detail"].default_value = 6.0
    links.new(coord.outputs["Object"], mottle.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = hex_to_linear(dark)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = hex_to_linear(light)
    links.new(mottle.outputs["Fac"], ramp.inputs["Fac"])
    color = ramp.outputs["Color"]
    if belly:  # paler underneath: mix by height in the object's own space
        sep = nodes.new("ShaderNodeSeparateXYZ")
        links.new(coord.outputs["Object"], sep.inputs["Vector"])
        under = nodes.new("ShaderNodeMapRange")
        under.inputs["From Min"].default_value = 0.2
        under.inputs["From Max"].default_value = -0.6
        links.new(sep.outputs["Z"], under.inputs["Value"])
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        links.new(under.outputs["Result"], mix.inputs["Factor"])
        links.new(color, mix.inputs[6])
        mix.inputs[7].default_value = hex_to_linear(belly)
        color = mix.outputs[2]
    links.new(color, bsdf.inputs["Base Color"])
    scales = nodes.new("ShaderNodeTexVoronoi")
    scales.inputs["Scale"].default_value = 26.0
    links.new(coord.outputs["Object"], scales.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.05
    links.new(scales.outputs["Distance"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _blob(name, mat, at, scale, parent, rotation=(0, 0, 0), radius=1.0):
    return objects.mesh_object(
        name, objects.sphere(radius, 28, 14), mat, True, location=at, rotation=rotation, scale=scale, parent=parent
    )


def _cone(name, mat, at, r, h, parent, rotation=(0, 0, 0)):
    return objects.mesh_object(
        name, objects.cone(r, 0.0, h, 10, base_at_origin=True), mat, True, location=at, rotation=rotation, parent=parent
    )


@dataclass
class Dinosaur:
    name: str
    kind: str
    root: object
    hips: object
    legs: list
    tail: list
    neck: list
    head: object
    jaw: object | None
    params: dict = field(default_factory=dict)
    focus_height: float = 3.0

    def animate_scene(self, ctx, timeline=None) -> None:
        animate(self, ctx, timeline)


# --- T-rex -----------------------------------------------------------------------------------------------
def build_trex(name: str, location, facing_deg: float = 0.0, **params) -> Dinosaur:
    import bpy

    skin = _skin(f"{name}_skin", "#6b6a3c", "#3d4626", belly="#b9a77c")
    tooth = bpy.data.materials.get("dino_tooth") or _plain("dino_tooth", "#efe6cf", 0.4)
    mouth = _plain("dino_mouth", "#5a1a1c", 0.6)
    eye = _plain("dino_eye", "#d9a21a", 0.15, coat=1.0)
    pupil = _plain("dino_pupil", "#0c0c0c", 0.1)
    claw = _plain("dino_claw", "#2a2622", 0.4)

    root = objects.empty(f"{name}_root", location=tuple(location))
    root.rotation_euler = (0, 0, math.radians(facing_deg))
    hips = objects.empty(f"{name}_hips", location=(0, 0, 3.15), parent=root)
    body = objects.empty(f"{name}_body", parent=hips)
    _blob(f"{name}_pelvis", skin, (0, 0.2, 0.2), (1.05, 1.9, 1.15), body)
    _blob(f"{name}_chest", skin, (0, 1.9, 0.15), (1.1, 1.6, 1.3), body, rotation=(math.radians(10), 0, 0))
    _blob(f"{name}_back", skin, (0, 1.0, 0.75), (0.8, 2.2, 0.6), body)
    for sx in (-1, 1):  # tiny arms
        _blob(
            f"{name}_arm_{sx}",
            skin,
            (0.75 * sx, 2.75, -0.55),
            (0.14, 0.42, 0.14),
            body,
            rotation=(math.radians(-35), 0, 0),
        )
        _cone(
            f"{name}_armclaw_{sx}", claw, (0.75 * sx, 3.1, -0.85), 0.04, 0.16, body, rotation=(math.radians(150), 0, 0)
        )
    # Neck and head on pivots (the roar lifts the head and opens the jaw).
    neck = objects.empty(f"{name}_neck", location=(0, 3.0, 0.75), parent=body)
    neck.rotation_euler = (math.radians(-10), 0, 0)
    _blob(f"{name}_neck_m", skin, (0, 0.55, 0.15), (0.62, 0.95, 0.75), neck, rotation=(math.radians(25), 0, 0))
    head = objects.empty(f"{name}_head", location=(0, 1.25, 0.45), parent=neck)
    _blob(f"{name}_skull", skin, (0, 0.8, 0.05), (0.62, 1.25, 0.55), head)
    _blob(f"{name}_snout", skin, (0, 1.75, -0.08), (0.42, 0.75, 0.36), head)
    _blob(f"{name}_brow", skin, (0, 0.65, 0.42), (0.55, 0.7, 0.22), head)
    for sx in (-1, 1):
        _blob(f"{name}_eye_{sx}", eye, (0.5 * sx, 0.75, 0.3), (0.1, 0.1, 0.1), head)
        _blob(f"{name}_pupil_{sx}", pupil, (0.585 * sx, 0.78, 0.3), (0.03, 0.06, 0.08), head)
        _blob(f"{name}_brow_ridge_{sx}", skin, (0.42 * sx, 0.78, 0.43), (0.16, 0.3, 0.1), head)
        for k in range(7):  # upper teeth along the jaw line, pointing down
            y = 0.75 + k * 0.22
            x = (0.46 - k * 0.03) * sx
            _cone(f"{name}_tooth_u_{sx}_{k}", tooth, (x, y, -0.3), 0.045, 0.2, head, rotation=(math.pi, 0, 0))
    _blob(f"{name}_mouth", mouth, (0, 1.1, -0.32), (0.42, 1.05, 0.12), head)
    jaw = objects.empty(f"{name}_jaw", location=(0, 0.35, -0.3), parent=head)
    _blob(f"{name}_jaw_m", skin, (0, 0.85, -0.12), (0.5, 1.2, 0.24), jaw)
    for sx in (-1, 1):
        for k in range(6):  # lower teeth, pointing up
            _cone(f"{name}_tooth_l_{sx}_{k}", tooth, ((0.38 - k * 0.03) * sx, 0.5 + k * 0.22, 0.04), 0.04, 0.17, jaw)
    # Legs: thigh on a hip pivot, shin on a knee pivot, a three-toed foot.
    legs = []
    for sx in (-1, 1):
        hip = objects.empty(f"{name}_hip_{sx}", location=(0.78 * sx, 0.3, -0.1), parent=body)
        _blob(f"{name}_thigh_{sx}", skin, (0.08 * sx, 0.1, -0.65), (0.5, 0.85, 1.05), hip)
        knee = objects.empty(f"{name}_knee_{sx}", location=(0.05 * sx, 0.25, -1.45), parent=hip)
        objects.mesh_object(
            f"{name}_shin_{sx}",
            objects.capsule(0.24, 1.55),
            skin,
            True,
            rotation=(math.radians(-14), 0, 0),
            parent=knee,
        )
        ankle = objects.empty(f"{name}_ankle_{sx}", location=(0, -0.35, -1.45), parent=knee)
        _blob(f"{name}_foot_{sx}", skin, (0, 0.35, -0.08), (0.32, 0.6, 0.16), ankle)
        for t, dx in enumerate((-0.17, 0.0, 0.17)):
            _cone(
                f"{name}_toe_{sx}_{t}", claw, (dx, 0.95, -0.12), 0.06, 0.25, ankle, rotation=(math.radians(-80), 0, 0)
            )
        legs.append((hip, knee))
    # Tail: a chain of tapering segments, each on its own pivot so it can sway.
    tail, parent, pos = [], body, (0, -1.4, 0.25)
    segments = 9
    for k in range(segments):
        r = 0.9 - 0.82 * k / (segments - 1)
        length = 1.05
        pivot = objects.empty(f"{name}_tail_{k}", location=pos, parent=parent)
        pivot.rotation_euler = (math.radians(2.5), 0, 0)
        _blob(f"{name}_tail_m_{k}", skin, (0, -length * 0.5, 0), (r, length * 1.0, r * 0.92), pivot)
        tail.append(pivot)
        parent, pos = pivot, (0, -length * 0.95, 0)
    return Dinosaur(name, "trex", root, hips, legs, tail, [neck], head, jaw, params, focus_height=4.2)


# --- Sauropod --------------------------------------------------------------------------------------------
def build_sauropod(name: str, location, facing_deg: float = 0.0, **params) -> Dinosaur:
    skin = _skin(f"{name}_skin", "#7d8460", "#4a553f", belly="#a9a483")
    eye = _plain("dino_pupil", "#0c0c0c", 0.1)
    root = objects.empty(f"{name}_root", location=tuple(location))
    root.rotation_euler = (0, 0, math.radians(facing_deg))
    hips = objects.empty(f"{name}_hips", location=(0, 0, 5.2), parent=root)
    _blob(f"{name}_body", skin, (0, 0.3, 0.3), (1.9, 3.8, 1.9), hips, rotation=(math.radians(-8), 0, 0))
    _blob(f"{name}_withers", skin, (0, 2.4, 1.0), (1.6, 1.8, 1.5), hips)
    legs = []
    for sx in (-1, 1):
        for sy, length in ((2.3, 5.4), (-1.6, 4.9)):
            hip = objects.empty(f"{name}_leg_{sx}_{sy}", location=(1.15 * sx, sy, 0.2), parent=hips)
            objects.mesh_object(f"{name}_leg_m_{sx}_{sy}", objects.capsule(0.5, length), skin, True, parent=hip)
            _blob(f"{name}_foot_{sx}_{sy}", skin, (0, 0.1, -length + 0.25), (0.62, 0.7, 0.3), hip)
            legs.append((hip, None))
    neck, parent, pos = [], hips, (0, 3.4, 1.2)
    segments = 8
    for k in range(segments):  # many short, overlapping segments: a smooth neck, not a string of beads
        r = 1.05 - 0.65 * k / (segments - 1)
        length = 1.2
        pivot = objects.empty(f"{name}_neck_{k}", location=pos, parent=parent)
        pivot.rotation_euler = (math.radians(42 if k == 0 else 3), 0, 0)
        _blob(f"{name}_neck_m_{k}", skin, (0, length * 0.5, 0), (r, length * 1.35, r), pivot)
        neck.append(pivot)
        parent, pos = pivot, (0, length * 0.95, 0)
    head = objects.empty(f"{name}_head", location=pos, parent=parent)
    head.rotation_euler = (math.radians(-55), 0, 0)
    _blob(f"{name}_skull", skin, (0, 0.45, 0.1), (0.42, 0.75, 0.42), head)
    _blob(f"{name}_crest", skin, (0, 0.2, 0.42), (0.3, 0.35, 0.3), head)
    for sx in (-1, 1):
        _blob(f"{name}_eye_{sx}", eye, (0.36 * sx, 0.35, 0.3), (0.07, 0.07, 0.07), head)
    tail, parent, pos = [], hips, (0, -3.2, 0.2)
    segments = 9
    for k in range(segments):
        r = 1.25 - 1.15 * k / (segments - 1)
        length = 1.3
        pivot = objects.empty(f"{name}_tail_{k}", location=pos, parent=parent)
        pivot.rotation_euler = (math.radians(9 if k < 3 else 3), 0, 0)
        _blob(f"{name}_tail_m_{k}", skin, (0, -length * 0.5, 0), (r, length * 1.35, r * 0.9), pivot)
        tail.append(pivot)
        parent, pos = pivot, (0, -length * 0.95, 0)
    return Dinosaur(name, "sauropod", root, hips, legs, tail, neck, head, None, params, focus_height=9.0)


def _plain(name, color, roughness=0.5, coat=0.0):
    from render_engines.core.blender import materials

    return materials.principled(name, color, roughness=roughness, coat=coat)


def dinosaur(name: str, location, facing_deg: float = 0.0, *, kind: str = "trex", **params) -> Dinosaur:
    builder = build_sauropod if kind == "sauropod" else build_trex
    return builder(name, location, facing_deg, **params)


# --- Animation -------------------------------------------------------------------------------------------
def animate(dino: Dinosaur, ctx, timeline=None) -> None:
    """Walk (if walk_to), sway the tail, breathe, roar at the given seconds, feed (sauropod)."""
    p = dino.params
    f0, f1, fps = ctx.frame_start, ctx.frame_end, ctx.fps
    start = tuple(dino.root.location)
    walk_to = p.get("walk_to")
    ws = ctx.frame(float(p.get("walk_start", 0.0)))
    we = ctx.frame(float(p.get("walk_end", ctx.duration_seconds)))
    if walk_to:
        end = (float(walk_to[0]), float(walk_to[1]), start[2])
        yaw = math.atan2(end[1] - start[1], end[0] - start[0]) - math.pi / 2
        dino.root.rotation_euler = (0, 0, yaw)
        key(dino.root, "location", ws, start)
        key(dino.root, "location", we, end)
        set_interpolation(dino.root, "LINEAR")
        if timeline is not None and dino.name in timeline.tracks:
            timeline.tracks[dino.name].add(ws, start)
            timeline.tracks[dino.name].add(we, end)
        stride = 1.1 if dino.kind == "trex" else 1.6  # seconds per step
        _walk_cycle(dino, ws, we, round(fps * stride))
    _tail_sway(dino, f0, f1, fps)
    _breathe(dino, f0, f1, fps)
    for at in p.get("roars", []) or []:
        if dino.jaw is not None:
            _roar(dino, ctx.frame(float(at)), fps)
    if dino.kind == "sauropod" and p.get("feeds", True):
        _feed(dino, f0, f1, fps)


def _walk_cycle(dino: Dinosaur, start: int, end: int, step: int) -> None:
    swing = math.radians(24 if dino.kind == "trex" else 14)
    f, i = start, 0
    while f <= end + step:
        phase = 1 if i % 2 else -1
        for n, (hip, knee) in enumerate(dino.legs):
            side = 1 if n % 2 == 0 else -1
            if dino.kind == "sauropod":  # diagonal pairs move together
                side = 1 if n in (0, 3) else -1
            a = swing * phase * side
            key(hip, "rotation_euler", f, (a, 0, 0))
            if knee is not None:  # the knee bends while the leg comes forward
                key(knee, "rotation_euler", f, (max(0.0, -a) * 0.9, 0, 0))
        bob = 0.14 if dino.kind == "trex" else 0.08
        key(dino.hips, "location", f, (0, 0, dino.hips.location.z + (bob if i % 2 else -bob) * 0.5))
        f += step // 2
        i += 1
    for hip, knee in dino.legs:  # standing still after the walk
        key(hip, "rotation_euler", end + step, (0, 0, 0))
        if knee is not None:
            key(knee, "rotation_euler", end + step, (0, 0, 0))


def _tail_sway(dino: Dinosaur, f0: int, f1: int, fps: int) -> None:
    period = fps * (2.2 if dino.kind == "trex" else 3.4)
    amp = math.radians(7 if dino.kind == "trex" else 5)
    for k, pivot in enumerate(dino.tail):
        base = tuple(pivot.rotation_euler)
        f = f0
        while f <= f1 + period:
            a = amp * math.sin(2 * math.pi * (f - f0) / period - k * 0.7)
            key(pivot, "rotation_euler", round(f), (base[0], base[1], a))
            f += period / 8


def _breathe(dino: Dinosaur, f0: int, f1: int, fps: int) -> None:
    period = fps * 2.6
    f, i = f0, 0
    while f <= f1 + period:
        s = 0.012 if i % 2 else 0.0
        key(dino.hips, "scale", round(f), (1 + s, 1, 1 + s * 0.6))
        f += period / 2
        i += 1


def _roar(dino: Dinosaur, at: int, fps: int) -> None:
    """Head up and back, jaw wide open, a shake, then back down."""
    head, jaw, neck = dino.head, dino.jaw, dino.neck[0]
    rise, hold, fall = round(fps * 0.35), round(fps * 1.1), round(fps * 0.45)
    n0 = tuple(neck.rotation_euler)
    key(neck, "rotation_euler", at - 2, n0)
    key(neck, "rotation_euler", at + rise, (n0[0] + math.radians(22), 0, 0))
    key(head, "rotation_euler", at - 2, (0, 0, 0))
    key(head, "rotation_euler", at + rise, (math.radians(12), 0, 0))
    key(jaw, "rotation_euler", at - 2, (0, 0, 0))
    key(jaw, "rotation_euler", at + rise, (math.radians(-38), 0, 0))
    for j in range(0, hold, 3):  # the head shakes while it roars
        key(head, "rotation_euler", at + rise + j, (math.radians(12), 0, math.radians(4 if j % 2 else -4)))
    key(neck, "rotation_euler", at + rise + hold, (n0[0] + math.radians(22), 0, 0))
    key(jaw, "rotation_euler", at + rise + hold, (math.radians(-38), 0, 0))
    key(neck, "rotation_euler", at + rise + hold + fall, n0)
    key(head, "rotation_euler", at + rise + hold + fall, (0, 0, 0))
    key(jaw, "rotation_euler", at + rise + hold + fall, (0, 0, 0))


def _feed(dino: Dinosaur, f0: int, f1: int, fps: int) -> None:
    """The long neck dips to the treetops and comes back up, slowly."""
    period = fps * 4.0
    f, i = f0, 0
    bases = [tuple(p.rotation_euler) for p in dino.neck]
    while f <= f1 + period:
        dip = math.radians(-6) if i % 2 else 0.0
        for pivot, base in zip(dino.neck[1:], bases[1:], strict=True):
            key(pivot, "rotation_euler", round(f), (base[0] + dip, 0, 0))
        f += period / 2
        i += 1
