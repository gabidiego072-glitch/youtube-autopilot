"""Times Square billboards built in 3D: a glowing panel plus a modelled icon (a burger, stars, a face, a
bottle) and bold 3D text. Everything is code: no photos, no AI images.

Each design is drawn in a local frame where the panel lies in the X-Z plane facing -Y (towards the street
for buildings on the north side); a parent empty places and turns it.
"""

from __future__ import annotations

import math
import os

import bpy
from mathutils import Matrix

from render_engines.core.blender import materials, objects

FONTS = (
    "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)
_FONT = None


def _font():
    global _FONT
    if _FONT is None:
        for path in FONTS:
            if os.path.isfile(path):
                _FONT = bpy.data.fonts.load(path)
                break
        else:
            _FONT = False
    return _FONT or None


def glow(name: str, color: str, strength: float = 1.6):
    return materials.principled(name, color, roughness=0.4, emission=color, emission_strength=strength)


def text(name: str, body: str, at, size: float, color: str, parent, col=None, strength: float = 2.5, align="CENTER"):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = body
    curve.size = size
    curve.extrude = 0.015
    curve.align_x, curve.align_y = align, "CENTER"
    font = _font()
    if font:
        curve.font = font
    obj = bpy.data.objects.new(name, curve)
    obj.location = at
    obj.rotation_euler = (math.radians(90), 0, 0)  # stand up, facing -Y
    obj.data.materials.append(glow(f"txt_{color}", color, strength))
    obj.parent = parent
    objects.link(obj, col)
    return obj


def _ellipsoid(r, sx, sy, sz, at):
    return objects.transform(objects.sphere(r, 20, 10), Matrix.Translation(at) @ Matrix.Diagonal((sx, sy, sz, 1)))


def _icon(name, parts, parent, col):
    from render_engines.cinematic.urban import compound

    obj = compound(name, parts, col=col, smooth=True)
    obj.parent = parent
    return obj


# --- designs: (w, h) panel size; draw icon + texts in the local frame ------------------------------
def burger(name, w, h, parent, col):
    s = min(w, h) * 0.22
    cx, cz = -w * 0.25, 0
    bun, patty = glow("ad_bun", "#e39b3d", 1.2), glow("ad_patty", "#5a2e1a", 0.8)
    cheese, lettuce = glow("ad_cheese", "#ffd23f", 1.4), glow("ad_lettuce", "#4caf50", 1.2)
    _icon(
        f"{name}_burger",
        [
            (_ellipsoid(s, 1.0, 0.35, 0.55, (cx, -0.12, cz + s * 0.55)), bun),
            (_ellipsoid(s, 1.05, 0.33, 0.14, (cx, -0.16, cz + s * 0.12)), lettuce),
            (objects.transform(objects.box(2.0 * s, 0.05, 0.12 * s), Matrix.Translation((cx, -0.17, cz))), cheese),
            (_ellipsoid(s, 1.0, 0.33, 0.2, (cx, -0.15, cz - s * 0.18)), patty),
            (_ellipsoid(s, 1.0, 0.33, 0.3, (cx, -0.12, cz - s * 0.55)), bun),
        ],
        parent,
        col,
    )
    text(f"{name}_t1", "BIG\nBURGER", (w * 0.2, -0.12, h * 0.08), h * 0.2, "#ffffff", parent, col)
    text(f"{name}_t2", "2 x 5$", (w * 0.2, -0.12, -h * 0.3), h * 0.13, "#ffe14d", parent, col)
    return "#d6461f"


def musical(name, w, h, parent, col):
    gold = glow("ad_gold", "#ffd36b", 4.0)
    parts = []
    for i in range(14):  # a frame of marquee bulbs
        t = i / 13
        for z in (h * 0.42, -h * 0.42):
            parts.append((_ellipsoid(0.08, 1, 1, 1, (-w * 0.45 + t * w * 0.9, -0.1, z)), gold))
    _icon(f"{name}_bulbs", parts, parent, col)
    text(f"{name}_t1", "EL GRAN ACTO", (0, -0.12, h * 0.12), h * 0.16, "#ffd36b", parent, col, 3.0)
    text(f"{name}_t2", "DE DESAPARICIÓN", (0, -0.12, -h * 0.12), h * 0.1, "#ffffff", parent, col)
    return "#3b1a5a"


def alert(name, w, h, parent, col):
    white = glow("ad_white", "#ffffff", 2.0)
    _icon(
        f"{name}_bars",
        [
            (objects.transform(objects.box(w * 0.9, 0.04, h * 0.05), Matrix.Translation((0, -0.1, z))), white)
            for z in (h * 0.38, -h * 0.38)
        ],
        parent,
        col,
    )
    text(f"{name}_t1", "ALERTA", (0, -0.12, h * 0.08), h * 0.3, "#ffffff", parent, col, 3.0)
    text(f"{name}_t2", "QUÉDATE EN CASA", (0, -0.12, -h * 0.22), h * 0.1, "#ffe14d", parent, col)
    return "#c4161c"


def news(name, w, h, parent, col):
    bar, tag = glow("ad_bar", "#f4f4f4", 1.6), glow("ad_tag", "#e0201c", 2.5)
    _icon(
        f"{name}_bar",
        [
            (objects.transform(objects.box(w * 0.92, 0.04, h * 0.24), Matrix.Translation((0, -0.1, -h * 0.25))), bar),
            (
                objects.transform(
                    objects.box(w * 0.3, 0.05, h * 0.16), Matrix.Translation((-w * 0.3, -0.11, h * 0.05))
                ),
                tag,
            ),
        ],
        parent,
        col,
    )
    text(f"{name}_t1", "EN DIRECTO", (-w * 0.3, -0.13, h * 0.05), h * 0.08, "#ffffff", parent, col)
    text(f"{name}_t2", "ÚLTIMA HORA: BROTE EN NUEVA YORK", (0, -0.12, -h * 0.25), h * 0.07, "#111111", parent, col, 0.3)
    return "#123a75"


def face(name, w, h, parent, col):
    skin, white = glow("ad_skin", "#f1c27d", 1.2), glow("ad_eye", "#ffffff", 2.0)
    dark, mouth = glow("ad_pupil", "#1b1b22", 0.2), glow("ad_mouth", "#c0392b", 1.5)
    r = min(w, h) * 0.3
    cx = -w * 0.22
    _icon(
        f"{name}_face",
        [
            (_ellipsoid(r, 1, 0.25, 1, (cx, -0.1, 0)), skin),
            (_ellipsoid(r * 0.18, 1, 0.3, 1, (cx - r * 0.35, -0.2, r * 0.2)), white),
            (_ellipsoid(r * 0.18, 1, 0.3, 1, (cx + r * 0.35, -0.2, r * 0.2)), white),
            (_ellipsoid(r * 0.08, 1, 0.3, 1, (cx - r * 0.35, -0.25, r * 0.2)), dark),
            (_ellipsoid(r * 0.08, 1, 0.3, 1, (cx + r * 0.35, -0.25, r * 0.2)), dark),
            (_ellipsoid(r * 0.4, 1, 0.25, 0.35, (cx, -0.2, -r * 0.4)), mouth),
        ],
        parent,
        col,
    )
    text(f"{name}_t1", "SONRÍE,\nESTÁS EN\nNUEVA YORK", (w * 0.2, -0.12, 0), h * 0.12, "#ffffff", parent, col)
    return "#0f8b8d"


def soda(name, w, h, parent, col):
    glass, cap = glow("ad_bottle", "#e8f4ff", 1.5), glow("ad_cap", "#ffd23f", 2.0)
    bh = h * 0.7
    _icon(
        f"{name}_bottle",
        [
            (
                objects.transform(
                    objects.capsule(bh * 0.13, bh * 0.75), Matrix.Translation((-w * 0.28, -0.12, bh * 0.4))
                ),
                glass,
            ),
            (
                objects.transform(
                    objects.capsule(bh * 0.05, bh * 0.2), Matrix.Translation((-w * 0.28, -0.12, bh * 0.55))
                ),
                glass,
            ),
            (_ellipsoid(bh * 0.06, 1, 0.5, 0.5, (-w * 0.28, -0.12, bh * 0.58)), cap),
        ],
        parent,
        col,
    )
    text(f"{name}_t1", "FRESCA", (w * 0.15, -0.12, h * 0.1), h * 0.22, "#ffffff", parent, col, 3.0)
    text(f"{name}_t2", "SABOR NYC", (w * 0.15, -0.12, -h * 0.2), h * 0.1, "#ffe14d", parent, col)
    return "#b3123a"


def breaking(name, w, h, parent, col):
    """A TV newsflash: a red band with ÚLTIMA HORA and the headline in big letters."""
    band = glow("ad_breaking_band", "#d7141a", 2.2)
    _icon(
        f"{name}_band",
        [(objects.transform(objects.box(w * 0.96, 0.04, h * 0.3), Matrix.Translation((0, -0.1, h * 0.27))), band)],
        parent,
        col,
    )
    text(f"{name}_t1", "ÚLTIMA HORA", (0, -0.13, h * 0.27), h * 0.2, "#ffffff", parent, col, 3.0)
    text(f"{name}_t2", "BROTE EN\nNUEVA YORK", (0, -0.12, -h * 0.17), h * 0.17, "#ffe14d", parent, col, 2.5)
    return "#0b1d3a"


DESIGNS = (burger, musical, alert, news, face, soda)


def billboard(name: str, center, w: float, h: float, side: int, design, col=None):
    """A billboard on a facade: side +1 = building north of the street (faces -Y), -1 = south (faces +Y)."""
    holder = objects.empty(f"{name}_holder", location=center, col=col)
    holder.rotation_euler = (0, 0, 0 if side > 0 else math.pi)
    background = design(name, w, h, holder, col)
    panel = objects.mesh_object(
        f"{name}_panel", objects.box(w, 0.12, h), glow(f"ad_bg_{background}", background, 1.1), col=col
    )
    panel.parent = holder
    frame = materials.principled("ad_frame", "#1a1a1e", roughness=0.4, metallic=0.6)
    border = objects.mesh_object(
        f"{name}_frame", objects.box(w + 0.3, 0.1, h + 0.3), frame, col=col, location=(0, 0.06, 0)
    )
    border.parent = holder
    return holder
