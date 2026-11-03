"""Keyframe helpers that work with Blender 4.4+ slotted actions and older layouts."""

import bpy


def key(target, data_path: str, frame: int, value=None, index: int = -1) -> None:
    if value is not None:
        if index >= 0:
            getattr(target, data_path)[index] = value
        else:
            setattr(target, data_path, value)
    target.keyframe_insert(data_path=data_path, frame=frame, index=index)


def fcurves(id_data) -> list:
    anim = getattr(id_data, "animation_data", None)
    if anim is None or anim.action is None:
        return []
    action = anim.action
    try:
        return list(action.fcurves)
    except AttributeError:
        pass
    curves = []
    for layer in action.layers:
        for strip in layer.strips:
            bag = strip.channelbag(anim.action_slot)
            if bag:
                curves.extend(bag.fcurves)
    return curves


def set_interpolation(id_data, interpolation: str = "LINEAR", data_path: str | None = None) -> None:
    for curve in fcurves(id_data):
        if data_path and curve.data_path != data_path:
            continue
        for point in curve.keyframe_points:
            point.interpolation = interpolation


def add_noise(id_data, data_path: str, strength: float, scale: float = 30.0, phase: float = 0.0) -> None:
    """Procedural wobble on an animated channel (e.g. handheld camera, hovering)."""
    for curve in fcurves(id_data):
        if curve.data_path == data_path:
            mod = curve.modifiers.new("NOISE")
            mod.strength = strength
            mod.scale = scale
            mod.phase = phase + curve.array_index * 13.7


def ensure_keyed(obj: bpy.types.Object, frame: int, paths=("location", "rotation_euler")) -> None:
    for path in paths:
        obj.keyframe_insert(data_path=path, frame=frame)
