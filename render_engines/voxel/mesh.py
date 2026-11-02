"""Turn VoxelGrids into Blender meshes: one object, one material slot per block type,
per-block colour jitter stored in a colour attribute."""

from __future__ import annotations

import bpy

from render_engines.core.blender.objects import link
from render_engines.core.colors import hex_to_linear, scale_color
from render_engines.voxel.grid import FACES, VoxelGrid, block_hash

SEE_THROUGH = frozenset({"water", "glass", "leaves", "flower_red", "flower_yellow", "flower_white"})

# Per block type surface properties (base colour comes from the palette).
SURFACES = {
    "water": {"roughness": 0.05, "coat": 0.6},
    "glass": {"roughness": 0.02, "transmission": 0.9},
    "cloud": {"roughness": 1.0, "emission": 0.35},
    "metal": {"roughness": 0.35, "metallic": 0.7},
    "chest_band": {"roughness": 0.4, "metallic": 0.8},
    "chest_lock": {"roughness": 0.25, "metallic": 1.0},
    "shell": {"roughness": 0.3, "coat": 0.5},
    "visor": {"roughness": 0.1, "coat": 1.0},
    "gem": {"roughness": 0.05, "coat": 1.0},
    "crystal": {"roughness": 0.05, "coat": 1.0},
}

_MATERIALS: dict[tuple, bpy.types.Material] = {}


def block_material(block: str, color: str, emission: float = 0.0) -> bpy.types.Material:
    key = (block, color, emission)
    if key in _MATERIALS:
        return _MATERIALS[key]
    props = SURFACES.get(block, {})
    mat = bpy.data.materials.new(f"vox_{block}")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = "Col"
    links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = props.get("roughness", 0.85)
    bsdf.inputs["Metallic"].default_value = props.get("metallic", 0.0)
    bsdf.inputs["Transmission Weight"].default_value = props.get("transmission", 0.0)
    bsdf.inputs["Coat Weight"].default_value = props.get("coat", 0.0)
    strength = emission or props.get("emission", 0.0)
    if strength:
        bsdf.inputs["Emission Color"].default_value = hex_to_linear(color)
        bsdf.inputs["Emission Strength"].default_value = strength
    mat.diffuse_color = hex_to_linear(color)
    _MATERIALS[key] = mat
    return mat


def build_voxel_object(
    name: str,
    grid: VoxelGrid,
    palette: dict[str, str],
    *,
    voxel_size: float = 1.0,
    pivot=(0.0, 0.0, 0.0),
    emissive: dict[str, float] | None = None,
    jitter: float = 0.12,
    seed: int = 0,
    location=(0, 0, 0),
    parent=None,
    col=None,
) -> bpy.types.Object:
    emissive = emissive or {}
    types = sorted({block for block in grid.blocks.values()})
    slot = {block: i for i, block in enumerate(types)}
    verts, faces, mat_index, colors = [], [], [], []
    px, py, pz = pivot
    for (x, y, z), face in grid.exposed_faces(SEE_THROUGH):
        block = grid.blocks[(x, y, z)]
        start = len(verts)
        for cx, cy, cz in FACES[face][1]:
            verts.append(((x + cx - px) * voxel_size, (y + cy - py) * voxel_size, (z + cz - pz) * voxel_size))
        faces.append((start, start + 1, start + 2, start + 3))
        mat_index.append(slot[block])
        shade = 1.0 + (block_hash((x, y, z), seed) - 0.5) * 2 * jitter
        rgba = scale_color(hex_to_linear(palette.get(block, "#ff00ff")), shade)
        colors.extend(rgba * 4)

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    for block in types:
        mesh.materials.append(block_material(block, palette.get(block, "#ff00ff"), emissive.get(block, 0.0)))
    mesh.polygons.foreach_set("material_index", mat_index)
    attribute = mesh.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
    attribute.data.foreach_set("color", colors)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.parent = parent
    return link(obj, col)
