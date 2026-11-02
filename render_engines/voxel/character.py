"""Block character rig built from voxel parts on pivots, with game-style animation."""

from __future__ import annotations

import math
from dataclasses import dataclass

from render_engines.core.blender import objects
from render_engines.core.blender.animation import key, set_interpolation
from render_engines.voxel.mesh import build_voxel_object
from render_engines.voxel.models import BOT_EMISSIVE, BOT_PALETTE, explorer_bot

VOXEL = 1 / 16  # 16 character voxels per world block


@dataclass
class VoxelCharacter:
    name: str
    root: object
    torso: object
    head: object
    arms: dict
    legs: dict
    hip_height: float
    yaw: float = 0.0
    position: tuple = (0.0, 0.0, 0.0)

    @staticmethod
    def yaw_towards(src, dst) -> float:
        return math.atan2(dst[1] - src[1], dst[0] - src[0]) - math.pi / 2

    def set_yaw(self, frame: int, yaw: float, turn_frames: int = 5) -> None:
        delta = (yaw - self.yaw + math.pi) % (2 * math.pi) - math.pi
        key(self.root, "rotation_euler", max(1, frame - turn_frames), (0, 0, self.yaw))
        self.yaw += delta
        key(self.root, "rotation_euler", frame, (0, 0, self.yaw))

    # The model's front is -Y in part space and the body is turned 180 degrees,
    # so a forward swing is a negative X rotation in the part's local frame.
    def _swing(self, limb, frame: int, angle: float, roll: float = 0.0) -> None:
        key(limb, "rotation_euler", frame, (-angle, 0, roll))

    def walk(
        self, start: int, end: int, src, dst, fps: int, ground=lambda x, y: 0, steps_hz: float = 2.2, track=None
    ) -> None:
        src3, dst3 = (src[0], src[1], ground(*src)), (dst[0], dst[1], ground(*dst))
        self.set_yaw(start, self.yaw_towards(src3, dst3))
        key(self.root, "location", start, src3)
        key(self.root, "location", end, dst3)
        set_interpolation(self.root, "LINEAR", "location")
        if track is not None:
            track.add(start, src3)
            track.add(end, dst3)
        self.position = dst3
        step = fps / (steps_hz * 4)
        n = int((end - start) / step)
        leg, arm = math.radians(38), math.radians(34)
        for i in range(n + 1):
            frame = round(start + i * step)
            phase = math.sin(i * math.pi / 2)
            self._swing(self.legs["L"], frame, leg * phase)
            self._swing(self.legs["R"], frame, -leg * phase)
            self._swing(self.arms["L"], frame, -arm * phase)
            self._swing(self.arms["R"], frame, arm * phase)
            bob = 0.05 * abs(math.cos(i * math.pi / 2))
            key(self.torso, "location", frame, (0, 0, self.hip_height + bob))
        for limb in (*self.legs.values(), *self.arms.values()):
            self._swing(limb, end + 3, 0)
        key(self.torso, "location", end + 3, (0, 0, self.hip_height))

    def jump(self, start: int, fps: int, height: float = 0.9) -> None:
        air = round(fps * 0.5)
        h = self.hip_height
        frames = [
            (start, 0.0, (1, 1, 1)),
            (start + 4, -0.1, (1.12, 1.12, 0.85)),  # squash
            (start + 6, 0.2, (0.9, 0.9, 1.15)),  # stretch on take-off
            (start + 6 + air // 2, height, (1, 1, 1)),
            (start + 6 + air, 0.0, (1.15, 1.15, 0.82)),  # land squash
            (start + 10 + air, 0.0, (1, 1, 1)),
        ]
        for frame, lift, scale in frames:
            key(self.torso, "location", frame, (0, 0, h + lift))
            key(self.torso, "scale", frame, scale)
        for side, sign in (("L", -1), ("R", 1)):
            self._swing(self.arms[side], start + 4, 0)
            self._swing(self.arms[side], start + 6 + air // 2, math.radians(160), math.radians(25 * sign))
            self._swing(self.arms[side], start + 10 + air, 0)

    def punch(self, start: int, side: str = "R") -> int:
        """Returns the impact frame."""
        arm = self.arms[side]
        self._swing(arm, start, 0)
        self._swing(arm, start + 4, math.radians(-30))  # wind up
        self._swing(arm, start + 7, math.radians(95))  # strike
        self._swing(arm, start + 14, math.radians(95))
        self._swing(arm, start + 20, 0)
        key(self.torso, "rotation_euler", start + 4, (0, 0, math.radians(-12)))
        key(self.torso, "rotation_euler", start + 7, (0, 0, math.radians(10)))
        key(self.torso, "rotation_euler", start + 20, (0, 0, 0))
        return start + 7

    def reach(self, start: int, end: int, hold: int = 20) -> None:
        for side in ("L", "R"):
            self._swing(self.arms[side], start, 0)
            self._swing(self.arms[side], end, math.radians(70))
            self._swing(self.arms[side], end + hold, math.radians(70))
            self._swing(self.arms[side], end + hold + 8, 0)

    def wave(self, start: int, end: int, side: str = "R") -> None:
        arm, toggle, frame = self.arms[side], 1, start + 6
        self._swing(arm, start, 0)
        while frame < end - 6:
            self._swing(arm, frame, math.radians(165), math.radians(30 * toggle))
            frame += 6
            toggle *= -1
        self._swing(arm, end, 0)

    def look_at(self, start: int, point, duration: int = 12) -> None:
        yaw = (self.yaw_towards(self.position, point) - self.yaw + math.pi) % (2 * math.pi) - math.pi
        head = max(-0.9, min(0.9, yaw))
        key(self.head, "rotation_euler", start, (0, 0, 0))
        key(self.head, "rotation_euler", start + duration, (math.radians(8), 0, head))
        if abs(yaw - head) > 0.05:
            self.set_yaw(start + duration + 4, self.yaw + (yaw - head), turn_frames=duration)

    def idle(self, frame_start: int, frame_end: int, fps: int) -> None:
        """Antenna-bob style idle: a slow head nod across the whole shot."""
        period = round(fps * 1.6)
        for i, frame in enumerate(range(frame_start, frame_end + period, period // 2)):
            key(self.head, "location", frame, tuple(self.head.location[:2]) + (self._head_z + (0.012 if i % 2 else 0),))


def build_voxel_character(
    name: str, location=(0, 0, 0), facing_deg: float = 0.0, palette: dict | None = None, seed: int = 0
) -> VoxelCharacter:
    col = objects.collection(name)
    pal = {**BOT_PALETTE, **(palette or {})}
    parts = explorer_bot()
    yaw = math.radians(facing_deg)
    root = objects.empty(f"{name}_root", location=location, col=col)
    root.rotation_euler = (0, 0, yaw)
    body = objects.empty(f"{name}_body", parent=root, col=col)
    body.rotation_euler = (0, 0, math.pi)

    built = {}
    for part in parts.values():  # dict order guarantees parents first
        parent_obj = built[part.parent] if part.parent else body
        parent_pivot = parts[part.parent].pivot if part.parent else (0, 0, 0)
        loc = tuple((a - p) * VOXEL for a, p in zip(part.attach, parent_pivot, strict=True))
        pivot_obj = objects.empty(f"{name}_{part.name}_pivot", location=loc, parent=parent_obj, col=col)
        build_voxel_object(
            f"{name}_{part.name}",
            part.grid,
            pal,
            voxel_size=VOXEL,
            pivot=part.pivot,
            emissive=BOT_EMISSIVE,
            jitter=0.04,
            seed=seed,
            parent=pivot_obj,
            col=col,
        )
        built[part.name] = pivot_obj

    character = VoxelCharacter(
        name=name,
        root=root,
        torso=built["torso"],
        head=built["head"],
        arms={"L": built["arm_L"], "R": built["arm_R"]},
        legs={"L": built["leg_L"], "R": built["leg_R"]},
        hip_height=parts["torso"].attach[2] * VOXEL,
        yaw=yaw,
        position=tuple(location),
    )
    character._head_z = built["head"].location[2]
    return character
