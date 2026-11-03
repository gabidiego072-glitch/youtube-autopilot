"""Colour helpers. Blender shader inputs expect scene-linear RGB."""


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_linear(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Expected #RRGGBB, got '{value}'.")
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return (_srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b), alpha)


def scale_color(rgba: tuple[float, ...], factor: float) -> tuple[float, float, float, float]:
    r, g, b, a = rgba
    return (min(1.0, r * factor), min(1.0, g * factor), min(1.0, b * factor), a)
