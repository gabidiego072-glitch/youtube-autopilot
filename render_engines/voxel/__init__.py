"""Voxel / game-style 3D engine: procedural block worlds, block characters,
interactive props and camera work, rendered with Cycles."""

import math

from render_engines.core.spec import RenderContext
from render_engines.core.timeline import Timeline

ACTION_TYPES = ("walk", "jump", "punch", "open_chest", "wave", "look_at", "turn")
# sun elevation, azimuth, sun strength, sky strength
DAYTIME = {"morning": (24, 120, 3.0, 0.6), "day": (45, 150, 3.5, 0.7), "sunset": (5, 250, 2.2, 0.4)}


def build(spec: dict, ctx: RenderContext, scene, frames_dir: str) -> None:
    from render_engines.core.blender import lights
    from render_engines.core.blender.animation import key, set_interpolation
    from render_engines.core.blender.camera import build_camera
    from render_engines.core.blender.scene import add_glow, configure_render, set_sky
    from render_engines.voxel.character import build_voxel_character
    from render_engines.voxel.mesh import build_voxel_object
    from render_engines.voxel.models import WORLD_PALETTE
    from render_engines.voxel.props import PROP_BUILDERS
    from render_engines.voxel.world import DECOR_SCALE, generate_world

    configure_render(scene, ctx, frames_dir, motion_blur=spec.get("motion_blur", False))
    env = spec.get("environment", {})
    paths = [(tuple(a["from"]), tuple(a["to"])) for a in spec.get("actions", []) if a["type"] == "walk"]
    clear = [(p["location"][0], p["location"][1], 2.0) for p in spec.get("props", [])]
    anchors = {c["id"]: tuple(c.get("start", (0, 0))[:2]) for c in spec.get("characters", [])}
    anchors.update({p["id"]: tuple(p["location"][:2]) for p in spec.get("props", [])})
    shots = spec["camera"]["shots"]
    sightlines = [(tuple(s["location"][:2]), anchors.get(s.get("target"), (0, 0))) for s in shots]
    sightlines += [(tuple(a["location"][:2]), tuple(b["location"][:2])) for a, b in zip(shots, shots[1:], strict=False)]
    world = generate_world(
        ctx.seed,
        radius=env.get("radius", 26),
        stage_radius=env.get("stage_radius", 7.0),
        trees=env.get("trees", 30),
        flowers=env.get("flowers", 60),
        houses=env.get("houses", 1),
        paths=paths,
        clear=clear,
        sightlines=sightlines,
    )
    build_voxel_object("Terrain", world.terrain, WORLD_PALETTE, seed=ctx.seed)
    if len(world.decor):
        build_voxel_object("Decor", world.decor, WORLD_PALETTE, voxel_size=1 / DECOR_SCALE, jitter=0.1, seed=ctx.seed)
    clouds = build_voxel_object("Clouds", world.clouds, WORLD_PALETTE, voxel_size=1.0, jitter=0.03)
    key(clouds, "location", ctx.frame_start, (0, 0, 0))
    key(clouds, "location", ctx.frame_end, (env.get("cloud_drift", 3.0), 0, 0))
    set_interpolation(clouds, "LINEAR")

    elevation, azimuth, sun_strength, sky_strength = DAYTIME[env.get("time_of_day", "day")]
    set_sky(scene, elevation, azimuth, strength=sky_strength)
    lights.sun("Sun", elevation, azimuth, "#fff1d6", sun_strength, softness_deg=1.5)
    lights.area("Fill", (-8, -14, 9), (math.radians(55), 0, math.radians(-30)), "#cfe0ff", 60, size=10)
    add_glow(scene, threshold=env.get("glow_threshold", 1.2), size=6)

    timeline = Timeline()
    characters, props = {}, {}
    for i, c in enumerate(spec.get("characters", [])):
        x, y = c.get("start", (0, 0))[:2]
        start = (x, y, world.ground_z(x, y))
        char = build_voxel_character(c["id"], start, c.get("facing", 0), c.get("palette"), seed=ctx.seed + i)
        char.idle(ctx.frame_start, ctx.frame_end, ctx.fps)
        characters[c["id"]] = char
        timeline.register(c["id"], start, focus_height=1.1)
    for p in spec.get("props", []):
        x, y = p["location"][:2]
        location = (x, y, world.ground_z(x, y))
        builder = PROP_BUILDERS[p["type"]]
        prop = (
            builder(p["id"], location, p.get("facing", 0), seed=ctx.seed)
            if p["type"] == "chest"
            else builder(p["id"], location, seed=ctx.seed)
        )
        props[p["id"]] = prop
        timeline.register(p["id"], location, focus_height=prop.focus_height)

    def camera_position(seconds: float):
        before = [s for s in shots if s["time"] <= seconds] or shots[:1]
        return tuple(before[-1]["location"])

    for action in sorted(spec.get("actions", []), key=lambda a: a.get("start", a.get("at", 0))):
        kind = action["type"]
        if kind not in ACTION_TYPES:
            raise ValueError(f"Voxel engine does not support action '{kind}'.")
        start = ctx.frame(action.get("start", action.get("at", 0)))
        end = ctx.frame(action.get("end", action.get("start", 0) + 1))
        char = characters.get(action.get("character"))
        if kind == "walk":
            char.walk(
                start,
                end,
                action["from"],
                action["to"],
                ctx.fps,
                world.ground_z,
                action.get("pace", 2.2),
                timeline.tracks[action["character"]],
            )
        elif kind == "jump":
            char.jump(start, ctx.fps, action.get("height", 0.9))
        elif kind == "punch":
            target = props[action["target"]]
            char.set_yaw(start, char.yaw_towards(char.position, target.location), turn_frames=4)
            impact = char.punch(start)
            target.shatter(impact, ctx.fps, ctx.seed)
        elif kind == "open_chest":
            target = props[action["prop"]]
            char.set_yaw(start, char.yaw_towards(char.position, target.location), turn_frames=4)
            char.reach(start, start + 8)
            target.open(start + 6, ctx.fps)
        elif kind == "wave":
            char.wave(start, end)
        elif kind == "turn":
            point = timeline.focus_point(action["towards"], start) if "towards" in action else None
            yaw = char.yaw_towards(char.position, point) if point else math.radians(action["facing"])
            char.set_yaw(end, yaw, turn_frames=max(4, end - start))
        elif kind == "look_at":
            target = action["target"]
            point = camera_position(action["start"]) if target == "camera" else timeline.focus_point(target, start)
            char.look_at(start, point)

    build_camera(scene, ctx, spec["camera"], timeline)
