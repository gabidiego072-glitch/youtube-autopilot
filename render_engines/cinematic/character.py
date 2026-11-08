"""Stylised procedural character built from smooth primitives on a pivot hierarchy.

Local axes: +Y is forward, +Z is up. Every limb hangs from a pivot empty, so
animation is plain rotations on pivots (no armature needed).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from mathutils import Matrix

from render_engines.core.blender import materials, objects
from render_engines.core.blender.animation import key, set_interpolation

DEFAULT_PALETTE = {
    "body": "#2f5d8a",
    "skin": "#e8b48c",
    "accent": "#d94f30",
    "hair": "#3b2618",
    "boots": "#3a2a20",
    "eyes": "#1b1b22",
}

HIP_HEIGHT = 0.78

ZOMBIE_PALETTE = {
    "body": "#4f5544",  # dirty, faded clothes
    "skin": "#8ea377",  # grey-green skin
    "accent": "#6b2a26",  # dried-blood red
    "hair": "#2a2620",
    "boots": "#2b2622",
    "eyes": "#c9b13a",  # yellowish eyes
}
ZOMBIE_ARMS = math.radians(82)  # arms held forward


@dataclass
class CinematicCharacter:
    name: str
    root: object
    hips: object
    torso: object
    neck: object
    eyes: list
    arms: dict
    legs: dict
    scale: float = 1.0
    yaw: float = 0.0  # radians, current facing
    position: tuple = (0.0, 0.0, 0.0)
    busy_until: dict = field(default_factory=dict)
    zombie: bool = False

    # --- helpers ----------------------------------------------------------
    @staticmethod
    def yaw_towards(src, dst) -> float:
        return math.atan2(dst[1] - src[1], dst[0] - src[0]) - math.pi / 2

    def set_yaw(self, frame: int, yaw: float, turn_frames: int = 6) -> None:
        # Shortest rotation, keeping the euler continuous.
        delta = (yaw - self.yaw + math.pi) % (2 * math.pi) - math.pi
        key(self.root, "rotation_euler", max(1, frame - turn_frames), (0, 0, self.yaw))
        self.yaw += delta
        key(self.root, "rotation_euler", frame, (0, 0, self.yaw))

    # --- actions ----------------------------------------------------------
    def walk(self, start: int, end: int, src, dst, fps: int, stride_hz: float = 1.8, timeline_track=None) -> None:
        src3, dst3 = (src[0], src[1], 0.0), (dst[0], dst[1], 0.0)
        self.set_yaw(start, self.yaw_towards(src3, dst3))
        key(self.root, "location", start, src3)
        key(self.root, "location", end, dst3)
        set_interpolation(self.root, "LINEAR", "location")
        if timeline_track is not None:
            timeline_track.add(start, src3)
            timeline_track.add(end, dst3)
        self.position = dst3

        swing_leg, swing_arm = math.radians(28), math.radians(24)
        step = fps / (stride_hz * 4)  # quarter cycle in frames
        n = int((end - start) / step)
        for i in range(n + 1):
            frame = round(start + i * step)
            phase = math.sin(i * math.pi / 2)
            fade = min(1.0, i / 2, (n - i) / 2) if n >= 4 else 1.0
            key(self.legs["L"], "rotation_euler", frame, (swing_leg * phase * fade, 0, 0))
            key(self.legs["R"], "rotation_euler", frame, (-swing_leg * phase * fade, 0, 0))
            if self.zombie:  # arms stretched forward, swaying; a lurching, uneven gait
                sway = 0.25 * swing_arm * phase
                key(self.arms["L"], "rotation_euler", frame, (ZOMBIE_ARMS - sway, 0, math.radians(-6)))
                key(self.arms["R"], "rotation_euler", frame, (ZOMBIE_ARMS + sway, 0, math.radians(6)))
                key(self.hips, "rotation_euler", frame, (0, math.radians(7) * phase, 0))
            else:
                key(self.arms["L"], "rotation_euler", frame, (-swing_arm * phase * fade, 0, math.radians(-4)))
                key(self.arms["R"], "rotation_euler", frame, (swing_arm * phase * fade, 0, math.radians(4)))
            bob = 0.035 * abs(math.cos(i * math.pi / 2)) * fade
            key(self.hips, "location", frame, (0, 0, HIP_HEIGHT + bob))
        for limb in self.legs.values():
            key(limb, "rotation_euler", end + 4, (0, 0, 0))
        for limb in self.arms.values():
            key(limb, "rotation_euler", end + 4, (ZOMBIE_ARMS if self.zombie else 0, 0, 0))
        key(self.hips, "location", end + 4, (0, 0, HIP_HEIGHT))

    def raise_arm(self, start: int, end: int, side: str = "R", hold: int = 24) -> None:
        arm = self.arms[side]
        key(arm, "rotation_euler", start, (0, 0, 0))
        key(arm, "rotation_euler", end, (math.radians(150), 0, math.radians(10 if side == "R" else -10)))
        key(arm, "rotation_euler", end + hold, (math.radians(150), 0, math.radians(10 if side == "R" else -10)))
        key(arm, "rotation_euler", end + hold + 12, (0, 0, 0))

    def wave(self, start: int, end: int, side: str = "R") -> None:
        arm = self.arms[side]
        key(arm, "rotation_euler", start, (0, 0, 0))
        f, toggle = start + 8, 1
        while f < end - 8:
            key(arm, "rotation_euler", f, (math.radians(160), math.radians(25 * toggle), 0))
            f += 7
            toggle *= -1
        key(arm, "rotation_euler", end, (0, 0, 0))

    def look_at(self, start: int, point, duration: int = 18) -> None:
        yaw = self.yaw_towards(self.position, point) - self.yaw
        yaw = (yaw + math.pi) % (2 * math.pi) - math.pi
        head_yaw = max(-1.0, min(1.0, yaw))  # head turns at most ~57 degrees
        key(self.neck, "rotation_euler", start, (0, 0, 0))
        key(self.neck, "rotation_euler", start + duration, (math.radians(-6), 0, head_yaw * 0.7))
        body = yaw - head_yaw * 0.7
        if abs(body) > 0.05:
            self.set_yaw(start + duration + 6, self.yaw + body, turn_frames=duration)

    def jump(self, start: int, height: float = 0.5, fps: int = 24) -> None:
        air = round(fps * 0.45)
        base = HIP_HEIGHT
        key(self.hips, "location", start, (0, 0, base))
        key(self.hips, "location", start + 4, (0, 0, base - 0.12))
        key(self.hips, "location", start + 4 + air // 2, (0, 0, base + height))
        key(self.hips, "location", start + 4 + air, (0, 0, base - 0.08))
        key(self.hips, "location", start + 10 + air, (0, 0, base))
        for side, sign in (("L", 1), ("R", -1)):
            key(self.arms[side], "rotation_euler", start + 4, (0, 0, 0))
            key(
                self.arms[side], "rotation_euler", start + 4 + air // 2, (math.radians(140), 0, math.radians(20 * sign))
            )
            key(self.arms[side], "rotation_euler", start + 10 + air, (0, 0, 0))

    def fling(
        self,
        start: int,
        end: int,
        fps: int,
        direction_deg: float = 0.0,
        speed: float = 9.0,
        lift: float = 4.0,
        track=None,
        gravity: float = 1.6,
    ) -> None:
        """Inertia: the body keeps moving when the ground stops. Ballistic flight with tumbling."""
        heading = math.radians(direction_deg)
        dx, dy = math.cos(heading), math.sin(heading)
        x0, y0, z0 = self.position
        key(self.root, "location", start, (x0, y0, z0))
        key(self.root, "rotation_euler", start, (0, 0, self.yaw))
        for limb, angle in ((self.arms["L"], 150), (self.arms["R"], 150), (self.legs["L"], 25), (self.legs["R"], -25)):
            key(limb, "rotation_euler", start, (0, 0, 0))
            key(limb, "rotation_euler", start + 5, (math.radians(angle), 0, 0))
        for f in range(1, end - start + 1):
            t = f / fps
            x, y = x0 + dx * speed * t, y0 + dy * speed * t
            z = max(0.0, z0 + lift * t - gravity * t * t)
            key(self.root, "location", start + f, (x, y, z))
            key(self.root, "rotation_euler", start + f, (t * 2.2 * dy, -t * 2.2 * dx, self.yaw + t * 1.5))
            if track is not None and f % 4 == 0:
                track.add(start + f, (x, y, z))
        set_interpolation(self.root, "LINEAR")

    def cover(self, start: int, end: int) -> None:
        """Crouch and protect the head with both arms."""
        key(self.hips, "location", start, (0, 0, HIP_HEIGHT))
        key(self.hips, "location", start + 6, (0, 0, HIP_HEIGHT * 0.55))
        key(self.hips, "location", end, (0, 0, HIP_HEIGHT * 0.55))
        for side, sign in (("L", 1), ("R", -1)):
            key(self.arms[side], "rotation_euler", start, (0, 0, 0))
            key(self.arms[side], "rotation_euler", start + 6, (math.radians(165), 0, math.radians(35 * sign)))
            key(self.arms[side], "rotation_euler", end, (math.radians(165), 0, math.radians(35 * sign)))
        for side in ("L", "R"):
            key(self.legs[side], "rotation_euler", start, (0, 0, 0))
            key(self.legs[side], "rotation_euler", start + 6, (math.radians(70), 0, 0))
            key(self.legs[side], "rotation_euler", end, (math.radians(70), 0, 0))
        key(self.neck, "rotation_euler", start + 6, (math.radians(25), 0, 0))

    def fall(self, start: int, fps: int, direction_deg: float = 0.0) -> None:
        """Topple over towards a direction (about the feet), arms out."""
        heading = math.radians(direction_deg) - self.yaw
        axis_x, axis_y = -math.sin(heading), math.cos(heading)
        key(self.root, "rotation_euler", start, (0, 0, self.yaw))
        key(
            self.root,
            "rotation_euler",
            start + round(fps * 0.6),
            (axis_x * math.radians(85), axis_y * math.radians(85), self.yaw),
        )
        for side in ("L", "R"):
            key(self.arms[side], "rotation_euler", start, (0, 0, 0))
            key(self.arms[side], "rotation_euler", start + 8, (math.radians(110), 0, 0))

    def grow(self, start: int, end: int, to_scale: float, scale_track=None) -> None:
        """Smooth growth (time-lapse). Children scale with the root, so the whole rig grows."""
        key(self.root, "scale", start, (self.scale,) * 3)
        key(self.root, "scale", end, (to_scale,) * 3)
        if scale_track is not None:
            scale_track.add(start, (self.scale, 0, 0))
            scale_track.add(end, (to_scale, 0, 0))
        self.scale = to_scale

    def idle(self, frame_start: int, frame_end: int, fps: int, seed: int) -> None:
        """Breathing and blinking for the whole shot."""
        period = round(fps * 3.2)
        for i, frame in enumerate(range(frame_start, frame_end + period, period // 2)):
            s = 1.0 + (0.018 if i % 2 else 0.0)
            key(self.torso, "scale", frame, (s, s, 1.0 + (s - 1) * 0.6))
        blink_every = round(fps * (2.3 + (seed % 5) * 0.2))
        for frame in range(frame_start + blink_every // 2, frame_end, blink_every):
            for eye in self.eyes:
                key(eye, "scale", frame, (1, 1, 1))
                key(eye, "scale", frame + 2, (1, 1, 0.1))
                key(eye, "scale", frame + 4, (1, 1, 1))


def _hat(name: str, accent, neck, col) -> None:
    objects.mesh_object(
        f"{name}_hat",
        objects.cone(0.2, 0.02, 0.36, 24),
        accent,
        True,
        (0, -0.02, 0.4),
        rotation=(math.radians(-14), 0, 0),
        parent=neck,
        col=col,
    )
    objects.mesh_object(
        f"{name}_brim",
        objects.cone(0.32, 0.32, 0.025, 32),
        accent,
        True,
        (0, -0.01, 0.39),
        rotation=(math.radians(-8), 0, 0),
        parent=neck,
        col=col,
    )


def build_character(
    name: str,
    palette: dict | None = None,
    location=(0, 0, 0),
    facing_deg: float = 0.0,
    scale: float = 1.0,
    zombie: bool = False,
    hat: bool = True,
) -> CinematicCharacter:
    p = {**DEFAULT_PALETTE, **(palette or {})}
    if zombie:  # a zombie keeps no palette of the living (continuity palettes are for the cast)
        p = dict(ZOMBIE_PALETTE)
    body = materials.principled(f"{name}_body", p["body"], roughness=0.85)
    skin = materials.principled(f"{name}_skin", p["skin"], roughness=0.55, subsurface=0.15)
    accent = materials.principled(f"{name}_accent", p["accent"], roughness=0.7)
    hair = materials.principled(f"{name}_hair", p["hair"], roughness=0.6)
    boots = materials.principled(f"{name}_boots", p["boots"], roughness=0.6)
    eye_white = materials.principled("eye_white", "#f4f1ea", roughness=0.2, coat=0.5)
    eye_dark = materials.principled("eye_dark", p["eyes"], roughness=0.1, coat=1.0)

    col = objects.collection(name)
    yaw = math.radians(facing_deg)
    root = objects.empty(f"{name}_root", location=location, col=col)
    root.rotation_euler = (0, 0, yaw)
    root.scale = (scale, scale, scale)
    hips = objects.empty(f"{name}_hips", location=(0, 0, HIP_HEIGHT), parent=root, col=col)

    objects.mesh_object(
        f"{name}_pelvis", objects.sphere(0.2), body, True, (0, 0, 0.02), scale=(1.1, 0.85, 0.7), parent=hips, col=col
    )
    torso = objects.mesh_object(
        f"{name}_torso", objects.sphere(0.26), body, True, (0, 0, 0.32), scale=(1.0, 0.78, 1.25), parent=hips, col=col
    )
    objects.mesh_object(
        f"{name}_belt",
        objects.cone(0.215, 0.215, 0.06, 32, False),
        boots,
        True,
        (0, 0, 0.1),
        scale=(1.0, 0.82, 1),
        parent=hips,
        col=col,
    )

    neck = objects.empty(f"{name}_neck", location=(0, 0, 0.64), parent=hips, col=col)
    objects.mesh_object(
        f"{name}_scarf", objects.cone(0.15, 0.13, 0.09, 32, False), accent, True, (0, 0, 0.0), parent=neck, col=col
    )
    objects.mesh_object(
        f"{name}_head",
        objects.sphere(0.23, 32, 16),
        skin,
        True,
        (0, 0.0, 0.24),
        scale=(1, 0.95, 1.02),
        parent=neck,
        col=col,
    )
    objects.mesh_object(
        f"{name}_hair",
        objects.sphere(0.235, 32, 16),
        hair,
        True,
        (0, -0.03, 0.29),
        scale=(1.03, 0.98, 0.85),
        parent=neck,
        col=col,
    )
    objects.mesh_object(f"{name}_nose", objects.sphere(0.04), skin, True, (0, 0.225, 0.22), parent=neck, col=col)
    if hat and not zombie:
        _hat(name, accent, neck, col)
    eyes = []
    for sx in (-1, 1):
        eye = objects.mesh_object(
            f"{name}_eye_{sx}", objects.sphere(0.05), eye_white, True, (0.085 * sx, 0.19, 0.27), parent=neck, col=col
        )
        objects.mesh_object(
            f"{name}_pupil_{sx}", objects.sphere(0.028), eye_dark, True, (0, 0.035, 0.0), parent=eye, col=col
        )
        eyes.append(eye)

    arms = {}
    for side, sx in (("L", -1), ("R", 1)):
        shoulder = objects.empty(f"{name}_shoulder_{side}", location=(0.3 * sx, 0, 0.5), parent=hips, col=col)
        objects.mesh_object(f"{name}_arm_{side}", objects.capsule(0.075, 0.5), body, True, parent=shoulder, col=col)
        objects.mesh_object(
            f"{name}_hand_{side}", objects.sphere(0.075), skin, True, (0, 0, -0.5), parent=shoulder, col=col
        )
        arms[side] = shoulder

    legs = {}
    for side, sx in (("L", -1), ("R", 1)):
        hip = objects.empty(f"{name}_hip_{side}", location=(0.11 * sx, 0, 0.0), parent=hips, col=col)
        objects.mesh_object(f"{name}_leg_{side}", objects.capsule(0.09, 0.7), body, True, parent=hip, col=col)
        objects.mesh_object(
            f"{name}_boot_{side}",
            objects.transform(objects.sphere(0.1), Matrix.Diagonal((1, 1.5, 0.6, 1))),
            boots,
            True,
            (0, 0.05, -0.72),
            parent=hip,
            col=col,
        )
        legs[side] = hip

    if zombie:
        for side, shoulder in arms.items():
            shoulder.rotation_euler = (ZOMBIE_ARMS, 0, math.radians(-6 if side == "L" else 6))
        neck.rotation_euler = (math.radians(12), math.radians(14), 0)  # head hanging to one side
    return CinematicCharacter(
        zombie=zombie,
        name=name,
        root=root,
        hips=hips,
        torso=torso,
        neck=neck,
        eyes=eyes,
        arms=arms,
        legs=legs,
        scale=scale,
        yaw=yaw,
        position=tuple(location),
    )
