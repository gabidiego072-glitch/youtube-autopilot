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

    if camera_spec.get("pov"):
        _pov_rig(cam, camera_spec.get("pov_item"))
        camera_spec.setdefault("handheld", 0.02)  # a person's head never holds perfectly still
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


def _pov_rig(cam, item: str | None = None) -> None:
    """First-person view: the viewer's own arms and hands at the bottom of the frame, optionally holding
    a phone (glowing map screen) or a flashlight. Parented to the camera (local -Z is forward, +Y up)."""
    import math

    from mathutils import Matrix

    from render_engines.core.blender import materials, objects
    from render_engines.core.blender.animation import add_noise

    cam.data.clip_start = 0.02
    sleeve = materials.principled("pov_sleeve", "#2f3440", roughness=0.85)
    skin = materials.principled("pov_skin", "#d9a27e", roughness=0.55, subsurface=0.15)
    holder = objects.empty("pov_arms", parent=cam)
    for sx in (-1, 1):
        if item and sx < 0:
            continue  # the left hand stays out of frame when the right one holds something
        arm = objects.mesh_object(
            f"pov_arm_{sx}",
            objects.capsule(0.055, 0.42),
            sleeve,
            True,
            # Vertical frames are narrow: a hand holding something sits near the centre; free hands rest
            # lower, towards the bottom corners, so they frame the view instead of covering it.
            location=(0.12 * sx, -0.3, 0.0) if item else (0.15 * sx, -0.4, 0.0),
            rotation=(math.radians(20 if item else 14), math.radians((9 if item else 4) * sx), 0),
            parent=holder,
        )
        objects.mesh_object(
            f"pov_hand_{sx}",
            objects.transform(objects.sphere(0.05), Matrix.Diagonal((1.0, 0.75, 1.35, 1))),
            skin,
            True,
            location=(0, 0, -0.44),
            parent=arm,
        )
    if item == "phone":
        screen = materials.principled("pov_screen", "#1b2a3a", roughness=0.2, emission="#4fa3e0", emission_strength=2.5)
        body = materials.principled("pov_phone", "#141418", roughness=0.3)
        phone = objects.mesh_object(
            "pov_phone",
            objects.box(0.075, 0.15, 0.008),
            body,
            location=(0.06, -0.13, -0.36),
            rotation=(math.radians(55), 0, math.radians(-8)),
            parent=holder,
        )
        objects.mesh_object(
            "pov_phone_screen", objects.box(0.068, 0.14, 0.002), screen, location=(0, 0, 0.005), parent=phone
        )
    elif item == "flashlight":
        metal = materials.principled("pov_torch", "#2a2b2f", roughness=0.3, metallic=0.8)
        torch = objects.mesh_object(
            "pov_torch",
            objects.capsule(0.022, 0.2),
            metal,
            True,
            location=(0.07, -0.17, -0.3),
            rotation=(math.radians(12), 0, 0),  # the capsule's -Z is the camera's forward
            parent=holder,
        )
        from render_engines.core.blender import lights

        beam = lights.point("pov_beam", (0, 0, -0.25), "#fff1d0", 120.0, radius=0.05, parent=torch)
        beam.data.shadow_soft_size = 0.05
    # Arms sway a little with breathing and steps.
    holder.keyframe_insert("location", frame=1)
    add_noise(holder, "location", strength=0.012, scale=18)
