"""Famous cities beyond New York: Paris, Tokyo and London.

Each city has its own buildings (Haussmann stone blocks with balconies and zinc mansard roofs; narrow Tokyo
towers covered in vertical neon signs; London brick terraces with white sash windows), its own street life
(café terraces and Morris columns; vending machines, paper lanterns and overhead power lines; red phone boxes)
and vehicles (red double-decker buses and black cabs in London, small white cars in Tokyo), and its landmark
standing at the far end of the avenue in the haze: the Eiffel Tower, Tokyo Tower or Big Ben.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Matrix

from render_engines.cinematic.urban import (
    BUILDING_LINE,
    ROAD_HALF,
    _box,
    _cyl,
    _mat,
    awning,
    car,
    compound,
    facade_material,
)
from render_engines.core.blender import objects

FAMOUS = ("paris", "tokyo", "london")
HAZE = {
    "paris": {"day": "#d4dbe4", "golden": "#ecc7a0", "dusk": "#9a8fb5", "dawn": "#e0c3b3", "night": "#252a3d"},
    "tokyo": {"day": "#cdd6e0", "golden": "#e9bf98", "dusk": "#8d84b0", "dawn": "#d8bcae", "night": "#1f2236"},
    "london": {"day": "#c8ced6", "golden": "#ddbf9f", "dusk": "#8a8aa6", "dawn": "#cdb8ad", "night": "#23273a"},
}
TOKYO_SIGNS = ("RAMEN", "SUSHI", "KARAOKE", "GAMES", "HOTEL", "IZAKAYA", "CAFE", "MANGA", "UDON", "BAR")


def _t(bm, at, scale=(1, 1, 1)):
    return objects.transform(bm, Matrix.Translation(at) @ Matrix.Diagonal((*scale, 1)))


# --- buildings --------------------------------------------------------------------------------------
def building(urban, style: str, name: str, x0: float, width: float, side: int, seed: int, rng, col) -> float:
    """One building of the city's kind between x0 and x0 + width. Returns its height."""
    return {"paris": _paris, "tokyo": _tokyo, "london": _london}[style](urban, name, x0, width, side, seed, rng, col)


def _block(urban, name, cx, side, w, depth, h, mat, col, inset=0.0):
    y = side * (BUILDING_LINE + inset + depth / 2)
    obj = objects.mesh_object(name, _box(w, depth, h, (cx, y, h / 2)), mat, col=col)
    urban.static.append(obj)
    urban.buildings.append((obj, side, False))
    return obj


def _paris(urban, name, x0, width, side, seed, rng, col) -> float:
    """Haussmann block: cream stone, 6 floors, iron balconies on floors 2 and 5, a grey zinc mansard roof."""
    wall = rng.choice(("#e3d0a8", "#dcc79c", "#e8d6b2", "#d6c194"))
    mat = facade_material(f"{name}_facade", wall, seed, bay=2.4, floor_h=3.2)
    urban.facades.append(mat)
    floors, depth = 6, rng.uniform(12, 16)
    w, cx = width - 0.15, x0 + width / 2
    h = floors * 3.2
    _block(urban, name, cx, side, w, depth, h, mat, col)
    face = side * BUILDING_LINE
    out = -side
    iron = _mat("paris_iron", "#1c1d20", 0.4, metallic=0.7)
    stone = _mat(f"paris_stone_{wall}", wall, 0.8)
    zinc = _mat("paris_zinc", "#6f7680", 0.45, metallic=0.4)
    parts = []
    for floor in (2, 5):  # continuous balconies with railings
        z = floor * 3.2
        parts.append((_box(w, 0.9, 0.18, (cx, face + out * 0.45, z)), stone))
        parts.append((_box(w, 0.05, 0.95, (cx, face + out * 0.88, z + 0.55)), iron))
    for floor in (3, 4):  # a small iron balcony under every window
        for k in range(max(1, int(w // 2.4))):
            bx = x0 + 1.2 + k * 2.4
            parts.append((_box(1.5, 0.45, 0.1, (bx, face + out * 0.22, floor * 3.2)), stone))
            parts.append((_box(1.5, 0.04, 0.8, (bx, face + out * 0.44, floor * 3.2 + 0.45)), iron))
    for floor in range(1, floors + 1):  # cornice lines
        parts.append((_box(w, 0.25, 0.12, (cx, face + out * 0.12, floor * 3.2 - 0.1)), stone))
    parts.append((_box(w + 0.2, 0.6, 0.4, (cx, face + out * 0.3, h)), stone))  # top cornice
    compound(f"{name}_relief", parts, col=col)
    # Mansard roof: a sloped zinc box with dormer windows, chimneys on top.
    roof_h = 3.4
    roof = objects.cone(1.0, 0.72, roof_h, 4, base_at_origin=True)
    objects.transform(roof, Matrix.Rotation(math.radians(45), 4, "Z"))
    obj = objects.mesh_object(
        f"{name}_mansard",
        roof,
        zinc,
        location=(cx, side * (BUILDING_LINE + depth / 2), h),
        scale=(w / 1.414, depth / 1.414, 1.0),
        col=col,
    )
    urban.static.append(obj)
    dormers = []
    for k in range(max(1, int(w // 2.4))):
        dx = x0 + 1.2 + k * 2.4
        dormers.append((_box(1.0, 0.9, 1.3, (dx, face + side * 0.9, h + 1.2)), stone))
        dormers.append((_box(0.7, 0.05, 0.9, (dx, face + side * 0.44, h + 1.15)), _mat("dormer_glass", "#2b3440", 0.1)))
    for k in range(2):
        dormers.append(
            (_box(0.6, 1.4, 1.6, (x0 + 1 + k * (w - 2), side * (BUILDING_LINE + depth / 2), h + 3.6)), stone)
        )
    compound(f"{name}_dormers", dormers, col=col)
    if rng.random() < 0.45:  # a café with its red awning on the ground floor
        awning(
            f"{name}_awning", (cx, face - side * 0.02, 3.0), w * 0.8, rng.choice(("#a3161e", "#1d4d3a", "#8a1c2b")), col
        )
    return h + roof_h


def _tokyo(urban, name, x0, width, side, seed, rng, col) -> float:
    """Narrow Tokyo building: tiles or concrete, 5-14 floors, covered in vertical glowing signs."""
    wall = rng.choice(("#c9c5bd", "#9aa0a6", "#e4e0d6", "#6d7378", "#b7a99a", "#d6d2c8"))
    mat = facade_material(f"{name}_facade", wall, seed, bay=1.8, floor_h=3.0)
    urban.facades.append(mat)
    floors = rng.randint(5, 14)
    h = floors * 3.0 + 0.4
    w, cx = width - 0.2, x0 + width / 2
    _block(urban, name, cx, side, w, rng.uniform(10, 14), h, mat, col)
    face = side * BUILDING_LINE
    for k in range(rng.randint(1, 3)):  # stacked blade signs, the Shinjuku look
        x = x0 + rng.uniform(0.6, width - 0.6)
        z = rng.uniform(4.0, min(h - 6, 18))
        _vertical_sign(f"{name}_sign{k}", (x, face, z), side, rng.choice(TOKYO_SIGNS), rng, col)
    if rng.random() < 0.5:  # a lit box sign across the facade
        from render_engines.cinematic import ads

        panel = rng.choice(("#ff3b5c", "#ffd23f", "#2ec4ff", "#ffffff"))
        objects.mesh_object(
            f"{name}_banner",
            _box(w * 0.8, 0.12, 1.2, (cx, face - side * 0.1, rng.uniform(4.5, 9.0))),
            ads.glow(f"tokyo_banner_{panel}", panel, 1.4),
            col=col,
        )
    return h


def _london(urban, name, x0, width, side, seed, rng, col) -> float:
    """Victorian terrace: dark red or yellow brick, white window frames and cornice, chimney stacks."""
    wall = rng.choice(("#8a4433", "#9c5a3c", "#c9a66b", "#7a3f30", "#b58d5c"))
    mat = facade_material(f"{name}_facade", wall, seed, bay=2.0, floor_h=3.1)
    urban.facades.append(mat)
    floors = rng.randint(3, 5)
    h = floors * 3.1 + 0.4
    w, cx = width - 0.15, x0 + width / 2
    depth = rng.uniform(10, 14)
    _block(urban, name, cx, side, w, depth, h, mat, col)
    face = side * BUILDING_LINE
    out = -side
    white = _mat("london_white", "#f1eee6", 0.6)
    parts = [(_box(w + 0.1, 0.4, 0.45, (cx, face + out * 0.2, h)), white)]
    for floor in range(1, floors + 1):
        parts.append((_box(w, 0.18, 0.12, (cx, face + out * 0.09, floor * 3.1)), white))
    for k in range(2):  # chimney stacks with pots
        x = x0 + 0.8 + k * (w - 1.6)
        parts.append(
            (_box(0.9, 0.7, 1.6, (x, side * (BUILDING_LINE + depth / 2), h + 0.8)), _mat(f"chim_{wall}", wall, 0.8))
        )
        parts.append(
            (_cyl(0.12, 0.5, (x, side * (BUILDING_LINE + depth / 2), h + 1.85)), _mat("chim_pot", "#a5583a", 0.8))
        )
    compound(f"{name}_relief", parts, col=col)
    if rng.random() < 0.5:
        awning(
            f"{name}_awning",
            (cx, face - side * 0.02, 3.0),
            w * 0.75,
            rng.choice(("#1d3b5a", "#2d5a3a", "#5a1d2b")),
            col,
        )
    return h


def _vertical_sign(name, at, side, word, rng, col):
    from render_engines.cinematic import ads

    x, face, z0 = at
    height = 0.5 * len(word) + 0.6
    colour = rng.choice(("#ff2d55", "#ffcc00", "#00c2ff", "#ff7a00", "#ff4fd8", "#2ee59d", "#ffffff"))
    holder = objects.empty(f"{name}_holder", location=(x, face - side * 0.7, z0 + height / 2), col=col)
    panel = objects.mesh_object(
        f"{name}_panel", _box(0.22, 0.95, height), ads.glow(f"sign_{colour}", colour, 1.8), col=col
    )
    panel.parent = holder
    text_colour = "#111111" if colour in ("#ffffff", "#ffcc00", "#2ee59d") else "#ffffff"
    for sx in (-1, 1):
        curve = bpy.data.curves.new(f"{name}_t{sx}", "FONT")
        curve.body = "\n".join(word)
        curve.size = 0.45
        curve.space_line = 0.85
        curve.extrude = 0.01
        curve.align_x, curve.align_y = "CENTER", "CENTER"
        font = ads._font()
        if font:
            curve.font = font
        txt = bpy.data.objects.new(f"{name}_t{sx}", curve)
        txt.location = (sx * 0.12, 0, 0)
        txt.rotation_euler = (math.radians(90), 0, math.radians(90 * sx))
        txt.data.materials.append(
            ads.glow(f"sign_text_{text_colour}", text_colour, 3.0 if text_colour == "#ffffff" else 0.2)
        )
        txt.parent = holder
        objects.link(txt, col)


# --- street life ------------------------------------------------------------------------------------
def street_life(urban, style: str, length: float, rng, col, coast: bool) -> None:
    sides = (1,) if coast else (1, -1)
    if style == "london":
        red = _mat("phone_box_red", "#c8102e", 0.4)
        glass = _mat("phone_box_glass", "#d8e4ea", 0.1)
        for i, x in enumerate(range(-int(length) + 18, int(length), 31)):
            side = sides[i % len(sides)]
            compound(
                f"phone_box_{i}",
                [
                    (_box(0.95, 0.95, 2.5, (0, 0, 1.25)), red),
                    (_box(0.8, 0.97, 1.6, (0, 0, 1.25)), glass),
                    (_box(1.05, 1.05, 0.2, (0, 0, 2.6)), red),
                ],
                (x, side * (ROAD_HALF + 1.0), 0),
                col=col,
            )
    elif style == "paris":
        green = _mat("morris_green", "#2f4f3a", 0.5)
        poster = _mat("morris_poster", "#efe2c4", 0.8)
        chair = _mat("bistro_chair", "#a3161e", 0.5)
        table = _mat("bistro_table", "#c9c3b8", 0.3, metallic=0.6)
        for i, x in enumerate(range(-int(length) + 20, int(length), 34)):  # Morris advertising columns
            side = sides[i % len(sides)]
            compound(
                f"morris_{i}",
                [
                    (_cyl(0.7, 3.0, (0, 0, 1.5), segments=20), poster),
                    (objects.cone(0.85, 0.2, 0.9, 20, base_at_origin=True), green),
                ],
                (x, side * (ROAD_HALF + 1.2), 0),
                col=col,
            )
        for i, x in enumerate(range(-int(length) + 9, int(length), 13)):  # café terraces on the sidewalks
            side = sides[i % len(sides)]
            y = side * (BUILDING_LINE - 1.0)
            parts = []
            for k in range(3):
                tx = k * 1.3
                parts += [
                    (_cyl(0.32, 0.04, (tx, 0, 0.74), segments=14), table),
                    (_cyl(0.04, 0.72, (tx, 0, 0.36), segments=8), table),
                    (_box(0.4, 0.4, 0.45, (tx - 0.45, 0, 0.22)), chair),
                    (_box(0.4, 0.4, 0.45, (tx + 0.45, 0, 0.22)), chair),
                ]
            compound(f"terrace_{i}", parts, (x, y, 0), col=col)
    elif style == "tokyo":
        pole = _mat("utility_pole", "#8f8b84", 0.8)
        wire = _mat("power_wire", "#141414", 0.6)
        lantern = _mat("lantern_red", "#d1232a", 0.6, emission="#ff4a3a", strength=1.2)
        for side in sides:  # concrete utility poles and the tangle of overhead wires
            xs = list(range(-int(length) + 6, int(length), 14))
            for x in xs:
                compound(
                    f"pole_{side}_{x}",
                    [(_cyl(0.16, 9.0, (0, 0, 4.5)), pole), (_box(0.1, 1.6, 0.1, (0, 0, 8.2)), pole)],
                    (x, side * (ROAD_HALF + 0.4), 0),
                    col=col,
                )
            for k, sag in enumerate((7.6, 8.0, 8.4)):
                objects.mesh_object(
                    f"wire_{side}_{k}",
                    _box(length * 2, 0.03, 0.03, (0, side * (ROAD_HALF + 0.4 + (k - 1) * 0.5), sag)),
                    wire,
                    col=col,
                )
        for i, x in enumerate(range(-int(length) + 5, int(length), 9)):  # glowing vending machines
            side = sides[i % len(sides)]
            colour = ("#e8eef2", "#d62828", "#1d6fb8")[i % 3]
            compound(
                f"vending_{i}",
                [
                    (
                        _box(1.0, 0.75, 1.85, (0, 0, 0.93)),
                        _mat(f"vend_{colour}", colour, 0.4, emission="#f4f8ff", strength=0.35),
                    )
                ],
                (x, side * (BUILDING_LINE - 0.45), 0),
                col=col,
            )
        for i, x in enumerate(range(-int(length) + 3, int(length), 4)):  # paper lanterns under the eaves
            side = sides[i % len(sides)]
            compound(
                f"lantern_{i}",
                [(_t(objects.sphere(0.22, 12, 8), (0, 0, 0), (1, 1, 1.4)), lantern)],
                (x, side * (BUILDING_LINE - 0.3), 3.2),
                col=col,
            )


# --- vehicles ---------------------------------------------------------------------------------------
def vehicle(style: str, name: str, location, heading: float, rng, col=None, bus: bool = True):
    """A car that belongs to the city (a red double-decker or a black cab in London...). Parked cars pass
    bus=False: a parked bus by the curb would swallow a camera standing on the sidewalk edge."""
    if style == "london":
        roll = rng.random()
        if bus and roll < 0.25:
            return double_decker(name, location, heading, col)
        return car(
            name, location, heading, "#16171a" if roll < 0.65 else rng.choice(("#7a7f86", "#e8e8e8", "#1f4e8c")), col
        )
    if style == "tokyo":
        return car(name, location, heading, rng.choice(("#f2f2f0", "#d9dcdf", "#2b2d31", "#9aa3ab", "#1f4e8c")), col)
    if style == "paris":
        return car(name, location, heading, rng.choice(("#e8e8e8", "#3a3d42", "#7a1f2b", "#2a4d7a", "#b9bcc0")), col)
    return car(name, location, heading, rng.choice(("#b3261e", "#1f4e8c", "#e8e8e8", "#202226")), col)


def double_decker(name: str, location, heading: float = 0.0, col=None):
    red = _mat("bus_red", "#c8102e", 0.35, metallic=0.2)
    glass = _mat("bus_glass", "#1a222b", 0.05)
    tyre = _mat("tyre", "#151515", 0.9)
    parts = [
        (_box(10.0, 2.5, 4.0, (0, 0, 2.35)), red),
        (_box(9.4, 2.52, 0.8, (0, 0, 1.75)), glass),
        (_box(9.4, 2.52, 0.8, (0, 0, 3.55)), glass),
        (_box(0.06, 2.0, 0.5, (5.0, 0, 4.0)), _mat("bus_sign", "#111111", 0.4, emission="#ffb300", strength=1.5)),
    ]
    for x in (-3.6, 3.4):
        for y in (-1.15, 1.15):
            parts.append((_cyl(0.5, 0.3, (x, y, 0.5), "Y", 16), tyre))
    return compound(name, parts, location, (0, 0, math.radians(heading)), col)


# --- landmarks --------------------------------------------------------------------------------------
def landmark(style: str, length: float, col) -> None:
    """The city's landmark at the far end of the avenue, big enough to read through the haze."""
    at = (length + 520.0, 30.0, 0.0)  # far away: it rises above the end of the avenue
    if style == "paris":
        _eiffel(at, col)
    elif style == "tokyo":
        _tokyo_tower(at, col)
    elif style == "london":
        _big_ben(at, col)


def _leg(p0, p1, t0, t1):
    """A tapered square beam from p0 (thickness t0) to p1 (thickness t1)."""
    import bmesh

    bm = bmesh.new()
    for (x, y, z), t in ((p0, t0), (p1, t1)):
        for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            bm.verts.new((x + dx * t / 2, y + dy * t / 2, z))
    bmesh.ops.convex_hull(bm, input=bm.verts)
    return bm


def _lattice_tower(name, at, levels, mats, col):
    """A tapering open tower: four legs leaning inwards, platforms and cross braces. levels = [(z, half width)]."""
    parts = []
    for k in range(len(levels) - 1):
        (z0, w0), (z1, w1) = levels[k], levels[k + 1]
        mat = mats[k % len(mats)]
        t0, t1 = max(0.5, w0 * 0.22), max(0.3, w1 * 0.22)
        for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            parts.append((_leg((sx * w0, sy * w0, z0), (sx * w1, sy * w1, z1), t0, t1), mat))
        zm, wm = (z0 + z1) / 2, (w0 + w1) / 2
        for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):  # X braces on each face
            a = (sx * w0 if sx else -w0, sy * w0 if sy else -w0, z0)
            b = (sx * w1 if sx else w1, sy * w1 if sy else w1, z1)
            parts.append((_leg(a, b, t1 * 0.5, t1 * 0.5), mat))
        parts.append((_box(w1 * 2 + t1 * 2, w1 * 2 + t1 * 2, max(0.6, (z1 - z0) * 0.03), (0, 0, z1)), mat))
        del zm, wm
    compound(name, parts, at, col=col)


def _eiffel(at, col):
    iron = _mat("eiffel_iron", "#6b5a45", 0.6, metallic=0.4)
    levels = [(0, 62), (57, 34), (115, 18), (200, 7), (276, 3), (300, 0.6)]
    _lattice_tower("eiffel_tower", at, levels, [iron], col)
    # The great arch between the legs at the bottom.


def _tokyo_tower(at, col):
    white = _mat("tokyo_tower_white", "#f1f1ee", 0.5)
    orange = _mat("tokyo_tower_orange", "#e8471c", 0.5, emission="#ff5a20", strength=0.3)
    levels = [(0, 40), (40, 26), (80, 16), (125, 10), (150, 7), (190, 4), (250, 1.5), (333, 0.4)]
    _lattice_tower("tokyo_tower", at, levels, [orange, white], col)


def _big_ben(at, col):
    stone = _mat("bigben_stone", "#c9b48a", 0.75)
    roof = _mat("bigben_roof", "#3b4a52", 0.5, metallic=0.4)
    face = _mat("bigben_clock", "#f6f0dc", 0.4, emission="#fff4d0", strength=1.2)
    gold = _mat("bigben_gold", "#c9a227", 0.3, metallic=0.9)
    parts = [
        (_box(14, 14, 62, (0, 0, 31)), stone),
        (_box(16, 16, 14, (0, 0, 69)), stone),
        (_box(13, 13, 8, (0, 0, 80)), stone),
        (
            objects.transform(
                objects.cone(7.5, 0.4, 20, 4, base_at_origin=True),
                Matrix.Translation((0, 0, 84)) @ Matrix.Rotation(math.radians(45), 4, "Z"),
            ),
            roof,
        ),
    ]
    for sx, sy, rot in ((0, -8.05, 0), (0, 8.05, 0), (-8.05, 0, 90), (8.05, 0, 90)):
        disc = objects.transform(
            _cyl(5.2, 0.2, (0, 0, 0), "Y", 32),
            Matrix.Translation((sx, sy, 69)) @ Matrix.Rotation(math.radians(rot), 4, "Z"),
        )
        parts.append((disc, face))
        ring = objects.transform(
            _cyl(5.7, 0.15, (0, 0, 0), "Y", 32),
            Matrix.Translation((sx * 0.995, sy * 0.995, 69)) @ Matrix.Rotation(math.radians(rot), 4, "Z"),
        )
        parts.append((ring, gold))
    for k in range(5):  # the long Parliament building beside the tower
        parts.append((_box(18, 30, 26, (-24 - k * 18, 0, 13)), stone))
        parts.append((_box(2, 2, 8, (-24 - k * 18, 14, 30)), stone))
    compound("big_ben", parts, at, col=col)


def haze_colour(style: str, time_of_day: str) -> str:
    return HAZE[style].get(time_of_day, HAZE[style]["day"])
