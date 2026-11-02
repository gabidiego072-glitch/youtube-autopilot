"""3D science-visualisation engine (Blender, Cycles): characters, natural environments,
physically based lighting and keyframed camera work, for illustrating 'What would
happen if...?' scenarios (growth, scale, speed...) without paid services or a GPU."""

import math

from render_engines.core.spec import RenderContext
from render_engines.core.timeline import Timeline

ACTION_TYPES = ("walk", "raise_arm", "wave", "look_at", "jump", "light_on", "turn", "grow")


def build(spec: dict, ctx: RenderContext, scene, frames_dir: str) -> None:
    from render_engines.cinematic.character import build_character
    from render_engines.cinematic.environment import build_environment, fireflies
    from render_engines.cinematic.props import PROP_BUILDERS
    from render_engines.core.blender.camera import build_camera
    from render_engines.core.blender.scene import add_glow, configure_render

    configure_render(scene, ctx, frames_dir, motion_blur=spec.get("motion_blur", True))
    env = spec.get("environment", {})
    paths = [(tuple(a["from"]), tuple(a["to"])) for a in spec.get("actions", []) if a["type"] == "walk"]
    build_environment(env, ctx, scene, paths)
    add_glow(scene, threshold=env.get("glow_threshold", 1.0))

    timeline = Timeline()
    characters, props = {}, {}
    for c in spec.get("characters", []):
        start = tuple(c.get("start", (0, 0))[:2]) + (0.0,)
        char = build_character(c["id"], c.get("palette"), start, c.get("facing", 0), c.get("scale", 1.0))
        char.idle(ctx.frame_start, ctx.frame_end, ctx.fps, ctx.seed + len(characters))
        characters[c["id"]] = char
        timeline.register(c["id"], start, focus_height=1.25, scale=char.scale)
    for p in spec.get("props", []):
        prop = PROP_BUILDERS[p["type"]](p["id"], tuple(p["location"]), p.get("facing", 0))
        props[p["id"]] = prop
        timeline.register(p["id"], tuple(p["location"]), focus_height=getattr(prop, "focus_height", 1.0))

    if env.get("fireflies"):
        fireflies(env["fireflies"], env.get("firefly_center", (0, 2)), 6, ctx, ctx.seed)

    shots = spec["camera"]["shots"]

    def camera_position(seconds: float):
        before = [s for s in shots if s["time"] <= seconds] or shots[:1]
        return tuple(before[-1]["location"])

    for action in sorted(spec.get("actions", []), key=lambda a: a.get("start", a.get("at", 0))):
        kind = action["type"]
        if kind not in ACTION_TYPES:
            raise ValueError(f"Cinematic engine does not support action '{kind}'.")
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
                action.get("pace", 1.8),
                timeline.tracks[action["character"]],
            )
        elif kind == "raise_arm":
            char.raise_arm(
                start,
                end,
                "R" if action.get("side", "right") == "right" else "L",
                hold=round(action.get("hold", 1.0) * ctx.fps),
            )
        elif kind == "wave":
            char.wave(start, end, "R" if action.get("side", "right") == "right" else "L")
        elif kind == "jump":
            char.jump(start, action.get("height", 0.5), ctx.fps)
        elif kind == "turn":
            if "towards" in action:
                yaw = char.yaw_towards(char.position, timeline.focus_point(action["towards"], start))
            else:
                yaw = math.radians(action["facing"])
            char.set_yaw(end, yaw, turn_frames=max(4, end - start))
        elif kind == "look_at":
            target = action["target"]
            point = camera_position(action["start"]) if target == "camera" else timeline.focus_point(target, start)
            char.look_at(start, point)
        elif kind == "grow":
            char.grow(start, end, float(action["to_scale"]), timeline.scales[action["character"]])
        elif kind == "light_on":
            props[action["prop"]].light_on(start)

    build_camera(scene, ctx, spec["camera"], timeline)
