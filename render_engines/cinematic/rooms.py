"""Furnished rooms for the 'interior' environment (same shell: x in [-3, 3], y in [-2.5, 2.5], height 2.7,
window in the north wall at x in [-0.9, 0.9]). The centre (|x| < 1, -1.8 < y < 0.6) is kept free for people.

Every room has loose objects (plates, chairs, books...) that physics can throw, and the colours vary with
the seed, so two kitchens never look identical.
"""

from __future__ import annotations

import math

from render_engines.cinematic.urban import Urban, _box, _cyl, _living_room, _mat, compound

# Spots the director (and the catalog text) can use for effects such as fire.
STOVE = (-2.8, 0.6, 0.95)


def _chair(name, at, wood, col, facing_y=1, rotation=(0, 0, 0)):
    back_y = -0.2 * facing_y
    return compound(
        name,
        [(_box(0.45, 0.45, 0.05, (0, 0, 0.45)), wood), (_box(0.45, 0.05, 0.5, (0, back_y, 0.7)), wood)]
        + [(_box(0.04, 0.04, 0.45, (x, y, 0.22)), wood) for x in (-0.2, 0.2) for y in (-0.2, 0.2)],
        at,
        rotation,
        col=col,
    )


def _small_items(urban: Urban, name, spots, parts, mass, col):
    """`parts` builds fresh meshes for each copy (compound consumes them)."""
    for i, at in enumerate(spots):
        urban.loose.append((compound(f"{name}_{i}", parts(), at, col=col), mass))


def kitchen(urban: Urban, rng, col) -> None:
    cabinet = _mat("cabinet", rng.choice(("#f1efe9", "#3d5a6c", "#7a8b6f", "#c9b79c", "#2f3236")), roughness=0.5)
    top = _mat("countertop", rng.choice(("#d8d4cc", "#2a2a2c", "#a88b64")), roughness=0.3)
    steel = _mat("steel", "#b9bcc0", roughness=0.25, metallic=1.0)
    black = _mat("cooktop", "#121214", roughness=0.15)
    wood = _mat("kitchen_wood", rng.choice(("#6b4a2e", "#a07850", "#4a3a2c")), roughness=0.55)
    white = _mat("crockery", "#f4f2ee", roughness=0.3)
    # Counter along the west wall, with wall cabinets above it, and the stove in it.
    counter = compound(
        "counter_west",
        [
            (_box(0.6, 4.2, 0.88, (0, 0, 0.44)), cabinet),
            (_box(0.64, 4.24, 0.04, (0, 0, 0.9)), top),
            (_box(0.35, 4.2, 0.7, (-0.12, 0, 1.85)), cabinet),
            (_box(0.56, 0.6, 0.02, (0.0, STOVE[1] - 0.3, 0.93)), black),
        ],
        (-2.8, 0.3, 0),
        col=col,
    )
    # Counter with a sink under the window's right side, and the fridge in the corner.
    sink = compound(
        "counter_north",
        [
            (_box(1.3, 0.6, 0.88, (0, 0, 0.44)), cabinet),
            (_box(1.34, 0.64, 0.04, (0, 0, 0.9)), top),
            (_box(0.5, 0.4, 0.05, (0, 0, 0.9)), steel),
            (_cyl(0.02, 0.35, (0, 0.2, 1.08)), steel),
        ],
        (1.65, 2.2, 0),
        col=col,
    )
    fridge = compound(
        "fridge",
        [(_box(0.7, 0.7, 1.85, (0, 0, 0.925)), _mat("fridge", rng.choice(("#e8e8e6", "#b9bcc0")), roughness=0.3))],
        (2.7, 1.0, 0),
        col=col,
    )
    urban.static += [counter, sink]
    urban.loose.append((fridge, 90))
    table = compound(
        "kitchen_table",
        [(_box(1.0, 0.8, 0.05, (0, 0, 0.75)), wood)]
        + [(_box(0.05, 0.05, 0.73, (x, y, 0.365)), wood) for x in (-0.45, 0.45) for y in (-0.35, 0.35)],
        (1.6, -0.9, 0),
        col=col,
    )
    urban.loose.append((table, 20))
    urban.loose += [
        (_chair(f"kitchen_chair_{i}", (1.6 + dx, -0.9 - 0.65, 0), wood, col), 5) for i, dx in enumerate((-0.25, 0.3))
    ]
    pot = compound("pot", [(_cyl(0.14, 0.16, (0, 0, 0.08)), steel)], (STOVE[0] + 0.05, STOVE[1] - 0.15, 0.94), col=col)
    pan = compound(
        "pan",
        [(_cyl(0.13, 0.04, (0, 0, 0.02)), black), (_box(0.25, 0.03, 0.02, (0.2, 0, 0.03)), black)],
        (STOVE[0] + 0.05, STOVE[1] + 0.15, 0.94),
        col=col,
    )
    urban.loose += [(pot, 2), (pan, 1)]

    def plate():
        return [(_cyl(0.11, 0.015, (0, 0, 0.008), segments=16), white)]

    def cup():
        return [(_cyl(0.04, 0.09, (0, 0, 0.045)), _mat("cup", rng.choice(("#c0392b", "#2d6b8a", "#e3b23c")), 0.4))]

    _small_items(urban, "plate", [(1.6 + dx, -0.9, 0.78) for dx in (-0.25, 0.25)], plate, 0.4, col)
    _small_items(urban, "cup", [(1.75, -0.75, 0.78), (1.3, 2.2, 0.92), (-2.7, -0.6, 0.92)], cup, 0.25, col)

    def bottle():
        return [(_cyl(0.035, 0.26, (0, 0, 0.13)), _mat("bottle", "#3f7a35", roughness=0.1))]

    _small_items(urban, "bottle", [(-2.75, -1.2, 0.92), (-2.75, -1.05, 0.92)], bottle, 0.6, col)


def bedroom(urban: Urban, rng, col) -> None:
    wood = _mat("bed_wood", rng.choice(("#6b4a2e", "#c2a37a", "#3a3430", "#e8e2d4")), roughness=0.5)
    sheet = _mat("sheet", "#f2efe9", roughness=0.9)
    duvet = _mat("duvet", rng.choice(("#3f5e7a", "#b55a4a", "#d9c06a", "#6b7f5a", "#8a6fa0")), roughness=0.95)
    bed = compound(
        "bed",
        [
            (_box(1.6, 2.1, 0.3, (0, 0, 0.15)), wood),
            (_box(1.6, 0.08, 1.0, (0, 1.05, 0.5)), wood),
            (_box(1.5, 2.0, 0.2, (0, 0, 0.4)), sheet),
            (_box(1.52, 1.4, 0.08, (0, -0.3, 0.53)), duvet),
        ],
        (1.6, 1.4, 0),
        col=col,
    )
    urban.static.append(bed)
    for i, x in enumerate((1.25, 1.95)):
        pillow = compound(f"pillow_{i}", [(_box(0.55, 0.35, 0.12, (0, 0, 0.06)), sheet)], (x, 2.15, 0.5), col=col)
        urban.loose.append((pillow, 0.5))
    stand = compound("nightstand", [(_box(0.45, 0.4, 0.5, (0, 0, 0.25)), wood)], (0.45, 2.2, 0), col=col)
    lamp = compound(
        "bedside_lamp",
        [
            (_cyl(0.06, 0.25, (0, 0, 0.125)), _mat("lamp_base", "#d9d5cc", 0.4)),
            (_cyl(0.14, 0.18, (0, 0, 0.32)), _mat("lampshade", "#f5ecd8", 0.9, emission="#ffd9a0", strength=2.0)),
        ],
        (0.45, 2.2, 0.5),
        col=col,
    )
    wardrobe = compound(
        "wardrobe",
        [(_box(0.6, 1.6, 2.1, (0, 0, 1.05)), _mat("wardrobe", rng.choice(("#e8e2d4", "#6b4a2e", "#9fa9b3")), 0.5))],
        (-2.75, 1.4, 0),
        col=col,
    )
    desk = compound("bedroom_desk", [(_box(1.1, 0.55, 0.75, (0, 0, 0.375)), wood)], (-2.65, -1.5, 0), col=col)
    rug = compound(
        "rug",
        [(_box(2.0, 1.4, 0.01, (0, 0, 0.005)), _mat("rug", rng.choice(("#b8372d", "#2d6b8a", "#c9a46b")), 1.0))],
        (0.3, -0.2, 0),
        col=col,
    )
    urban.static += [rug]
    urban.loose += [(stand, 10), (lamp, 2), (wardrobe, 70), (desk, 20)]
    urban.loose.append((_chair("bedroom_chair", (-2.1, -1.5, 0), wood, col, rotation=(0, 0, 1.57)), 5))

    def book():
        return [(_box(0.18, 0.05, 0.25, (0, 0, 0.125)), _mat("book_bed", "#1f4e8c", 0.7))]

    _small_items(urban, "bed_book", [(-2.6, -1.4, 0.76), (-2.75, -1.55, 0.76), (0.45, 2.1, 0.5)], book, 0.6, col)


def office(urban: Urban, rng, col) -> None:
    desk_mat = _mat("office_desk", rng.choice(("#d8d3c8", "#6b4a2e", "#f1efe9", "#2f3236")), roughness=0.45)
    metal = _mat("office_metal", "#5c6066", roughness=0.35, metallic=0.8)
    screen = _mat("screen", "#0d1117", roughness=0.1, emission="#4a78c2", strength=1.5)
    seat = _mat("office_seat", rng.choice(("#202226", "#2d6b8a", "#b3261e")), roughness=0.8)
    for i, x in enumerate((-1.6, 1.6)):
        desk = compound(
            f"office_desk_{i}",
            [(_box(1.5, 0.75, 0.04, (0, 0, 0.74)), desk_mat)]
            + [(_box(0.04, 0.7, 0.72, (dx, 0, 0.36)), metal) for dx in (-0.7, 0.7)],
            (x, 1.6, 0),
            col=col,
        )
        monitor = compound(
            f"monitor_{i}",
            [(_box(0.6, 0.03, 0.36, (0, 0, 0.35)), screen), (_box(0.05, 0.05, 0.16, (0, 0.03, 0.08)), metal)],
            (x, 1.8, 0.76),
            col=col,
        )
        chair = compound(
            f"office_chair_{i}",
            [
                (_box(0.5, 0.5, 0.08, (0, 0, 0.48)), seat),
                (_box(0.5, 0.06, 0.55, (0, -0.25, 0.8)), seat),
                (_cyl(0.03, 0.42, (0, 0, 0.22)), metal),
                (_cyl(0.28, 0.03, (0, 0, 0.03)), metal),
            ],
            (x, 0.9, 0),
            col=col,
        )
        urban.loose += [(desk, 30), (monitor, 5), (chair, 12)]

        def paper():
            return [(_box(0.21, 0.3, 0.03, (0, 0, 0.015)), _mat("paper", "#f7f7f2", 0.9))]

        _small_items(urban, f"papers_{i}", [(x - 0.5, 1.5, 0.76), (x + 0.45, 1.45, 0.76)], paper, 0.3, col)
    board = compound(
        "whiteboard",
        [(_box(0.03, 2.0, 1.1, (0, 0, 0)), _mat("whiteboard", "#f7f7f5", 0.2))],
        (2.93, -0.4, 1.5),
        col=col,
    )
    cabinet = compound("filing_cabinet", [(_box(0.5, 0.6, 1.3, (0, 0, 0.65)), metal)], (-2.7, -1.6, 0), col=col)
    urban.static.append(board)
    urban.loose.append((cabinet, 40))


def classroom(urban: Urban, rng, col) -> None:
    wood = _mat("school_wood", rng.choice(("#c2a37a", "#a07850")), roughness=0.55)
    frame = _mat("school_frame", rng.choice(("#2d6b8a", "#3f7a35", "#b3261e", "#5c6066")), roughness=0.4, metallic=0.5)
    board = compound(
        "blackboard",
        [
            (_box(1.9, 0.04, 1.05, (0, 0, 0)), _mat("blackboard", "#22382c", 0.8)),
            (_box(2.0, 0.06, 0.06, (0, -0.03, -0.55)), wood),
        ],
        (-1.95, 2.66, 1.5),
        col=col,
    )
    urban.static.append(board)
    teacher = compound("teacher_desk", [(_box(1.2, 0.6, 0.76, (0, 0, 0.38)), wood)], (1.9, 1.7, 0), col=col)
    urban.loose.append((teacher, 30))
    bag_colors = ("#b3261e", "#1f4e8c", "#d9a400", "#2e7d4f", "#6b3fa0")
    for row, y in enumerate((0.9, -0.3, -1.5)):
        for c, x in enumerate((-1.6, 1.6)):
            desk = compound(
                f"pupil_desk_{row}_{c}",
                [(_box(0.7, 0.5, 0.04, (0, 0, 0.68)), wood)]
                + [(_box(0.03, 0.03, 0.66, (dx, dy, 0.33)), frame) for dx in (-0.32, 0.32) for dy in (-0.22, 0.22)],
                (x, y, 0),
                col=col,
            )
            urban.loose.append((desk, 8))
            urban.loose.append((_chair(f"pupil_chair_{row}_{c}", (x, y - 0.55, 0), wood, col), 3))
            bag = compound(
                f"backpack_{row}_{c}",
                [(_box(0.3, 0.18, 0.4, (0, 0, 0.2)), _mat(f"bag_{row}{c}", bag_colors[(row * 2 + c) % 5], 0.9))],
                (x + 0.45, y - 0.2, 0),
                col=col,
            )
            urban.loose.append((bag, 2))


def cafe(urban: Urban, rng, col) -> None:
    """A New York coffee shop: counter with an espresso machine and a pastry display (west wall), a menu
    board and a TV on the north wall, hanging lamps, small round tables with cups, the street behind the window."""
    from mathutils import Matrix

    from render_engines.cinematic import ads
    from render_engines.core.blender import lights, objects

    def at(bm, loc):
        return objects.transform(bm, Matrix.Translation(loc))

    wood = _mat("cafe_wood", rng.choice(("#5a3a24", "#7a5234", "#3e2a1c")), roughness=0.45)
    top = _mat("cafe_marble", "#e8e4dc", roughness=0.25)
    chrome = _mat("cafe_chrome", "#c9ccd1", roughness=0.15, metallic=1.0)
    black = _mat("cafe_black", "#16161a", roughness=0.4)
    china = _mat("cafe_china", "#f4f1ea", roughness=0.25)
    pastry = ads.glow("cafe_display", "#ffe2b8", 1.2)
    counter = compound(
        "cafe_counter",
        [
            (_box(0.7, 3.2, 1.0, (0, 0, 0.5)), wood),
            (_box(0.8, 3.3, 0.06, (0, 0, 1.03)), top),
            (_box(0.45, 0.6, 0.5, (0, 1.0, 1.31)), chrome),  # espresso machine
            (at(objects.sphere(0.03, 8, 6), (-0.23, 1.15, 1.45)), ads.glow("cafe_led", "#ff3b30", 6.0)),
            (_box(0.55, 0.9, 0.45, (0, -0.6, 1.28)), pastry),  # lit pastry display
        ],
        (-2.6, 0.6, 0),
        col=col,
    )
    urban.static.append(counter)
    menu = objects.mesh_object("cafe_menu", _box(1.5, 0.05, 0.9, (-1.95, 2.66, 1.95)), black, col=col)
    holder = objects.empty("cafe_menu_text", location=(-1.95, 2.62, 1.95), col=col)
    ads.text("cafe_menu_t", "CAFÉ  2$\nLATTE  3$\nBAGEL  2$", (0, 0, 0), 0.13, "#fff3d6", holder, col, 1.5)
    del menu
    ads.billboard("cafe_tv", (1.85, 2.63, 1.85), 1.35, 0.78, 1, ads.breaking, col)  # the TV with the news
    for i, x in enumerate((-1.3, 0.0, 1.3)):  # hanging lamps
        lamp = compound(
            f"cafe_lamp_{i}",
            [
                (at(objects.cone(0.008, 0.008, 0.5, 6, base_at_origin=True), (0, 0, 2.2)), black),
                (at(objects.cone(0.18, 0.04, 0.2, 16, base_at_origin=True), (0, 0, 2.02)), black),
                (at(objects.sphere(0.07, 10, 6), (0, 0, 2.0)), ads.glow("cafe_bulb", "#ffd9a0", 8.0)),
            ],
            (x, 0.2, 0),
            col=col,
        )
        urban.static.append(lamp)
        lights.point(f"cafe_light_{i}", (x, 0.2, 1.95), "#ffcf90", 160, radius=0.2)
    for t, (x, y) in enumerate(((0.35, -0.75), (1.8, 0.7), (-0.9, 1.3))):  # round tables, chairs and cups
        table = compound(
            f"cafe_table_{t}",
            [
                (at(objects.cone(0.38, 0.38, 0.04, 24), (0, 0, 0.74)), top),
                (at(objects.cone(0.035, 0.035, 0.72, 8, base_at_origin=True), (0, 0, 0)), black),
                (at(objects.cone(0.22, 0.22, 0.03, 16), (0, 0, 0.015)), black),
            ],
            (x, y, 0),
            col=col,
        )
        urban.loose.append((table, 12))
        cup = compound(
            f"cafe_cup_{t}",
            [(objects.cone(0.045, 0.04, 0.09, 16, base_at_origin=True), china)],
            (x + 0.12, y + 0.08, 0.76),
            col=col,
        )
        urban.loose.append((cup, 0.3))
        for k, ang in enumerate((0.5, 3.6)):
            urban.loose.append(
                (
                    _chair(
                        f"cafe_chair_{t}_{k}",
                        (x + 0.6 * math.cos(ang), y + 0.6 * math.sin(ang), 0),
                        wood,
                        col,
                        rotation=(0, 0, ang + math.pi / 2),
                    ),
                    4,
                )
            )
    # Warm details on the walls: dark wood wainscot, framed prints, a shelf of cups behind the counter.
    for name, size, loc in (
        ("n", (6.2, 0.04, 1.0), (0, 2.68, 0.5)),
        ("e", (0.04, 5.2, 1.0), (2.98, 0, 0.5)),
        ("w", (0.04, 5.2, 1.0), (-2.98, 0, 0.5)),
    ):
        urban.static.append(objects.mesh_object(f"cafe_wainscot_{name}", _box(*size, loc), wood, col=col))
    for k, (y, design) in enumerate(((-1.4, ads.burger), (0.6, ads.musical))):
        frame = objects.empty(f"cafe_print_{k}", location=(2.95, y, 1.75), col=col)
        frame.rotation_euler = (0, 0, math.radians(90))
        ads.billboard(f"cafe_print_{k}_b", (0, 0, 0), 1.1, 0.75, 1, design, col).parent = frame
    shelf = [(_box(0.25, 2.6, 0.04, (0, 0, h)), wood) for h in (1.7, 2.1)]
    shelf += [
        (at(objects.cone(0.04, 0.035, 0.09, 12, base_at_origin=True), (0, -1.1 + i * 0.3, h + 0.02)), china)
        for h in (1.7, 2.1)
        for i in range(8)
    ]
    compound("cafe_shelf", shelf, (-2.85, 0.6, 0), col=col)
    # The street behind the window: a bright, slightly blue city backdrop.
    objects.mesh_object(
        "cafe_outside", _box(6.0, 0.05, 3.0, (0, 3.6, 1.5)), ads.glow("cafe_street", "#cfdbe8", 1.6), col=col
    )


ROOM_BUILDERS = {
    "living_room": _living_room,
    "kitchen": kitchen,
    "bedroom": bedroom,
    "office": office,
    "classroom": classroom,
    "cafe": cafe,
}
