"""Interactive voxel props: treasure chest (with gem), breakable crystal block."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from render_engines.core.blender import lights, objects
from render_engines.core.blender.animation import key, set_interpolation
from render_engines.voxel.grid import VoxelGrid
from render_engines.voxel.mesh import build_voxel_object
from render_engines.voxel.models import PROP_EMISSIVE, PROP_PALETTE, WORLD_PALETTE, chest, gem

PROP_VOXEL = 1 / 8


@dataclass
class Chest:
    name: str
    location: tuple
    lid: object
    gem: object
    gem_light: object
    focus_height: float = 0.6

    def open(self, frame: int, fps: int) -> None:
        key(self.lid, "rotation_euler", frame, (0, 0, 0))
        key(self.lid, "rotation_euler", frame + 3, (math.radians(-8), 0, 0))  # rattle
        key(self.lid, "rotation_euler", frame + 5, (0, 0, 0))
        key(self.lid, "rotation_euler", frame + 14, (math.radians(-115), 0, 0))
        key(self.lid, "rotation_euler", frame + 18, (math.radians(-100), 0, 0))
        rise_start, rise_end = frame + 8, frame + 8 + fps
        key(self.gem, "location", rise_start, (0, 0, 0.3))
        key(self.gem, "scale", rise_start, (0.01, 0.01, 0.01))
        key(self.gem, "location", rise_end, (0, 0, 1.4))
        key(self.gem, "scale", rise_end, (1, 1, 1))
        key(self.gem, "rotation_euler", rise_start, (0, 0, 0))
        key(self.gem, "rotation_euler", rise_start + 4 * fps, (0, 0, math.radians(720)))
        set_interpolation(self.gem, "LINEAR", "rotation_euler")
        key(self.gem_light.data, "energy", rise_start, 0)
        key(self.gem_light.data, "energy", rise_end, 40)


def build_chest(name: str, location, facing_deg: float = 0.0, seed: int = 0) -> Chest:
    col = objects.collection(name)
    parts = chest()
    root = objects.empty(f"{name}_root", location=location, col=col)
    root.rotation_euler = (0, 0, math.radians(facing_deg))
    base = parts["base"]
    build_voxel_object(
        f"{name}_base",
        base.grid,
        PROP_PALETTE,
        voxel_size=PROP_VOXEL,
        pivot=base.pivot,
        emissive=PROP_EMISSIVE,
        jitter=0.06,
        seed=seed,
        parent=root,
        col=col,
    )
    lid_part = parts["lid"]
    hinge = tuple((a - p) * PROP_VOXEL for a, p in zip(lid_part.attach, base.pivot, strict=True))
    lid = objects.empty(f"{name}_lid_pivot", location=hinge, parent=root, col=col)
    build_voxel_object(
        f"{name}_lid",
        lid_part.grid,
        PROP_PALETTE,
        voxel_size=PROP_VOXEL,
        pivot=lid_part.pivot,
        emissive=PROP_EMISSIVE,
        jitter=0.06,
        seed=seed,
        parent=lid,
        col=col,
    )
    gem_obj = build_voxel_object(
        f"{name}_gem",
        gem(),
        PROP_PALETTE,
        voxel_size=PROP_VOXEL * 0.9,
        pivot=(0.5, 0.5, 2.5),
        emissive=PROP_EMISSIVE,
        jitter=0.0,
        parent=root,
        col=col,
    )
    gem_obj.location = (0, 0, 0.3)
    gem_obj.scale = (0.01, 0.01, 0.01)
    glow = lights.point(f"{name}_gem_light", (0, 0, 0), "#e07bff", 0.0, radius=0.1, parent=gem_obj)
    return Chest(name, tuple(location), lid, gem_obj, glow)


@dataclass
class CrystalBlock:
    name: str
    location: tuple
    block: object
    debris: list
    focus_height: float = 0.5

    def shatter(self, frame: int, fps: int, seed: int) -> None:
        key(self.block, "scale", frame - 1, (1, 1, 1))
        key(self.block, "scale", frame + 1, (1.15, 1.15, 0.8))
        key(self.block, "scale", frame + 3, (0.0, 0.0, 0.0))
        rng = random.Random(seed)
        gravity = 9.8
        for piece in self.debris:
            vx, vy, vz = rng.uniform(-2.5, 2.5), rng.uniform(-2.5, 2.5), rng.uniform(2.5, 5.0)
            spin = rng.uniform(-12, 12)
            key(piece, "scale", frame, (0, 0, 0))
            size = rng.uniform(0.6, 1.0)
            key(piece, "scale", frame + 1, (size, size, size))
            x0, y0, z0 = rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(0.2, 0.8)
            landed = False
            for f in range(0, round(fps * 1.2), 2):
                t = f / fps
                z = z0 + vz * t - 0.5 * gravity * t * t
                if z <= 0.06:
                    z, landed = 0.06, True
                key(piece, "location", frame + 1 + f, (x0 + vx * t, y0 + vy * t, z))
                key(piece, "rotation_euler", frame + 1 + f, (spin * t, spin * t * 0.5, 0))
                if landed:
                    break
            key(piece, "scale", frame + round(fps * 1.8), (size, size, size))
            key(piece, "scale", frame + round(fps * 2.3), (0, 0, 0))


def build_crystal(name: str, location, seed: int = 0, pieces: int = 14) -> CrystalBlock:
    col = objects.collection(name)
    root = objects.empty(f"{name}_root", location=location, col=col)
    cube = VoxelGrid()
    cube.fill((0, 0, 0), (7, 7, 7), "crystal")
    emissive = {"crystal": 0.6}
    block = build_voxel_object(
        f"{name}_block",
        cube,
        WORLD_PALETTE,
        voxel_size=PROP_VOXEL,
        pivot=(4, 4, 0),
        emissive=emissive,
        jitter=0.1,
        seed=seed,
        parent=root,
        col=col,
    )
    chip = VoxelGrid()
    chip.set((0, 0, 0), "crystal")
    debris = []
    for i in range(pieces):
        piece = build_voxel_object(
            f"{name}_chip_{i}",
            chip,
            WORLD_PALETTE,
            voxel_size=0.14,
            pivot=(0.5, 0.5, 0.5),
            emissive=emissive,
            jitter=0.15,
            seed=seed + i,
            parent=root,
            col=col,
        )
        piece.scale = (0, 0, 0)
        debris.append(piece)
    return CrystalBlock(name, tuple(location), block, debris)


PROP_BUILDERS = {"chest": build_chest, "crystal": build_crystal}
