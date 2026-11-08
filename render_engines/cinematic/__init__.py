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
    from render_engines.core.blender.animation import key
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
    elif env_type == "theater":
        from render_engines.cinematic.theater import build_theater

        urban = build_theater(env, ctx, scene, ctx.seed)
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
        start = tuple(c.get("start", (0, 0))[:2]) + (float(c.get("elevation", 0.0)),)  # e.g. on a stage
        char = build_character(
            c["id"],
            c.get("palette"),
            start,
            c.get("facing", 0),
            c.get("scale", 1.0),
            zombie=bool(c.get("zombie")),
            hat=c.get("hat", True),
        )
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
            walker = build_character(
                f"ped_{i}", palette, (x0, y, 0.0), 0, rng.uniform(0.92, 1.08), hat=rng.random() < 0.2
            )
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

    if urban is not None and (env.get("crowd") or env.get("panic")) and env_type in ("city", "coast"):
        from render_engines.cinematic import crowd

        lane = env.get("keep_clear_y")  # e.g. the camera's running line
        clear = (lambda _x, y: lane is not None and abs(y - lane) < 0.9) if lane is not None else None
        n = int(env.get("crowd", 0))
        span = (-60.0, 60.0)
        side_walk = (urban_env.ROAD_HALF + 0.4, urban_env.BUILDING_LINE - 0.4)
        crowd.walkers(n // 2, (span, side_walk), 0, (0.9, 1.6), ctx.frame_start, ctx.frame_end, ctx.fps, ctx.seed + 1)
        crowd.walkers(
            n // 2,
            (span, (-side_walk[1], -side_walk[0])),
            180,
            (0.9, 1.6),
            ctx.frame_start,
            ctx.frame_end,
            ctx.fps,
            ctx.seed + 2,
        )
        if env.get("panic"):  # people running for their lives down the road
            crowd.walkers(
                int(env["panic"]),
                (span, (-urban_env.ROAD_HALF + 0.5, urban_env.ROAD_HALF - 0.5)),
                env.get("panic_direction", 0),
                (2.6, 4.2),
                ctx.frame_start,
                ctx.frame_end,
                ctx.fps,
                ctx.seed + 3,
                keep_clear=clear,
            )
        if env.get("onlookers"):  # people standing on the sidewalk staring at the screens
            zones = env.get("clear_zones", [])  # [[x0, x1, y0, y1], ...] where the camera passes

            def blocked(x, y):
                return any(z[0] <= x <= z[1] and z[2] <= y <= z[3] for z in zones)

            crowd.standers(
                int(env["onlookers"]),
                ((span[0] / 2, span[1] / 2), side_walk),
                ctx.frame_start,
                ctx.frame_end,
                ctx.fps,
                ctx.seed + 4,
                keep_clear=blocked,
            )

    if urban is not None and env.get("traffic") and env_type in ("city", "coast"):
        import random as _random

        rng = _random.Random(ctx.seed + 55)
        for i in range(int(env["traffic"])):  # cars and taxis driving both ways
            east = i % 2 == 0
            lane_y = -2.35 if east else 2.1
            v = rng.uniform(7.0, 12.0) * (1 if east else -1)
            x0 = rng.uniform(-70, 40) if east else rng.uniform(-40, 70)
            color = urban_env.TAXI_YELLOW if rng.random() < 0.6 else rng.choice(urban_env.CAR_COLORS)
            moving = urban_env.car(f"traffic_{i}", (x0, lane_y, -urban_env.CURB_H), 0 if east else 180, color)
            key_end = (x0 + v * ctx.duration_seconds, lane_y, -urban_env.CURB_H)
            moving.keyframe_insert("location", frame=ctx.frame_start)
            moving.location = key_end
            moving.keyframe_insert("location", frame=ctx.frame_end)
            from render_engines.core.blender.animation import set_interpolation

            set_interpolation(moving, "LINEAR", "location")

    if urban is not None and env.get("chasers") and env_type in ("city", "coast"):  # a horde running after you
        from render_engines.cinematic import crowd

        start_x = float(env.get("chasers_from", -60.0))
        crowd.walkers(
            int(env["chasers"]),
            ((start_x - 14, start_x), (-3.0, 2.0)),
            0,
            (4.3, 4.8),
            ctx.frame_start,
            ctx.frame_end,
            ctx.fps,
            ctx.seed + 9,
            zombie=True,
        )

    if env.get("zombies"):  # a horde shambling towards the scene centre from the distance
        import random as _random

        rng = _random.Random(ctx.seed + 77)
        for i in range(int(env["zombies"])):
            angle = rng.uniform(0, 2 * math.pi)
            dist = rng.uniform(9, 22)
            x0, y0 = dist * math.cos(angle), dist * math.sin(angle)
            if env.get("type") in ("city", "coast"):  # keep them on the street, not inside buildings
                y0 = max(-6.5, min(6.5, y0))
            if env.get("type") == "interior":
                x0, y0 = max(-2.6, min(2.6, x0 / 6)), max(-2.2, min(2.2, y0 / 6))
            pace = rng.uniform(0.55, 0.9)  # metres per second: slow, unstoppable
            travel = min(dist - 2.0, pace * ctx.duration_seconds)
            x1, y1 = x0 - travel * math.cos(angle), y0 - travel * math.sin(angle)
            z = build_character(f"zombie_{i}", None, (x0, y0, 0.0), 0, rng.uniform(0.9, 1.1), zombie=True)
            z.idle(ctx.frame_start, ctx.frame_end, ctx.fps, ctx.seed + 90 + i)
            z.walk(ctx.frame_start, ctx.frame_end, (x0, y0), (x1, y1), ctx.fps, rng.uniform(1.0, 1.3))
            characters.setdefault(f"zombie_{i}", z)

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
        elif kind == "vanish":  # a magician's trick: a puff of white smoke and the character is gone
            from render_engines.cinematic import effects

            key(char.root, "scale", start, (char.scale,) * 3)
            key(char.root, "scale", start + 3, (0.0001,) * 3)
            head = timeline.focus_point(action["character"], start)
            effects.puffs(
                f"vanish_{start}",
                (head[0], head[1], head[2] - 0.8),
                start - 2,
                start + 10,
                ctx.fps,
                color="#bdbdc4",
                alpha=0.35,
                count=22,
                rise=2.2,
                spread=1.4,
                size=0.3,
                life=2.0,
                seed=start,
            )
        elif kind in ("fire", "smoke", "crack", "flood", "collapse"):
            _effect(kind, action, start, end, ctx, urban, env)
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


def _effect(kind: str, action: dict, start: int, end: int, ctx, urban, env: dict) -> None:
    """Narration-driven events: fire, smoke, cracks, rising water, a building collapsing."""
    from mathutils import Vector

    from render_engines.cinematic import effects
    from render_engines.cinematic import urban as urban_env

    name = f"{kind}_{start}"
    interior = env.get("type") == "interior"
    default = (-2.8, 0.6, 0.95) if interior and env.get("room") == "kitchen" else (0.0, 0.0, 0.0)
    location = tuple((list(action.get("location") or default) + [0.0, 0.0, 0.0])[:3])
    seed = ctx.seed + start
    if kind == "fire":
        effects.fire(name, location, start, end, ctx.fps, float(action.get("size", 1.0)), seed)
    elif kind == "smoke":
        effects.puffs(name, location, start, end, ctx.fps, count=max(8, (end - start) // 4), seed=seed)
    elif kind == "crack":
        surface = action.get("surface", "wall" if interior else "floor")
        effects.crack(name, location, start, end, surface, float(action.get("length", 2.0)), seed)
    elif kind == "flood":
        if interior:
            center, size = (0.0, 0.0, 0.0), (6.2, 5.2)
        else:
            length = env.get("length", 90.0)
            center, size = (0.0, 0.0, -urban_env.CURB_H), (length * 2, urban_env.BUILDING_LINE * 2)
        effects.rising_water(name, center, size, start, end, float(action.get("height", 0.6)))
    elif kind == "collapse":
        if urban is None or not urban.buildings:
            raise ValueError("collapse needs the city or coast environment.")
        x = float(action.get("x", location[0]))
        pool = [b for b, _side, hero in urban.buildings if not hero] or [b for b, _s, _h in urban.buildings]

        def centre(b):  # buildings keep their origin at 0: use the geometry's world centre
            corners = [b.matrix_world @ Vector(c) for c in b.bound_box]
            return sum(c.x for c in corners) / 8, sum(c.y for c in corners) / 8

        building = min(pool, key=lambda b: abs(centre(b)[0] - x) + (0 if centre(b)[1] > 0 else 5))
        if building in urban.static:
            urban.static.remove(building)  # it moves now, physics must not pin it
        effects.collapse(building, start, end, ctx.fps, seed)
