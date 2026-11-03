"""3D science-visualisation engine (Blender, Cycles): characters, natural environments,
physically based lighting and keyframed camera work, for illustrating 'What would
happen if...?' scenarios (growth, scale, speed...) without paid services or a GPU."""

import math

from render_engines.core.catalog import ACTIONS
from render_engines.core.spec import RenderContext
from render_engines.core.timeline import Timeline

ACTION_TYPES = tuple(ACTIONS)


def build(spec: dict, ctx: RenderContext, scene, frames_dir: str) -> None:
    from render_engines.cinematic.character import build_character
    from render_engines.cinematic.environment import build_environment, fireflies
    from render_engines.cinematic.props import PROP_BUILDERS
    from render_engines.core.blender.camera import build_camera
    from render_engines.core.blender.scene import add_glow, configure_render

    configure_render(scene, ctx, frames_dir, motion_blur=spec.get("motion_blur", True))
    from render_engines.cinematic import urban as urban_env
    from render_engines.cinematic.environment import sun_path
    from render_engines.cinematic.explainers import start_wind
    from render_engines.cinematic.space import build_space

    env = spec.get("environment", {})
    env_refs = {}
    urban = None
    env_type = env.get("type", "meadow")
    if env_type == "space":
        build_space(env, scene, ctx.seed)
    elif env_type in ("city", "coast"):
        urban = urban_env.build_city(env, ctx, scene, ctx.seed)
        env_refs = urban.sky_refs
    elif env_type == "interior":
        urban = urban_env.build_interior(env, ctx, scene, ctx.seed)
        env_refs = urban.sky_refs
    else:
        paths = [(tuple(a["from"]), tuple(a["to"])) for a in spec.get("actions", []) if a["type"] == "walk"]
        starts = {c["id"]: tuple(c.get("start", (0, 0))[:2]) for c in spec.get("characters", [])}
        for a in spec.get("actions", []):
            if a["type"] == "fling" and a.get("character") in starts:  # keep the flight path clear
                x, y = starts[a["character"]]
                heading = math.radians(a.get("direction_deg", 0.0))
                paths.append(((x, y), (x + 40 * math.cos(heading), y + 40 * math.sin(heading))))
        env_refs = build_environment(env, ctx, scene, paths)
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
        params = {k: v for k, v in p.items() if k not in ("id", "type", "location", "facing")}
        if p["type"] == "wind":
            params.setdefault("seed", ctx.seed)
        prop = PROP_BUILDERS[p["type"]](p["id"], tuple(p["location"]), p.get("facing", 0), **params)
        props[p["id"]] = prop
        timeline.register(p["id"], tuple(p["location"]), focus_height=getattr(prop, "focus_height", 1.0))

    if urban is not None and env.get("pedestrians"):
        import random as _random

        rng = _random.Random(ctx.seed + 31)
        for i in range(int(env["pedestrians"])):
            side = 1 if i % 2 else -1
            y = side * (urban_env.ROAD_HALF + rng.uniform(0.9, 2.6))
            x0 = rng.uniform(-30, 30)
            direction = rng.choice((-1, 1))
            palette = {
                "body": rng.choice(("#355c7d", "#6c5b7b", "#c06c84", "#4a7c59", "#8c6d46", "#2f3e46")),
                "accent": rng.choice(("#e07a3a", "#f2c14e", "#e8e8e8", "#3f88c5")),
                "skin": rng.choice(("#e0ac85", "#c68642", "#8d5524", "#f1c27d")),
                "hair": rng.choice(("#2d1e14", "#6b4423", "#1b1b1b", "#b89778")),
            }
            walker = build_character(f"ped_{i}", palette, (x0, y, 0.0), 0, rng.uniform(0.92, 1.08))
            walker.idle(ctx.frame_start, ctx.frame_end, ctx.fps, ctx.seed + 50 + i)
            walker.walk(
                ctx.frame_start,
                ctx.frame_end,
                (x0, y),
                (x0 + direction * 1.3 * ctx.duration_seconds, y),
                ctx.fps,
                rng.uniform(1.6, 2.0),
            )
            characters.setdefault(f"ped_{i}", walker)

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
        elif kind == "spin":
            props[action["prop"]].change_spin(start, end, float(action["rate_from"]), float(action["rate_to"]))
        elif kind == "fling":
            char.fling(
                start,
                end,
                ctx.fps,
                action.get("direction_deg", 0.0),
                action.get("speed", 9.0),
                action.get("lift", 4.0),
                timeline.tracks[action["character"]],
                action.get("gravity", 1.6),
            )
        elif kind == "wind":
            start_wind(props[action["prop"]], start, end, ctx.fps, action.get("speed", 22.0))
        elif kind == "sun_path":
            if not env_refs:
                raise ValueError("sun_path needs the meadow environment.")
            sun_path(env_refs, start, end, float(action["elevation_from"]), float(action["elevation_to"]))
        elif kind == "migrate_oceans":
            props[action["prop"]].migrate_oceans(start, end, float(action.get("amount", 1.0)))
        elif kind == "inertia_shock":
            urban_env.inertia_shock(
                scene, start, end, float(action.get("accel", 35.0)), float(action.get("direction_deg", 0.0))
            )
        elif kind == "shatter_windows":
            urban.pending_shatter = start  # applied once the shards have rigid bodies
        elif kind == "surge":
            urban_env.surge(urban, start, end, float(action.get("height", 3.0)), float(action.get("inland", 40.0)))
        elif kind == "lights_on":
            urban_env.lights_on(urban, start, end)
        elif kind == "cover":
            char.cover(start, end)
        elif kind == "fall":
            char.fall(start, ctx.fps, float(action.get("direction_deg", 0.0)))
        elif kind == "appear":
            props[action["target"]].appear(start, end)
        elif kind == "fade":
            props[action["target"]].fade(start, end, float(action.get("to", 0.0)))
        elif kind == "scale":
            target = action["target"]
            current = timeline.scales[target].at(start)[0]
            props[target].scale_to(start, end, float(action["factor"]), current)
            timeline.scales[target].add(start, (current, 0, 0))
            timeline.scales[target].add(end, (float(action["factor"]), 0, 0))

    for prop in props.values():
        if hasattr(prop, "bake_spin"):
            prop.bake_spin(ctx.frame_start, ctx.frame_end, ctx.fps)

    camera = build_camera(scene, ctx, spec["camera"], timeline)
    if urban is not None:
        if urban.water is not None:
            urban_env.animate_waves(urban.water, ctx.frame_start, ctx.frame_end)
        if env.get("physics"):
            urban_env.enable_physics(urban, scene, ctx)
            if getattr(urban, "pending_shatter", None) is not None:
                urban_env.shatter_windows(urban, urban.pending_shatter, ctx.fps)
            urban_env.simulate(scene)
    for prop in props.values():
        if getattr(prop, "billboard", False):  # labels always face the camera
            constraint = prop.root.constraints.new("TRACK_TO")
            constraint.target = camera
            constraint.track_axis = "TRACK_Z"
            constraint.up_axis = "UP_Y"
