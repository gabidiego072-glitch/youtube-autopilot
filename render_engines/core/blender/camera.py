"""Camera rig: keyframed position and lens, a target empty that follows any
timeline entity, depth of field, optional handheld noise, aspect-aware framing."""

import bpy

from render_engines.core.blender.animation import add_noise, key, set_interpolation
from render_engines.core.blender.objects import empty, link
from render_engines.core.spec import RenderContext
from render_engines.core.timeline import Timeline, lerp, smoothstep


def build_camera(scene: bpy.types.Scene, ctx: RenderContext, camera_spec: dict, timeline: Timeline):
    data = bpy.data.cameras.new("Camera")
    data.sensor_width = 36
    data.clip_end = 500
    cam = link(bpy.data.objects.new("Camera", data))
    scene.camera = cam

    target = empty("CameraTarget")
    track = cam.constraints.new("TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    if camera_spec.get("dof", True):
        data.dof.use_dof = True
        data.dof.focus_object = target
        data.dof.aperture_fstop = camera_spec.get("fstop", 4.0)

    # Vertical frames show more height and less width; zoom in a little so the
    # subject keeps a similar size, without cropping it horizontally.
    lens_scale = camera_spec.get("portrait_lens_scale", 1.25) if ctx.portrait else 1.0
    shots = camera_spec["shots"]
    for shot in shots:
        frame = ctx.frame(shot["time"])
        key(cam, "location", frame, tuple(shot["location"]))
        key(data, "lens", frame, shot.get("lens", 35) * lens_scale)

    _animate_target(target, ctx, shots, timeline)

    if camera_spec.get("handheld", 0) > 0:
        add_noise(cam, "location", strength=camera_spec["handheld"], scale=40)
    if camera_spec.get("shakes"):
        _add_shakes(cam, ctx, camera_spec["shakes"])
    return cam


def _add_shakes(cam, ctx: RenderContext, shakes: list[dict]) -> None:
    """Impact shakes: a parent rig jitters (decaying) inside each window, zero elsewhere."""
    import random

    rig = empty("CameraShake")
    cam.parent = rig
    rng = random.Random(ctx.seed + 77)
    key(rig, "location", ctx.frame_start, (0, 0, 0))
    for shake in shakes:
        start, end = ctx.frame(shake["start"]), ctx.frame(shake["end"])
        strength = shake.get("strength", 0.15)
        key(rig, "location", max(ctx.frame_start, start - 1), (0, 0, 0))
        for frame in range(start, end):
            decay = 1 - (frame - start) / max(1, end - start)
            amp = strength * decay
            key(rig, "location", frame, (rng.uniform(-amp, amp), rng.uniform(-amp, amp), rng.uniform(-amp, amp)))
        key(rig, "location", end, (0, 0, 0))
    set_interpolation(rig, "LINEAR")


def _resolve(target, frame: float, timeline: Timeline):
    if isinstance(target, str):
        return timeline.focus_point(target, frame)
    return tuple(target)


def _animate_target(target_obj, ctx: RenderContext, shots: list[dict], timeline: Timeline, step: int = 2) -> None:
    """Sample the target every `step` frames; blend smoothly when the shot target changes."""
    shot_frames = [ctx.frame(s["time"]) for s in shots]
    targets = [s.get("target", shots[0].get("target", (0, 0, 1))) for s in shots]
    for frame in range(ctx.frame_start, ctx.frame_end + step, step):
        idx = max(i for i, f in enumerate(shot_frames) if f <= frame) if frame >= shot_frames[0] else 0
        current = _resolve(targets[idx], frame, timeline)
        if idx + 1 < len(shots) and targets[idx + 1] != targets[idx]:
            span = shot_frames[idx + 1] - shot_frames[idx]
            t = smoothstep((frame - shot_frames[idx]) / span) if span else 1.0
            current = lerp(current, _resolve(targets[idx + 1], frame, timeline), t)
        key(target_obj, "location", frame, current)
    set_interpolation(target_obj, "LINEAR")
