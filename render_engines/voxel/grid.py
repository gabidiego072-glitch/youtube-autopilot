"""Sparse voxel grid with hidden-face culling. Pure Python (no bpy).

Only faces that touch air (or a see-through block of another type) become
geometry, so large worlds stay light enough for Cycles.
"""

from __future__ import annotations

from collections.abc import Iterator

Pos = tuple[int, int, int]

# (normal, four corner offsets in counter-clockwise order seen from outside)
FACES: tuple[tuple[Pos, tuple[Pos, Pos, Pos, Pos]], ...] = (
    ((1, 0, 0), ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))),
    ((-1, 0, 0), ((0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1))),
    ((0, 1, 0), ((1, 1, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1))),
    ((0, -1, 0), ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1))),
    ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))),
    ((0, 0, -1), ((0, 1, 0), (1, 1, 0), (1, 0, 0), (0, 0, 0))),
)


class VoxelGrid:
    def __init__(self) -> None:
        self.blocks: dict[Pos, str] = {}

    def __len__(self) -> int:
        return len(self.blocks)

    def __contains__(self, pos: Pos) -> bool:
        return pos in self.blocks

    def get(self, pos: Pos) -> str | None:
        return self.blocks.get(pos)

    def set(self, pos: Pos, block: str) -> None:
        self.blocks[tuple(pos)] = block

    def remove(self, pos: Pos) -> None:
        self.blocks.pop(tuple(pos), None)

    def fill(self, lo: Pos, hi: Pos, block: str) -> None:
        """Fill the inclusive box lo..hi."""
        for x in range(lo[0], hi[0] + 1):
            for y in range(lo[1], hi[1] + 1):
                for z in range(lo[2], hi[2] + 1):
                    self.blocks[(x, y, z)] = block

    def bounds(self) -> tuple[Pos, Pos]:
        xs, ys, zs = zip(*self.blocks, strict=True) if self.blocks else ((0,), (0,), (0,))
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def exposed_faces(self, see_through: frozenset[str] = frozenset()) -> Iterator[tuple[Pos, int]]:
        for pos, block in self.blocks.items():
            x, y, z = pos
            for index, (normal, _corners) in enumerate(FACES):
                neighbor = self.blocks.get((x + normal[0], y + normal[1], z + normal[2]))
                if neighbor is None or (neighbor in see_through and neighbor != block):
                    yield pos, index


def block_hash(pos: Pos, seed: int = 0) -> float:
    """Stable 0..1 value per block, for colour jitter."""
    x, y, z = pos
    h = (x * 73856093) ^ (y * 19349663) ^ (z * 83492791) ^ (seed * 2654435761)
    h &= 0xFFFFFFFF
    h = ((h ^ (h >> 15)) * 2246822519) & 0xFFFFFFFF
    return ((h ^ (h >> 13)) & 0xFFFF) / 0xFFFF
