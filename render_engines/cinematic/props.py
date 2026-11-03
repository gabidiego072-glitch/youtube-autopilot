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

PROP_BUILDERS = {
    **EXPLAINER_BUILDERS,
    "lantern_post": lambda name, location, facing_deg=0.0, **_: lantern_post(name, location, facing_deg),
    "planet": _planet,
}
