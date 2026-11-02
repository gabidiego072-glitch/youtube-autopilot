"""Procedural voxel worlds: terrain, trees, flowers, houses and clouds. Pure Python."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from render_engines.core.noise import fbm
from render_engines.voxel.grid import VoxelGrid


@dataclass
class World:
    terrain: VoxelGrid
    clouds: VoxelGrid
    decor: VoxelGrid = field(default_factory=VoxelGrid)  # small details at DECOR_SCALE
    surface: dict[tuple[int, int], int] = field(default_factory=dict)  # (x, y) -> top z (exclusive)
    stage_height: int = 0

    def ground_z(self, x: float, y: float) -> int:
        return self.surface.get((math.floor(x), math.floor(y)), self.stage_height)


def _segment_distance(px, py, a, b) -> float:
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def generate_world(
    seed: int,
    radius: int = 26,
    stage_radius: float = 7.0,
    max_height: int = 9,
    water_level: int = -3,
    trees: int = 30,
    flowers: int = 60,
    houses: int = 1,
    paths=(),
    clear=(),
    sightlines=(),
) -> World:
    """Island-shaped terrain. The stage (around the origin) is flat with its surface at z=0.

    `paths` are flattened and kept free; `sightlines` (camera to subject) only stay free of trees and houses.
    """
    rng = random.Random(seed)
    grid, surface = VoxelGrid(), {}
    for x in range(-radius, radius + 1):
        for y in range(-radius, radius + 1):
            d = math.hypot(x, y)
            if d > radius:
                continue
            falloff = max(0.0, 1.0 - (d / radius) ** 2.2)
            n = fbm(x * 0.07, y * 0.07, seed, octaves=4)
            height = round((n - 0.42) * max_height * 1.6 * falloff + falloff * 3 - 3)
            near_path = any(_segment_distance(x, y, a, b) < 2.5 for a, b in paths)
            if d < stage_radius or near_path:
                height = 0
            elif d < stage_radius + 3 and height > 0:
                height = round(height * (d - stage_radius) / 3)
            top = height - 1
            bottom = min(top, water_level) - 3
            for z in range(bottom, top + 1):
                depth = top - z
                if top < water_level + 1 and depth == 0:
                    block = "sand"
                elif depth == 0:
                    block = "grass"
                elif depth < 3:
                    block = "dirt"
                else:
                    block = "stone"
                grid.set((x, y, z), block)
            for z in range(top + 1, water_level + 1):
                grid.set((x, y, z), "water")
            surface[(x, y)] = max(height, water_level + 1)

    def free(x, y, margin=2.0) -> bool:
        if any(_segment_distance(x, y, a, b) < margin + 1 for a, b in paths):
            return False
        if any(_segment_distance(x, y, a, b) < margin + 1.5 for a, b in sightlines):
            return False
        return all(math.hypot(x - cx, y - cy) > margin + r for cx, cy, r in clear)

    for _ in range(houses):
        hx, hy = rng.choice([(-10, 9), (10, 10), (-11, -2)])
        if free(hx, hy, 4):
            place_house(grid, surface, hx, hy, rng)
            clear = (*clear, (hx, hy, 5))

    placed, attempts = 0, 0
    while placed < trees and attempts < trees * 40:
        attempts += 1
        x, y = rng.randint(-radius + 2, radius - 2), rng.randint(-radius + 2, radius - 2)
        top = surface.get((x, y))
        if top is None or grid.get((x, y, top - 1)) != "grass" or math.hypot(x, y) < stage_radius - 1:
            continue
        if not free(x, y) or y < -6 and abs(x) < 12:  # keep the camera side open
            continue
        place_tree(grid, x, y, top, rng)
        placed += 1

    decor = VoxelGrid()
    for _ in range(flowers):
        x, y = rng.randint(-radius, radius), rng.randint(-radius, radius)
        top = surface.get((x, y))
        if top is not None and grid.get((x, y, top - 1)) == "grass" and (x, y, top) not in grid and free(x, y, 0):
            place_flower(decor, x, y, top, rng)

    return World(terrain=grid, clouds=generate_clouds(seed, radius * 2), decor=decor, surface=surface, stage_height=0)


DECOR_SCALE = 4  # decor voxels per world block


def place_flower(decor: VoxelGrid, x: int, y: int, top: int, rng: random.Random) -> None:
    """A small flower (stem + petals) standing on block (x, y), in decor voxel space."""
    s = DECOR_SCALE
    fx, fy, fz = x * s + rng.randint(0, s - 1), y * s + rng.randint(0, s - 1), top * s
    petal = rng.choice(("flower_red", "flower_yellow", "flower_white"))
    decor.set((fx, fy, fz), "stem")
    decor.set((fx, fy, fz + 1), "stem")
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        decor.set((fx + dx, fy + dy, fz + 2), petal)
    decor.set((fx, fy, fz + 2), "flower_yellow" if petal != "flower_yellow" else "flower_white")


def place_tree(grid: VoxelGrid, x: int, y: int, base_z: int, rng: random.Random) -> None:
    height = rng.randint(4, 6)
    grid.fill((x, y, base_z), (x, y, base_z + height - 1), "wood")
    crown = base_z + height - 2
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            for dz in range(0, 3):
                if abs(dx) + abs(dy) + dz > 4 or (abs(dx) == 2 and abs(dy) == 2):
                    continue
                pos = (x + dx, y + dy, crown + dz)
                if pos not in grid and rng.random() > 0.08:
                    grid.set(pos, "leaves")
    grid.set((x, y, crown + 3), "leaves")


def place_house(grid: VoxelGrid, surface: dict, cx: int, cy: int, rng: random.Random) -> None:
    w, d, h = 3, 2, 3  # half-width, half-depth, wall height
    base = max(surface.get((cx + dx, cy + dy), 0) for dx in range(-w, w + 1) for dy in range(-d, d + 1))
    grid.fill((cx - w, cy - d, base - 1), (cx + w, cy + d, base - 1), "stone")
    for z in range(base, base + h):
        for x in range(cx - w, cx + w + 1):
            for y in range(cy - d, cy + d + 1):
                edge = x in (cx - w, cx + w) or y in (cy - d, cy + d)
                if not edge:
                    continue
                corner = x in (cx - w, cx + w) and y in (cy - d, cy + d)
                grid.set((x, y, z), "wood" if corner else "planks")
    grid.remove((cx, cy - d, base))
    grid.remove((cx, cy - d, base + 1))  # door
    for wx in (cx - 2, cx + 2):
        grid.set((wx, cy - d, base + 1), "glass")
    for level in range(0, d + 2):
        z = base + h + level
        for x in range(cx - w - 1, cx + w + 2):
            for y in (cy - d - 1 + level, cy + d + 1 - level):
                grid.set((x, y, z), "roof")
        if cy - d - 1 + level >= cy + d + 1 - level:
            break
    for x in (cx - w, cx + w):
        for level in range(0, d + 1):
            for y in range(cy - d + level, cy + d - level + 1):
                grid.set((x, y, base + h + level), "planks")
    for dx in range(-w, w + 1):
        for dy in range(-d, d + 1):
            surface[(cx + dx, cy + dy)] = base


def generate_clouds(seed: int, extent: int, height: int = 16, count: int = 7) -> VoxelGrid:
    rng = random.Random(seed + 7)
    grid = VoxelGrid()
    for _ in range(count):
        cx, cy = rng.randint(-extent, extent), rng.randint(0, extent)
        sx, sy = rng.randint(3, 7), rng.randint(2, 4)
        for x in range(-sx, sx + 1):
            for y in range(-sy, sy + 1):
                if (x / sx) ** 2 + (y / sy) ** 2 <= 1.0 + rng.uniform(-0.2, 0.1):
                    grid.set((cx + x, cy + y, height), "cloud")
                    if abs(x) < sx / 2 and abs(y) < sy / 2:
                        grid.set((cx + x, cy + y, height + 1), "cloud")
    return grid
