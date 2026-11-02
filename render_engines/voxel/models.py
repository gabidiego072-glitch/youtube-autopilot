"""Voxel models for characters and props, built from boxes. Pure Python.

Each part is a VoxelGrid in its own local voxel space plus a pivot (in voxels)
that becomes the part's rotation centre in Blender.
"""

from __future__ import annotations

from dataclasses import dataclass

from render_engines.voxel.grid import VoxelGrid


@dataclass
class Part:
    name: str
    grid: VoxelGrid
    pivot: tuple[float, float, float]  # voxel coords of the joint
    attach: tuple[float, float, float]  # where the joint sits in the parent's voxel space
    parent: str | None = None


def explorer_bot() -> dict[str, Part]:
    """Original block 'explorer bot': white head with a cyan visor, orange suit, green backpack."""
    parts: dict[str, Part] = {}

    torso = VoxelGrid()
    torso.fill((0, 0, 0), (5, 3, 6), "suit")
    torso.fill((0, 0, 0), (5, 3, 0), "dark")  # belt
    torso.fill((2, -1, 3), (3, -1, 4), "emblem")  # chest light (front is -y... flipped below)
    torso.fill((1, 4, 1), (4, 5, 5), "pack")  # backpack
    parts["torso"] = Part("torso", torso, pivot=(3, 2, 0), attach=(0, 0, 12))

    head = VoxelGrid()
    head.fill((0, 0, 0), (5, 5, 5), "shell")
    head.fill((0, -1, 2), (5, -1, 3), "visor")
    head.fill((1, -1, 2), (1, -1, 2), "pupil")
    head.fill((4, -1, 2), (4, -1, 2), "pupil")
    head.fill((2, 2, 6), (2, 2, 7), "dark")
    head.set((2, 2, 8), "antenna")
    parts["head"] = Part("head", head, pivot=(3, 3, 0), attach=(3, 2, 7), parent="torso")

    for side, x in (("L", -2), ("R", 6)):
        arm = VoxelGrid()
        arm.fill((0, 0, -5), (1, 1, 0), "suit")
        arm.fill((0, 0, -6), (1, 1, -6), "metal")
        arm.fill((0, 0, -7), (1, 1, -7), "glove")
        parts[f"arm_{side}"] = Part(f"arm_{side}", arm, pivot=(1, 1, 0), attach=(x + 1, 2, 6), parent="torso")

    for side, x in (("L", 0), ("R", 3)):
        leg = VoxelGrid()
        leg.fill((0, 0, -10), (2, 2, -1), "metal")
        leg.fill((0, -1, -12), (2, 2, -11), "boot")
        parts[f"leg_{side}"] = Part(f"leg_{side}", leg, pivot=(1.5, 1.5, 0), attach=(x + 1.5, 2, 0), parent="torso")
    return parts


BOT_PALETTE = {
    "suit": "#e8742c",
    "dark": "#2b2d36",
    "emblem": "#ffd23f",
    "pack": "#3f8f5a",
    "shell": "#eef0f2",
    "visor": "#1fd1e8",
    "pupil": "#0b3b47",
    "antenna": "#ff4f6d",
    "metal": "#8a919e",
    "glove": "#e8742c",
    "boot": "#3a3f4b",
}
BOT_EMISSIVE = {"visor": 1.5, "antenna": 5.0, "emblem": 2.0}


def chest() -> dict[str, Part]:
    base = VoxelGrid()
    base.fill((0, 0, 0), (7, 5, 4), "chest_wood")
    for x in (0, 7):
        base.fill((x, 0, 0), (x, 5, 4), "chest_band")
    lid = VoxelGrid()
    lid.fill((0, -6, 0), (7, -1, 2), "chest_wood")
    for x in (0, 7):
        lid.fill((x, -6, 0), (x, -1, 2), "chest_band")
    lid.fill((3, -7, 0), (4, -7, 1), "chest_lock")
    return {
        "base": Part("base", base, pivot=(4, 3, 0), attach=(0, 0, 0)),
        "lid": Part("lid", lid, pivot=(4, -0.5, 0), attach=(4, 5.5, 5), parent="base"),
    }


def gem() -> VoxelGrid:
    g = VoxelGrid()
    for z, r in ((0, 0), (1, 1), (2, 2), (3, 1), (4, 0)):
        for x in range(-r, r + 1):
            for y in range(-r, r + 1):
                if abs(x) + abs(y) <= r:
                    g.set((x, y, z), "gem")
    return g


PROP_PALETTE = {"chest_wood": "#9a5b2e", "chest_band": "#4a4f5c", "chest_lock": "#f2c230", "gem": "#d64dff"}
PROP_EMISSIVE = {"gem": 2.0, "chest_lock": 0.3}

WORLD_PALETTE = {
    "grass": "#5fae3f",
    "dirt": "#8a5a36",
    "stone": "#8c8f94",
    "sand": "#e3d08f",
    "water": "#3c8fd8",
    "wood": "#6e4a2b",
    "planks": "#c08a52",
    "roof": "#b8443a",
    "glass": "#bfe6ff",
    "leaves": "#3f8f35",
    "stem": "#2f7a2a",
    "flower_red": "#e8414a",
    "flower_yellow": "#f5d33a",
    "flower_white": "#f4f4ee",
    "cloud": "#ffffff",
    "crystal": "#2fc7e8",
}
