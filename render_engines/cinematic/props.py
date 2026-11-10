"""Interactive props. Each returns an object with the hooks the director animates."""

import math
from dataclasses import dataclass

from render_engines.core.blender import lights, materials, objects
from render_engines.core.blender.animation import key


@dataclass
class LanternPost:
    name: str
    location: tuple
    glass_material: object
    light: object
    focus_height: float = 1.9

    def light_on(self, frame: int, ramp: int = 10, strength: float = 25.0, power: float = 180.0) -> None:
        socket = self.glass_material.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
        socket.default_value = 0.0
        socket.keyframe_insert("default_value", frame=frame)
        key(self.light.data, "energy", frame, 0.0)
        # Flicker into life.
        for offset, s in ((3, 0.6), (5, 0.15), (7, 0.8), (ramp, 1.0)):
            socket.default_value = strength * s
            socket.keyframe_insert("default_value", frame=frame + offset)
            key(self.light.data, "energy", frame + offset, power * s)


def lantern_post(name: str, location, facing_deg: float = 0.0) -> LanternPost:
    col = objects.collection(name)
    metal = materials.principled("iron", "#2b2b30", roughness=0.45, metallic=0.9)
    glass = materials.principled(
        f"{name}_glass", "#3a3026", roughness=0.1, emission="#ffb35c", emission_strength=0.0, transmission=0.3
    )
    root = objects.empty(f"{name}_root", location=location, col=col)
    root.rotation_euler = (0, 0, math.radians(facing_deg))
    objects.mesh_object(f"{name}_base", objects.cone(0.22, 0.16, 0.25, 16), metal, True, parent=root, col=col)
    objects.mesh_object(f"{name}_pole", objects.cone(0.05, 0.04, 2.3, 12), metal, True, parent=root, col=col)
    objects.mesh_object(
        f"{name}_arm", objects.box(0.04, 0.55, 0.04), metal, False, (0, 0.25, 2.2), parent=root, col=col
    )
    housing_z = 1.95
    objects.mesh_object(
        f"{name}_cap",
        objects.cone(0.2, 0.03, 0.18, 4),
        metal,
        False,
        (0, 0.5, housing_z + 0.15),
        rotation=(0, 0, math.radians(45)),
        parent=root,
        col=col,
    )
    objects.mesh_object(
        f"{name}_glass", objects.box(0.2, 0.2, 0.28), glass, False, (0, 0.5, housing_z), parent=root, col=col
    )
    objects.mesh_object(
        f"{name}_bottom", objects.box(0.24, 0.24, 0.04), metal, False, (0, 0.5, housing_z - 0.16), parent=root, col=col
    )
    lamp = lights.point(f"{name}_light", (0, 0.5, housing_z), "#ffb35c", 0.0, radius=0.08, parent=root)
    return LanternPost(name, tuple(location), glass, lamp)


def _planet(name, location, facing_deg=0.0, **params):
    from render_engines.cinematic.space import planet

    return planet(
        name,
        location,
        radius=params.get("radius", 1.0),
        kind=params.get("kind", "earth"),
        spin_rate=params.get("spin_rate", 0.0),
        tilt=params.get("tilt", 23.4),
        oceans_moved=params.get("oceans_moved", 0.0),
        atmosphere=params.get("atmosphere", True),
    )


from render_engines.cinematic.explainers import EXPLAINER_BUILDERS  # noqa: E402


@dataclass
class Door:
    name: str
    root: object
    hinge: object
    focus_height: float = 1.2

    def open(self, start: int, end: int, angle_deg: float = 105.0) -> None:
        """Swing the leaf open on its hinge (ease in-out)."""
        import math

        from render_engines.core.blender.animation import key

        key(self.hinge, "rotation_euler", start, (0, 0, 0))
        key(self.hinge, "rotation_euler", end, (0, 0, math.radians(angle_deg)))


def door(
    name: str,
    location,
    facing_deg: float = 0.0,
    width: float = 1.0,
    height: float = 2.2,
    color: str = "#5a3a24",
    glass: bool = True,
    light_behind: bool = True,
    col=None,
    **_,
) -> Door:
    """A door in its frame. Local frame: the doorway lies in the X-Z plane; the leaf opens towards -Y (the side
    the viewer stands on), hinged at -X. 'light_behind' puts bright daylight on the other side (+Y)."""
    import math

    from mathutils import Matrix

    from render_engines.cinematic import ads
    from render_engines.cinematic.urban import compound
    from render_engines.core.blender import materials, objects

    root = objects.empty(f"{name}_root", location=tuple(location), col=col)
    root.rotation_euler = (0, 0, math.radians(facing_deg))
    frame_mat = materials.principled(f"{name}_frame", "#2a2420", roughness=0.5)
    leaf_mat = materials.principled(f"{name}_leaf", color, roughness=0.45)
    pane = materials.principled("door_glass", "#bcd2e0", roughness=0.05, transmission=0.6)
    brass = materials.principled("door_brass", "#c9a227", roughness=0.25, metallic=1.0)

    def box(sx, sy, sz, at):
        return objects.transform(objects.box(sx, sy, sz), Matrix.Translation(at))

    frame = compound(
        f"{name}_frame",
        [
            (box(0.12, 0.2, height + 0.12, (-width / 2 - 0.06, 0, (height + 0.12) / 2)), frame_mat),
            (box(0.12, 0.2, height + 0.12, (width / 2 + 0.06, 0, (height + 0.12) / 2)), frame_mat),
            (box(width + 0.24, 0.2, 0.12, (0, 0, height + 0.06)), frame_mat),
        ],
        col=col,
    )
    frame.parent = root
    hinge = objects.empty(f"{name}_hinge", location=(-width / 2, -0.03, 0), parent=root, col=col)
    parts = [
        (box(width, 0.05, height, (width / 2, 0, height / 2)), leaf_mat),
        (box(0.05, 0.08, 0.05, (width - 0.12, -0.05, 1.05)), brass),
    ]
    if glass:
        parts.append((box(width * 0.6, 0.06, height * 0.45, (width / 2, 0, height * 0.66)), pane))
    compound(f"{name}_leaf", parts, col=col).parent = hinge
    if light_behind:  # daylight on the other side, so opening the door floods the view with light
        sky = objects.mesh_object(
            f"{name}_daylight",
            objects.box(width * 4, 0.05, height * 2.5),
            ads.glow("door_daylight", "#fff1d6", 3.0),
            location=(0, 1.2, height * 0.9),
            col=col,
        )
        sky.parent = root
    return Door(name, root, hinge)


@dataclass
class TheaterEntrance:
    name: str
    root: object
    focus_height: float = 2.5


def theater_entrance(name: str, location, facing_deg: float = 0.0, **params) -> TheaterEntrance:
    """A Broadway theatre front on the north side of a city street: marquee with bulbs, glowing doors."""
    import math

    from mathutils import Matrix

    from render_engines.cinematic import ads
    from render_engines.cinematic.urban import BUILDING_LINE, compound
    from render_engines.core.blender import materials, objects

    x = float(location[0])
    root = objects.empty(f"{name}_root", location=(x, BUILDING_LINE, 0))
    gold = materials.principled("entr_gold", "#c9a227", roughness=0.3, metallic=0.9)
    door = ads.glow("entr_door", "#ffcf8a", 2.0)
    bulb = ads.glow("entr_bulb", "#fff1c4", 6.0)
    parts = []
    for dx in (-1.5, 0.0, 1.5):  # three glowing glass doors in golden frames
        parts.append((objects.transform(objects.box(1.3, 0.1, 2.6), Matrix.Translation((dx, -0.05, 1.3))), door))
        parts.append((objects.transform(objects.box(1.45, 0.12, 0.1), Matrix.Translation((dx, -0.07, 2.65))), gold))
    for i in range(24):  # bulbs around the marquee
        t = i / 23
        parts.append(
            (objects.transform(objects.sphere(0.08, 8, 6), Matrix.Translation((-3.6 + 7.2 * t, -1.25, 3.05))), bulb)
        )
    parts.append((objects.transform(objects.box(7.6, 1.4, 0.35), Matrix.Translation((0, -0.7, 3.1))), gold))
    compound(f"{name}_front", parts, col=None).parent = root
    sign = ads.billboard(f"{name}_sign", (0, -1.45, 4.3), 7.4, 1.9, 1, ads.musical)
    sign.parent = root
    root.rotation_euler = (0, 0, math.radians(facing_deg))
    return TheaterEntrance(name, root)


@dataclass
class Bedroll:
    name: str
    root: object
    focus_height: float = 0.5


def bedroll(name: str, location, facing_deg: float = 0.0, *, seed: int = 0, **_) -> Bedroll:
    """Where someone sleeps on the street: flattened cardboard, a sleeping bag, a backpack, a paper cup.
    A character with pose 'sit' at the same location and facing sits on it (local +Y = where they face)."""
    import math
    import random

    from render_engines.cinematic.urban import _box, _cyl, _mat, compound
    from render_engines.core.blender import objects

    rng = random.Random(seed)
    card = _mat("cardboard", rng.choice(("#a47d52", "#9a7448", "#b08a5c")), roughness=0.95)
    card_dark = _mat("cardboard_dark", "#7d5c3a", roughness=0.95)
    bag = _mat(f"{name}_sleeping_bag", rng.choice(("#2f4a3a", "#3a3f5c", "#5c2f2f", "#4a4a40")), roughness=0.85)
    pack = _mat(f"{name}_backpack", rng.choice(("#2b2d33", "#5a3a28", "#3d4a2a")), roughness=0.8)
    paper = _mat("paper_cup", "#efe8da", roughness=0.6)
    root = objects.empty(f"{name}_root", location=tuple(location))
    root.rotation_euler = (0, 0, math.radians(facing_deg))
    parts = [
        (_box(2.1, 1.05, 0.025, (0.45, 0.3, 0.012)), card),
        (_box(0.9, 0.7, 0.02, (-0.55, 0.35, 0.03)), card_dark),  # a second, overlapping piece
        (_cyl(0.17, 1.15, (1.0, 0.0, 0.16), axis="X", segments=16), bag),  # the rolled sleeping bag
        (_cyl(0.21, 0.14, (1.62, 0.0, 0.16), axis="X", segments=16), bag),
        (_box(0.34, 0.2, 0.42, (-0.55, -0.12, 0.23)), pack),  # backpack against the wall
        (_box(0.28, 0.06, 0.2, (-0.55, 0.0, 0.18)), pack),
        (_cyl(0.045, 0.1, (0.05, 0.95, 0.05)), paper),  # a paper cup on the pavement in front
    ]
    compound(f"{name}_things", parts, col=None).parent = root
    return Bedroll(name, root)


@dataclass
class Model:
    name: str
    root: object
    focus_height: float = 1.0


MODEL_SHAPES = ("box", "sphere", "cylinder", "cone")
MAX_MODEL_PARTS = 60


def model(name: str, location, facing_deg: float = 0.0, *, parts=(), height: float = 1.0, **_) -> Model:
    """Any object the engine has no hand-made model for (a rocket, a dinosaur, a bus stop), designed by the AI
    from simple shapes: parts [{shape box|sphere|cylinder|cone, size [x,y,z], at [x,y,z], rotation [deg x,y,z],
    color, glow}], in metres, +Y = its front, base at z=0. It is scaled to `height` metres and stands at
    `location`, its front towards `facing_deg`."""
    import math

    from mathutils import Euler, Matrix, Vector

    from render_engines.cinematic.urban import _mat, compound
    from render_engines.core.blender import objects

    built, top = [], 0.0
    for i, part in enumerate(list(parts)[:MAX_MODEL_PARTS]):
        shape = part.get("shape", "box")
        sx, sy, sz = (max(0.005, float(v)) for v in (list(part.get("size", (0.3, 0.3, 0.3))) + [0.3] * 3)[:3])
        if shape == "sphere":
            bm = objects.transform(objects.sphere(0.5, 16, 8), Matrix.Diagonal((sx, sy, sz, 1)))
        elif shape in ("cylinder", "cone"):
            top_r = 0.5 if shape == "cylinder" else 0.0
            bm = objects.transform(
                objects.cone(0.5, top_r, 1.0, 20, base_at_origin=False), Matrix.Diagonal((sx, sy, sz, 1))
            )
        else:
            bm = objects.box(sx, sy, sz)
        rot = [math.radians(float(v)) for v in (list(part.get("rotation", (0, 0, 0))) + [0] * 3)[:3]]
        at = [float(v) for v in (list(part.get("at", (0, 0, 0))) + [0] * 3)[:3]]
        bm = objects.transform(bm, Matrix.Translation(Vector(at)) @ Euler(rot).to_matrix().to_4x4())
        top = max(top, at[2] + sz / 2)
        color = str(part.get("color") or "#9a9a9a")
        glow = float(part.get("glow", 0) or 0)
        mat = _mat(f"{name}_m{i}", color, 0.55, emission=color if glow > 0 else None, strength=min(glow, 8.0))
        built.append((bm, mat))
    root = objects.empty(f"{name}_root", location=tuple(location))
    root.rotation_euler = (0, 0, math.radians(facing_deg))
    if built:
        obj = compound(f"{name}_model", built, col=None)
        obj.parent = root
        k = max(0.01, float(height)) / max(0.05, top)
        root.scale = (k, k, k)
    return Model(name, root, focus_height=max(0.3, float(height) * 0.6))


PROP_BUILDERS = {
    "door": door,
    "theater_entrance": theater_entrance,
    **EXPLAINER_BUILDERS,
    "lantern_post": lambda name, location, facing_deg=0.0, **_: lantern_post(name, location, facing_deg),
    "planet": _planet,
    "bedroll": bedroll,
    "model": model,
}
