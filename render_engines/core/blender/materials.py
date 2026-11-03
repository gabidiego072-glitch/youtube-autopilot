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
