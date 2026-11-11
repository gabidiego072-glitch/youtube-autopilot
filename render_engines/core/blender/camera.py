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
    data.clip_end = 2500  # far landmarks (Eiffel Tower, Big Ben) at the end of the avenue
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

    rig = None
    if camera_spec.get("pov"):
        rig = _pov_rig(cam, camera_spec.get("pov_item"), camera_spec.get("pov_hands", "normal"))
        camera_spec.setdefault("handheld", 0.02)  # a person's head never holds perfectly still
    if camera_spec.get("handheld", 0) > 0:
        add_noise(cam, "location", strength=camera_spec["handheld"], scale=40)
    if camera_spec.get("shakes"):
        _add_shakes(cam, ctx, camera_spec["shakes"])
    if rig is not None and camera_spec.get("pov_reach"):  # your hand goes to the thing and stays on it
        import math

        arm = rig["arms"].get(1) or next(iter(rig["arms"].values()))
        base = tuple(arm.location)
        for at in camera_spec["pov_reach"]:
            frame = ctx.frame(float(at))
            key(arm, "location", frame - 8, base)
            key(arm, "location", frame, (base[0] * 0.35, base[1] + 0.2, base[2] - 0.3))
            key(arm, "rotation_euler", frame - 8, tuple(arm.rotation_euler))
            key(arm, "rotation_euler", frame, (math.radians(40), 0, 0))
            key(arm, "location", frame + 6, (base[0] * 0.35, base[1] + 0.14, base[2] - 0.3))  # pull / press
    if rig is not None and (camera_spec.get("pov_run") or camera_spec.get("pov_pushes") or camera_spec.get("pov_sips")):
        _pov_motion(
            cam,
            rig,
            ctx,
            bool(camera_spec.get("pov_run")),
            camera_spec.get("pov_pushes", []),
            camera_spec.get("pov_sips", []),
        )
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


def _pov_rig(cam, item: str | None = None, hands: str = "normal") -> None:
    """First-person view: the viewer's own arms and hands at the bottom of the frame, optionally holding
    a phone (glowing map screen) or a flashlight. Parented to the camera (local -Z is forward, +Y up)."""
    import math

    from mathutils import Matrix

    from render_engines.core.blender import materials, objects
    from render_engines.core.blender.animation import add_noise

    cam.data.clip_start = 0.02
    sleeve = materials.principled("pov_sleeve", "#2f3440", roughness=0.85)
    skin = materials.principled("pov_skin", "#d9a27e", roughness=0.55, subsurface=0.15)
    if hands == "old":  # your own hands, aged: paler, wrinkled, with age spots
        skin = _old_skin()
    elif hands == "glow":  # a power: your hands shine
        skin = materials.principled(
            "pov_skin_glow", "#bfe9ff", roughness=0.4, emission="#5fd0ff", emission_strength=4.0
        )
    holder = objects.empty("pov_arms", parent=cam)
    arms = {}
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
        arms[sx] = arm
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
    elif item == "cup":
        china = materials.principled("pov_cup", "#f4f1ea", roughness=0.25)
        coffee = materials.principled("pov_coffee", "#3b2416", roughness=0.15)
        cup = objects.mesh_object(
            "pov_cup",
            objects.cone(0.036, 0.031, 0.075, 24, base_at_origin=True),
            china,
            True,
            location=(0.06, -0.165, -0.5),  # resting on top of the fist, in view
            rotation=(math.radians(-80), 0, 0),  # upright in the camera's view
            parent=holder,
        )
        objects.mesh_object(
            "pov_coffee_top", objects.cone(0.033, 0.033, 0.004, 24), coffee, True, location=(0, 0, 0.069), parent=cup
        )
        objects.mesh_object(
            "pov_cup_handle",
            objects.transform(objects.sphere(0.018, 10, 6), Matrix.Diagonal((0.4, 1, 1.2, 1))),
            china,
            True,
            location=(0.05, 0, 0.05),
            parent=cup,
        )
        holder["cup"] = cup.name
    elif item == "key":  # a brass door key between the fingers, held up in view
        brass = materials.principled("pov_key", "#d4a83a", roughness=0.28, metallic=1.0)
        key_root = objects.empty("pov_key_root", parent=holder)
        key_root.location = (0.05, -0.12, -0.42)
        key_root.rotation_euler = (math.radians(-70), math.radians(20), 0)
        ring = objects.transform(objects.cone(0.022, 0.022, 0.006, 20), Matrix.Rotation(math.pi / 2, 4, "X"))
        objects.mesh_object("pov_key_bow", ring, brass, True, location=(0, 0, 0), parent=key_root)
        objects.mesh_object(
            "pov_key_shaft", objects.box(0.008, 0.006, 0.06), brass, location=(0, 0, 0.05), parent=key_root
        )
        for i, h in enumerate((0.012, 0.007, 0.01)):  # the bit's teeth
            objects.mesh_object(
                f"pov_key_tooth_{i}",
                objects.box(h, 0.006, 0.006),
                brass,
                location=(0.004 + h / 2, 0, 0.064 + 0.009 * i),
                parent=key_root,
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
    if hands != "normal":  # you raise your hands and look at them
        holder.location = (0.0, 0.18, -0.06)
        holder.rotation_euler = (math.radians(6), 0, 0)
    # Arms sway a little with breathing and steps.
    holder.keyframe_insert("location", frame=1)
    add_noise(holder, "location", strength=0.012, scale=18)
    return {"holder": holder, "arms": arms}


def _pov_motion(cam, rig: dict, ctx: RenderContext, running: bool, pushes: list, sips: list = ()) -> None:
    """Running: the head bobs with every stride and the arms pump. Pushes: a hand thrusts forward."""
    import math

    arms = rig["arms"]
    if running:
        bob = empty("pov_bob")
        if cam.parent is not None:
            cam.parent.parent = bob
        else:
            cam.parent = bob
        step = ctx.fps / 5.6  # ~2.8 strides per second, one bob per step
        f, i = float(ctx.frame_start), 0
        while f <= ctx.frame_end + step:
            frame = round(f)
            key(bob, "location", frame, (0.025 * (1 if i % 2 else -1), 0, 0.05 if i % 2 else -0.03))
            for sx, arm in arms.items():
                swing = math.radians(18) * (1 if (i % 2 == 0) == (sx > 0) else -1)
                key(arm, "rotation_euler", frame, (math.radians(14) + swing, math.radians(4 * sx), 0))
            f += step
            i += 1
    for at in sips:  # bring the hand (and the cup) up to the mouth and back
        holder, frame = rig["holder"], ctx.frame(float(at))
        key(holder, "location", frame - 6, (0, 0, 0))
        key(holder, "location", frame, (-0.05, 0.16, 0.12))
        key(holder, "rotation_euler", frame - 6, (0, 0, 0))
        key(holder, "rotation_euler", frame, (math.radians(-25), 0, 0))
        key(holder, "location", frame + 14, (-0.05, 0.16, 0.12))
        key(holder, "rotation_euler", frame + 14, (math.radians(-25), 0, 0))
        key(holder, "location", frame + 22, (0, 0, 0))
        key(holder, "rotation_euler", frame + 22, (0, 0, 0))
    for n, at in enumerate(pushes):
        arm = arms.get(1 if n % 2 == 0 else -1) or next(iter(arms.values()))
        frame = ctx.frame(float(at))
        base = tuple(arm.location)
        key(arm, "location", frame - 3, base)
        key(arm, "location", frame, (base[0] * 0.4, base[1] + 0.12, base[2] - 0.28))  # thrust into the frame
        key(arm, "location", frame + 7, base)
        key(arm, "rotation_euler", frame, (math.radians(28), 0, 0))


def _old_skin():
    """Aged skin for the viewer's hands: pale, blotchy (age spots) and creased (bump)."""
    import bpy

    from render_engines.core.colors import hex_to_linear

    mat = bpy.data.materials.new("pov_skin_old")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.7
    spots = nodes.new("ShaderNodeTexNoise")
    spots.inputs["Scale"].default_value = 60.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.55
    ramp.color_ramp.elements[0].color = hex_to_linear("#d8bfa8")
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = hex_to_linear("#8f6a4c")
    links.new(spots.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    creases = nodes.new("ShaderNodeTexWave")
    creases.inputs["Scale"].default_value = 90.0
    creases.inputs["Distortion"].default_value = 6.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    links.new(creases.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat
