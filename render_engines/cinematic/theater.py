"""A Broadway-style theatre: raked rows of red seats full of people, a stage with a golden proscenium, red
curtains, footlights, spotlights and a glowing marquee sign above the stage.

Layout: the stage is at the north end (y in [4, 10], height 1.1); seats fill y in [-9.5, 2.5] with a centre
aisle at x = 0; the entrance doors are at the back (y = -12). A performer can stand on the stage at
(0, 6.5, 1.1).
"""

from __future__ import annotations

import math
import random

from mathutils import Matrix

from render_engines.cinematic import ads
from render_engines.cinematic.crowd import audience_row
from render_engines.cinematic.urban import Urban, _box, _mat, _sky, compound
from render_engines.core.blender import lights, objects

STAGE_Y, STAGE_H = 4.0, 1.1


def build_theater(env: dict, ctx, scene, seed: int) -> Urban:
    rng = random.Random(seed)
    urban = Urban()
    col = objects.collection("Theater")
    carpet = _mat("theater_carpet", "#5a1420", 0.95)
    wall = _mat("theater_wall", "#3a1218", 0.9)
    gold = _mat("theater_gold", "#c9a227", 0.3, metallic=0.9)
    wood = _mat("stage_wood", "#6b4224", 0.5)
    velvet = _mat("seat_velvet", "#9e1b2b", 0.9)
    curtain = _mat("curtain_red", "#a3101e", 0.85)
    dark = _mat("theater_dark", "#120a0c", 0.9)

    urban.static = [objects.mesh_object("t_floor", _box(20, 26, 0.1, (0, -3, -0.05)), carpet, col=col)]
    for at, size in (((-10, -3, 5), (0.2, 26, 10)), ((10, -3, 5), (0.2, 26, 10)), ((0, -13, 5), (20, 0.2, 10))):
        urban.static.append(objects.mesh_object(f"t_wall_{at[0]}_{at[1]}", _box(*size, at), wall, col=col))
    objects.mesh_object("t_ceiling", _box(20, 26, 0.2, (0, -3, 10)), dark, col=col)

    # Stage, apron trim and footlights.
    urban.static.append(
        objects.mesh_object("t_stage", _box(16, 6, STAGE_H, (0, STAGE_Y + 3, STAGE_H / 2)), wood, col=col)
    )
    objects.mesh_object("t_apron", _box(16.2, 0.12, 0.12, (0, STAGE_Y - 0.02, STAGE_H)), gold, col=col)
    foot = ads.glow("footlight", "#ffd9a0", 6.0)
    compound(
        "t_footlights",
        [
            (
                objects.transform(objects.sphere(0.06, 10, 6), Matrix.Translation((x, STAGE_Y + 0.15, STAGE_H + 0.05))),
                foot,
            )
            for x in [i * 0.8 - 7.2 for i in range(19)]
        ],
        col=col,
    )
    # Back curtain and the golden proscenium arch.
    objects.mesh_object(
        "t_back_curtain", _box(16, 0.2, 9, (0, 9.6, 4.5)), _mat("curtain_back", "#5c0a14", 0.9), col=col
    )
    for sx in (-1, 1):
        objects.mesh_object(f"t_column_{sx}", _box(1.0, 0.8, 8.5, (sx * 8.2, STAGE_Y, 4.25)), gold, col=col)
        folds = []
        for k in range(9):  # side curtain made of pleats
            x = sx * (8.0 - k * 0.42)
            depth = 0.18 if k % 2 else 0.05
            folds.append(
                (
                    objects.transform(
                        objects.box(0.45, 0.25, 7.6), Matrix.Translation((x, STAGE_Y + 0.4 + depth, STAGE_H + 3.8))
                    ),
                    curtain,
                )
            )
        compound(f"t_curtain_{sx}", folds, col=col)
    objects.mesh_object("t_arch", _box(17.4, 0.8, 1.1, (0, STAGE_Y, 8.6)), gold, col=col)
    objects.mesh_object("t_valance", _box(16, 0.4, 1.2, (0, STAGE_Y + 0.4, 7.5)), curtain, col=col)
    ads.billboard("t_sign", (0, STAGE_Y - 0.5, 9.0), 10.0, 2.2, 1, ads.musical, col)

    # Raked seating with the audience; centre aisle at x = 0.
    for row in range(12):
        y = 2.5 - row * 1.0
        z = row * env.get("rake", 0.14)
        seats = []
        x = -7.6
        while x <= 7.6:
            if abs(x) > 0.7:
                seats += [
                    (objects.transform(objects.box(0.5, 0.5, 0.12), Matrix.Translation((x, 0, 0.45))), velvet),
                    (objects.transform(objects.box(0.5, 0.1, 0.55), Matrix.Translation((x, -0.25, 0.75))), velvet),
                ]
            x += 0.6
        compound(f"t_seats_{row}", seats, (0, y, z), col=col)
        objects.mesh_object(f"t_riser_{row}", _box(16, 1.0, z + 0.01, (0, y, z / 2)), carpet, col=col)
        for side, xr in (("L", (-7.6, -0.8)), ("R", (0.8, 7.6))):
            audience_row(f"t_aud_{row}_{side}", xr, y - 0.05, z, 0.6, env.get("audience_fill", 0.85), rng, col)

    urban.sky_refs = _sky({"time_of_day": "night"}, scene)
    # Warm spotlights on the stage, dim house light, a soft fill from the stage onto the audience.
    for sx in (-1, 0, 1):
        spot = lights.area(f"t_spot_{sx}", (sx * 4.0, -2.0, 9.5), (math.radians(58), 0, 0), "#fff0d0", 4200, size=1.0)
        spot.data.shape = "DISK"
    # A bright key on the performer, footlights that really light the stage, and a wash on the back curtain.
    lights.area("t_key", (0, 1.5, 8.5), (math.radians(35), 0, 0), "#fff4e0", 3000, size=1.5)
    for x in (-5.0, 0.0, 5.0):
        lights.point(f"t_foot_{x}", (x, STAGE_Y + 0.3, STAGE_H + 0.25), "#ffd29a", 260, radius=0.3)
    lights.area("t_curtain_wash", (0, 6.0, 8.8), (math.radians(-25), 0, 0), "#ff9a7a", 1500, size=6)
    lights.area("t_house", (0, -5, 9.6), (0, 0, 0), "#ffb070", 450, size=10)
    lights.area("t_stage_glow", (0, STAGE_Y + 1, 2.5), (math.radians(-90), 0, 0), "#ffcf90", 500, size=8)
    return urban
