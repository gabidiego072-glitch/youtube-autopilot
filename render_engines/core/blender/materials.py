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
