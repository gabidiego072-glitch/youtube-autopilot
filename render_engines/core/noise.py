"""Deterministic 2D value noise + fBm. Pure Python so worlds are reproducible from a seed."""

import math


def _hash(ix: int, iy: int, seed: int) -> float:
    h = (ix * 374761393 + iy * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return (h & 0xFFFFFF) / 0xFFFFFF  # 0..1


def _smooth(t: float) -> float:
    return t * t * (3 - 2 * t)


def value_noise(x: float, y: float, seed: int = 0) -> float:
    """Smooth noise in 0..1."""
    x0, y0 = math.floor(x), math.floor(y)
    tx, ty = _smooth(x - x0), _smooth(y - y0)
    a = _hash(x0, y0, seed)
    b = _hash(x0 + 1, y0, seed)
    c = _hash(x0, y0 + 1, seed)
    d = _hash(x0 + 1, y0 + 1, seed)
    top = a + (b - a) * tx
    bottom = c + (d - c) * tx
    return top + (bottom - top) * ty


def fbm(x: float, y: float, seed: int = 0, octaves: int = 4, lacunarity: float = 2.0, gain: float = 0.5) -> float:
    """Fractal noise in 0..1."""
    total, amplitude, frequency, norm = 0.0, 1.0, 1.0, 0.0
    for octave in range(octaves):
        total += value_noise(x * frequency, y * frequency, seed + octave * 101) * amplitude
        norm += amplitude
        amplitude *= gain
        frequency *= lacunarity
    return total / norm
