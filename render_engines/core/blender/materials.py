import bpy

from render_engines.core.colors import hex_to_linear

_CACHE: dict[tuple, bpy.types.Material] = {}


def _principled(mat: bpy.types.Material):
    mat.use_nodes = True
    return mat.node_tree.nodes["Principled BSDF"]


def principled(
    name: str,
    color: str,
    roughness: float = 0.5,
    metallic: float = 0.0,
    emission: str | None = None,
    emission_strength: float = 0.0,
    transmission: float = 0.0,
    coat: float = 0.0,
    subsurface: float = 0.0,
) -> bpy.types.Material:
    key = (name, color, roughness, metallic, emission, emission_strength, transmission, coat, subsurface)
    if key in _CACHE:
        return _CACHE[key]
    mat = bpy.data.materials.new(name)
    bsdf = _principled(mat)
    bsdf.inputs["Base Color"].default_value = hex_to_linear(color)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Transmission Weight"].default_value = transmission
    bsdf.inputs["Coat Weight"].default_value = coat
    if subsurface:
        bsdf.inputs["Subsurface Weight"].default_value = subsurface
        bsdf.inputs["Subsurface Radius"].default_value = (0.3, 0.15, 0.1)
        bsdf.inputs["Subsurface Scale"].default_value = 0.05
    if emission:
        bsdf.inputs["Emission Color"].default_value = hex_to_linear(emission)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    mat.diffuse_color = hex_to_linear(color)
    _CACHE[key] = mat
    return mat


def emission_socket(mat: bpy.types.Material):
    return mat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]


def noise_ground(
    name: str, color_a: str, color_b: str, scale: float = 3.0, roughness: float = 0.85, bump: float = 0.3
) -> bpy.types.Material:
    """Two-tone procedural ground (grass, dirt) with bump. Generated, no image textures."""
    mat = bpy.data.materials.new(name)
    bsdf = _principled(mat)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 6.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = hex_to_linear(color_a)
    ramp.color_ramp.elements[1].color = hex_to_linear(color_b)
    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = scale * 40
    bump_node = nodes.new("ShaderNodeBump")
    bump_node.inputs["Strength"].default_value = bump
    links.new(coord.outputs["Object"], noise.inputs["Vector"])
    links.new(coord.outputs["Object"], fine.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(fine.outputs["Fac"], bump_node.inputs["Height"])
    links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def paver_ground(
    name: str,
    colors=("#4a4744", "#5c5853", "#3d3b39"),
    mortar: str = "#262422",
    size: float = 0.6,
    roughness: float = 0.3,
) -> bpy.types.Material:
    """Wet stone paving: slabs in a brick pattern with dark joints, each slab a slightly different shade,
    grooved joints (bump) and damp patches that shine more (roughness varies). Generated, no images."""
    mat = bpy.data.materials.new(name)
    bsdf = _principled(mat)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new("ShaderNodeTexCoord")
    brick = nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.inputs["Scale"].default_value = 1.0 / size
    brick.inputs["Mortar Size"].default_value = 0.025
    brick.inputs["Brick Width"].default_value = 1.0
    brick.inputs["Row Height"].default_value = 0.5
    brick.inputs["Color1"].default_value = hex_to_linear(colors[0])
    brick.inputs["Color2"].default_value = hex_to_linear(colors[1])
    brick.inputs["Mortar"].default_value = hex_to_linear(mortar)
    links.new(coord.outputs["Object"], brick.inputs["Vector"])
    # Grime and damp patches: a large noise darkens some areas and makes them glossier.
    grime = nodes.new("ShaderNodeTexNoise")
    grime.inputs["Scale"].default_value = 0.35
    grime.inputs["Detail"].default_value = 4.0
    links.new(coord.outputs["Object"], grime.inputs["Vector"])
    dark = nodes.new("ShaderNodeMix")
    dark.data_type = "RGBA"
    dark.blend_type = "MULTIPLY"
    dark.inputs["Factor"].default_value = 0.45
    links.new(brick.outputs["Color"], dark.inputs["A"])
    links.new(grime.outputs["Color"], dark.inputs["B"])
    links.new(dark.outputs["Result"], bsdf.inputs["Base Color"])
    wet = nodes.new("ShaderNodeMapRange")
    wet.inputs["To Min"].default_value = roughness * 0.4
    wet.inputs["To Max"].default_value = min(1.0, roughness * 1.8)
    links.new(grime.outputs["Fac"], wet.inputs["Value"])
    links.new(wet.outputs["Result"], bsdf.inputs["Roughness"])
    bump_node = nodes.new("ShaderNodeBump")
    bump_node.inputs["Strength"].default_value = 0.35
    bump_node.inputs["Distance"].default_value = 0.02
    links.new(brick.outputs["Fac"], bump_node.inputs["Height"])
    links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def wet_asphalt(name: str, roughness: float = 0.28) -> bpy.types.Material:
    """Dark asphalt after rain: fine grain, lighter worn patches and shiny wet areas that mirror the lights."""
    mat = noise_ground(name, "#1f2023", "#33343a", scale=1.2, roughness=roughness, bump=0.06)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    coord = next(n for n in nodes if n.type == "TEX_COORD")
    puddles = nodes.new("ShaderNodeTexNoise")
    puddles.inputs["Scale"].default_value = 0.25
    puddles.inputs["Detail"].default_value = 3.0
    links.new(coord.outputs["Object"], puddles.inputs["Vector"])
    shine = nodes.new("ShaderNodeMapRange")
    shine.inputs["From Min"].default_value = 0.45
    shine.inputs["From Max"].default_value = 0.6
    shine.inputs["To Min"].default_value = roughness * 1.6
    shine.inputs["To Max"].default_value = 0.04  # puddles: almost a mirror
    links.new(puddles.outputs["Fac"], shine.inputs["Value"])
    links.new(shine.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def vertex_color_material(
    name: str,
    attribute: str = "Col",
    roughness: float = 0.8,
    emission: str | None = None,
    emission_strength: float = 0.0,
    transmission: float = 0.0,
) -> bpy.types.Material:
    """Base colour from a mesh colour attribute (used for per-block colour jitter)."""
    mat = bpy.data.materials.new(name)
    bsdf = _principled(mat)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = attribute
    links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Transmission Weight"].default_value = transmission
    if emission:
        bsdf.inputs["Emission Color"].default_value = hex_to_linear(emission)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


# --- detailed floors ----------------------------------------------------------------------------------
def _node_math(nodes, links, op, a, b=None, value=None):
    node = nodes.new("ShaderNodeMath")
    node.operation = op
    for i, src in enumerate((a, b)):
        if src is None:
            continue
        if isinstance(src, (int, float)):
            node.inputs[i].default_value = src
        else:
            links.new(src, node.inputs[i])
    if value is not None:
        node.inputs[1].default_value = value
    return node.outputs[0]


def _mix_color(nodes, links, fac, a, b, blend="MIX"):
    mix = nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = blend
    for target, src in ((mix.inputs["Factor"], fac), (mix.inputs["A"], a), (mix.inputs["B"], b)):
        if isinstance(src, (int, float)):
            target.default_value = src
        elif isinstance(src, str):
            target.default_value = hex_to_linear(src)
        else:
            links.new(src, target)
    return mix.outputs["Result"]


def city_asphalt(
    name: str, lanes=(-2.35, 2.1), road_half: float = 4.0, base=("#2a2b2f", "#34353a"), roughness: float = 0.8
) -> bpy.types.Material:
    """A real street: fine aggregate, darker repaired patches, tyre tracks polished by traffic in every lane,
    a grimy gutter along the curbs, thin cracks and oil stains. All procedural (object coordinates, the road
    runs along x)."""
    mat = bpy.data.materials.new(name)
    bsdf = _principled(mat)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new("ShaderNodeTexCoord").outputs["Object"]
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coord, sep.inputs["Vector"])
    y = sep.outputs["Y"]

    def tex(kind, scale, **inputs):
        node = nodes.new(kind)
        node.inputs["Scale"].default_value = scale
        for key, value in inputs.items():
            node.inputs[key].default_value = value
        links.new(coord, node.inputs["Vector"])
        return node

    grain = tex("ShaderNodeTexNoise", 90.0, Detail=2.0)  # aggregate
    patches = tex("ShaderNodeTexVoronoi", 0.09)  # repaired areas, a cell each
    stains = tex("ShaderNodeTexNoise", 0.7, Detail=3.0)
    cracks = nodes.new("ShaderNodeTexVoronoi")
    cracks.feature = "DISTANCE_TO_EDGE"
    cracks.inputs["Scale"].default_value = 0.55
    links.new(coord, cracks.inputs["Vector"])
    crack_mask = tex("ShaderNodeTexNoise", 0.25, Detail=2.0)

    color = _mix_color(nodes, links, grain.outputs["Fac"], base[0], base[1])
    patch = _node_math(nodes, links, "GREATER_THAN", patches.outputs["Color"], value=0.62)
    color = _mix_color(nodes, links, _node_math(nodes, links, "MULTIPLY", patch, value=0.5), color, "#1d1e21")
    # Tyre tracks: two polished bands per lane.
    tracks = None
    for lane in lanes:
        for off in (-0.8, 0.8):
            d = _node_math(nodes, links, "SUBTRACT", y, value=lane + off)
            band = _node_math(
                nodes,
                links,
                "EXPONENT",
                _node_math(nodes, links, "MULTIPLY", _node_math(nodes, links, "MULTIPLY", d, d), value=-14.0),
            )
            tracks = band if tracks is None else _node_math(nodes, links, "MAXIMUM", tracks, band)
    color = _mix_color(nodes, links, _node_math(nodes, links, "MULTIPLY", tracks, value=0.35), color, "#1a1b1e")
    # Gutter grime along both curbs.
    edge = _node_math(nodes, links, "GREATER_THAN", _node_math(nodes, links, "ABSOLUTE", y), value=road_half - 0.45)
    color = _mix_color(nodes, links, _node_math(nodes, links, "MULTIPLY", edge, value=0.55), color, "#17171a")
    # Oil stains in the lanes.
    oil = _node_math(nodes, links, "GREATER_THAN", stains.outputs["Fac"], value=0.66)
    color = _mix_color(nodes, links, _node_math(nodes, links, "MULTIPLY", oil, value=0.35), color, "#151517")
    # Thin cracks, only in some areas.
    line = _node_math(nodes, links, "LESS_THAN", cracks.outputs["Distance"], value=0.012)
    crack = _node_math(
        nodes, links, "MULTIPLY", line, _node_math(nodes, links, "GREATER_THAN", crack_mask.outputs["Fac"], value=0.55)
    )
    color = _mix_color(nodes, links, crack, color, "#0b0b0c")
    links.new(color, bsdf.inputs["Base Color"])
    rough = _node_math(nodes, links, "SUBTRACT", roughness, _node_math(nodes, links, "MULTIPLY", tracks, value=0.3))
    rough = _node_math(nodes, links, "SUBTRACT", rough, _node_math(nodes, links, "MULTIPLY", oil, value=0.08))
    links.new(rough, bsdf.inputs["Roughness"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.01
    height = _node_math(
        nodes, links, "SUBTRACT", grain.outputs["Fac"], _node_math(nodes, links, "MULTIPLY", crack, value=1.5)
    )
    links.new(height, bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def worn_paint(name: str, color: str = "#eeeeea") -> bpy.types.Material:
    """Road paint worn by traffic: patchy, with the asphalt showing through."""
    mat = bpy.data.materials.new(name)
    bsdf = _principled(mat)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6.0
    noise.inputs["Detail"].default_value = 6.0
    links.new(nodes.new("ShaderNodeTexCoord").outputs["Object"], noise.inputs["Vector"])
    wear = _node_math(nodes, links, "GREATER_THAN", noise.outputs["Fac"], value=0.6)
    links.new(_mix_color(nodes, links, wear, color, "#3a3a3d"), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.6
    return mat


def wood_planks(name: str, tones=("#8a5a36", "#a8744a"), roughness: float = 0.45) -> bpy.types.Material:
    """Parquet: long planks of slightly different shades, staggered joints and a wood grain."""
    mat = bpy.data.materials.new(name)
    bsdf = _principled(mat)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new("ShaderNodeTexCoord").outputs["Object"]
    brick = nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.4
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Brick Width"].default_value = 1.4
    brick.inputs["Row Height"].default_value = 0.16
    brick.inputs["Mortar Size"].default_value = 0.004
    brick.inputs["Color1"].default_value = hex_to_linear(tones[0])
    brick.inputs["Color2"].default_value = hex_to_linear(tones[1])
    brick.inputs["Mortar"].default_value = hex_to_linear("#2a1a10")
    links.new(coord, brick.inputs["Vector"])
    grain = nodes.new("ShaderNodeTexWave")
    grain.wave_type = "BANDS"
    grain.inputs["Scale"].default_value = 18.0
    grain.inputs["Distortion"].default_value = 6.0
    grain.inputs["Detail"].default_value = 3.0
    links.new(coord, grain.inputs["Vector"])
    color = _mix_color(nodes, links, 0.22, brick.outputs["Color"], grain.outputs["Color"], "MULTIPLY")
    links.new(color, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.2
    bump.inputs["Distance"].default_value = 0.005
    links.new(brick.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def floor_tiles(name: str, a: str = "#e8e4dc", b: str = "#2f3033", size: float = 0.3) -> bpy.types.Material:
    """Square tiles with grout lines (kitchen, café), a little dirt and a soft shine."""
    mat = bpy.data.materials.new(name)
    bsdf = _principled(mat)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new("ShaderNodeTexCoord").outputs["Object"]
    checker = nodes.new("ShaderNodeTexChecker")
    checker.inputs["Scale"].default_value = 1.0 / size
    checker.inputs["Color1"].default_value = hex_to_linear(a)
    checker.inputs["Color2"].default_value = hex_to_linear(b)
    links.new(coord, checker.inputs["Vector"])
    grout = nodes.new("ShaderNodeTexBrick")
    grout.offset = 0.0
    grout.inputs["Scale"].default_value = 1.0 / size
    grout.inputs["Brick Width"].default_value = 1.0
    grout.inputs["Row Height"].default_value = 1.0
    grout.inputs["Mortar Size"].default_value = 0.012
    links.new(coord, grout.inputs["Vector"])
    dirt = nodes.new("ShaderNodeTexNoise")
    dirt.inputs["Scale"].default_value = 2.0
    links.new(coord, dirt.inputs["Vector"])
    color = _mix_color(nodes, links, grout.outputs["Fac"], checker.outputs["Color"], "#8f8a82")
    color = _mix_color(nodes, links, 0.12, color, dirt.outputs["Color"], "MULTIPLY")
    links.new(color, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.25
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.3
    bump.inputs["Distance"].default_value = 0.004
    links.new(grout.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def grass_ground(name: str, colors=("#4f7a2a", "#8aa040")) -> bpy.types.Material:
    """Lawn: clumps of different greens, dry yellowish patches, fine blade-like streaks and bump."""
    mat = bpy.data.materials.new(name)
    bsdf = _principled(mat)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new("ShaderNodeTexCoord").outputs["Object"]
    clumps = nodes.new("ShaderNodeTexVoronoi")
    clumps.inputs["Scale"].default_value = 4.0
    links.new(coord, clumps.inputs["Vector"])
    big = nodes.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = 0.08
    big.inputs["Detail"].default_value = 4.0
    links.new(coord, big.inputs["Vector"])
    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 40.0
    fine.inputs["Detail"].default_value = 8.0
    links.new(coord, fine.inputs["Vector"])
    color = _mix_color(nodes, links, clumps.outputs["Distance"], colors[1], colors[0])
    dry = _node_math(nodes, links, "GREATER_THAN", big.outputs["Fac"], value=0.6)
    color = _mix_color(nodes, links, _node_math(nodes, links, "MULTIPLY", dry, value=0.45), color, "#a99a52")
    color = _mix_color(nodes, links, 0.55, color, fine.outputs["Color"], "MULTIPLY")
    links.new(color, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.8
    links.new(fine.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat
