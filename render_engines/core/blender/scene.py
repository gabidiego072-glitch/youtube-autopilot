import contextlib

import bpy

from render_engines.core.spec import RenderContext


def reset_scene() -> bpy.types.Scene:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "Autopilot"
    return scene


def configure_render(scene: bpy.types.Scene, ctx: RenderContext, frames_dir: str, motion_blur: bool = False) -> None:
    """Cycles on CPU: deterministic, works headless and without a GPU."""
    render = scene.render
    render.engine = "CYCLES"
    render.resolution_x, render.resolution_y = ctx.width, ctx.height
    render.resolution_percentage = 100
    render.fps = ctx.fps
    render.use_persistent_data = True  # reuse scene data between frames
    render.use_motion_blur = motion_blur
    render.film_transparent = False
    render.image_settings.file_format = "PNG"
    render.image_settings.color_mode = "RGB"
    render.image_settings.color_depth = "8"
    render.image_settings.compression = 15
    render.filepath = f"{frames_dir.rstrip('/')}/frame_"
    render.use_file_extension = True

    scene.frame_start, scene.frame_end = ctx.frame_start, ctx.frame_end

    cycles = scene.cycles
    cycles.device = "CPU"
    cycles.samples = ctx.samples
    cycles.use_adaptive_sampling = True
    cycles.adaptive_threshold = 0.05
    cycles.use_denoising = True
    cycles.denoiser = "OPENIMAGEDENOISE"
    cycles.denoising_prefilter = "ACCURATE" if ctx.samples >= 4 else "FAST"  # cleaner edges on hd/final
    with contextlib.suppress(AttributeError, TypeError):  # older Blender has no quality setting
        cycles.denoising_quality = "BALANCED"
    cycles.max_bounces = 6
    cycles.diffuse_bounces = 3
    cycles.glossy_bounces = 2
    cycles.transmission_bounces = 4
    cycles.transparent_max_bounces = 4
    cycles.volume_bounces = 0
    cycles.caustics_reflective = False
    cycles.caustics_refractive = False
    cycles.blur_glossy = 1.0
    cycles.seed = ctx.seed

    view = scene.view_settings
    view.view_transform = "AgX"
    try:
        view.look = "AgX - Medium High Contrast"
    except TypeError:
        view.look = "None"


def set_sky(
    scene: bpy.types.Scene,
    sun_elevation_deg: float,
    sun_rotation_deg: float,
    strength: float = 1.0,
    air: float = 1.0,
    dust: float = 1.0,
    sun_disc: bool = False,
) -> None:
    """Physically based Nishita sky (Cycles). The sun itself normally comes from a sun lamp,
    so the sky's own (very bright) sun disc is off unless asked for."""
    import math

    world = bpy.data.worlds.new("Sky")
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(sun_elevation_deg)
    sky.sun_rotation = math.radians(sun_rotation_deg)
    sky.air_density = air
    sky.dust_density = dust
    sky.sun_disc = sun_disc
    background = nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = strength
    output = nodes.new("ShaderNodeOutputWorld")
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    return sky, background


def _set(node, name: str, value) -> None:
    """Glare options moved from properties to input sockets in recent Blender versions."""
    if hasattr(node, name.lower()):
        setattr(node, name.lower(), value)
    elif name in node.inputs:
        node.inputs[name].default_value = value


def add_glow(scene: bpy.types.Scene, threshold: float = 1.0, size: int = 7, strength: float = 1.0) -> None:
    """Compositor fog glow so bright emitters (lanterns, gems) bloom like a real lens."""
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    layers = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"
    _set(glare, "Quality", "MEDIUM")
    _set(glare, "Threshold", threshold)
    _set(glare, "Size", size)
    if "Strength" in glare.inputs:
        glare.inputs["Strength"].default_value = strength
    out = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(layers.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], out.inputs["Image"])


def add_haze(scene: bpy.types.Scene, color: str, start: float = 25.0, depth: float = 260.0, amount: float = 0.55):
    """Aerial perspective in the compositor: far things fade into the air colour (mist pass, no volumes)."""
    from render_engines.core.colors import hex_to_linear

    scene.view_layers[0].use_pass_mist = True
    world = scene.world
    world.mist_settings.start, world.mist_settings.depth = start, depth
    world.mist_settings.falloff = "QUADRATIC"
    tree = scene.node_tree
    layers = next(n for n in tree.nodes if n.type == "R_LAYERS")
    out = next(n for n in tree.nodes if n.type == "COMPOSITE")
    source = out.inputs["Image"].links[0].from_socket
    scale = tree.nodes.new("CompositorNodeMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = amount
    tree.links.new(layers.outputs["Mist"], scale.inputs[0])
    mix = tree.nodes.new("CompositorNodeMixRGB")
    mix.inputs[2].default_value = hex_to_linear(color)
    tree.links.new(scale.outputs[0], mix.inputs[0])
    tree.links.new(source, mix.inputs[1])
    tree.links.new(mix.outputs[0], out.inputs["Image"])


def render_animation() -> None:
    bpy.ops.render.render(animation=True)
