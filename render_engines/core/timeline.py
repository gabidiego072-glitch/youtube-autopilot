"""Piecewise-linear position tracks, so the camera can follow animated entities
without querying Blender's evaluated depsgraph frame by frame. Pure Python."""

from __future__ import annotations

from bisect import bisect_right

Vec3 = tuple[float, float, float]


def lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class PositionTrack:
    def __init__(self, initial: Vec3) -> None:
        self._frames: list[float] = [float("-inf")]
        self._points: list[Vec3] = [tuple(initial)]

    def add(self, frame: float, position: Vec3) -> None:
        idx = bisect_right(self._frames, frame)
        self._frames.insert(idx, frame)
        self._points.insert(idx, tuple(position))

    def at(self, frame: float) -> Vec3:
        idx = bisect_right(self._frames, frame) - 1
        if idx >= len(self._frames) - 1:
            return self._points[-1]
        f0, f1 = self._frames[idx], self._frames[idx + 1]
        if f0 == float("-inf"):
            return self._points[idx]
        return lerp(self._points[idx], self._points[idx + 1], (frame - f0) / (f1 - f0))


class Timeline:
    """Named tracks for every character/prop the camera might target."""

    def __init__(self) -> None:
        self.tracks: dict[str, PositionTrack] = {}
        self.heights: dict[str, float] = {}

    def register(self, name: str, position: Vec3, focus_height: float = 0.0) -> PositionTrack:
        self.tracks[name] = PositionTrack(position)
        self.heights[name] = focus_height
        return self.tracks[name]

    def focus_point(self, name: str, frame: float) -> Vec3:
        x, y, z = self.tracks[name].at(frame)
        return (x, y, z + self.heights.get(name, 0.0))
