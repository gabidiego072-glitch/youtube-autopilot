import math

import bpy

from render_engines.core.blender.objects import link
from render_engines.core.colors import hex_to_linear


def _light(name: str, kind: str, color: str, energy: float, location, rotation=(0, 0, 0), parent=None):
    data = bpy.data.lights.new(name, kind)
    data.color = hex_to_linear(color)[:3]
    data.energy = energy
    obj = bpy.data.objects.new(name, data)
    obj.location, obj.rotation_euler, obj.parent = location, rotation, parent
    return link(obj)


def sun(
    name: str,
    elevation_deg: float,
    azimuth_deg: float,
    color: str = "#fff4e0",
    strength: float = 3.0,
    softness_deg: float = 2.0,
):
    """Sun pointing from (azimuth, elevation) towards the origin. Matches the Nishita sky angles."""
    rotation = (math.radians(90 - elevation_deg), 0, math.radians(azimuth_deg + 90))
    obj = _light(name, "SUN", color, strength, (0, 0, 20), rotation)
    obj.data.angle = math.radians(softness_deg)
    return obj


def area(name: str, location, rotation, color: str = "#ffffff", power: float = 200.0, size: float = 4.0):
    obj = _light(name, "AREA", color, power, location, rotation)
    obj.data.size = size
    return obj


def point(name: str, location, color: str = "#ffcc88", power: float = 100.0, radius: float = 0.1, parent=None):
    obj = _light(name, "POINT", color, power, location, parent=parent)
    obj.data.shadow_soft_size = radius
    return obj
