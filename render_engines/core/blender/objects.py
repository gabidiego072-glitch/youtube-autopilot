"""Mesh and object construction via bmesh/bpy.data (no viewport operators)."""

import bmesh
import bpy
from mathutils import Matrix, Vector


def link(obj: bpy.types.Object, collection: bpy.types.Collection | None = None) -> bpy.types.Object:
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def empty(name: str, location=(0, 0, 0), parent=None, col=None) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = 0.2
    obj.location = location
    obj.parent = parent
    return link(obj, col)


def mesh_object(
    name: str,
    bm: bmesh.types.BMesh,
    material=None,
    smooth: bool = False,
    location=(0, 0, 0),
    rotation=(0, 0, 0),
    scale=(1, 1, 1),
    parent=None,
    col=None,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    if smooth:
        mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    if material is not None:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    obj.location, obj.rotation_euler, obj.scale = location, rotation, scale
    obj.parent = parent
    return link(obj, col)


def _bm() -> bmesh.types.BMesh:
    return bmesh.new()


def sphere(radius=1.0, segments=24, rings=12) -> bmesh.types.BMesh:
    bm = _bm()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius)
    return bm


def icosphere(radius=1.0, subdivisions=2) -> bmesh.types.BMesh:
    bm = _bm()
    bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=radius)
    return bm


def cone(radius_bottom=1.0, radius_top=0.0, depth=2.0, segments=16, base_at_origin=True) -> bmesh.types.BMesh:
    bm = _bm()
    bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius_bottom, radius2=radius_top, depth=depth
    )
    if base_at_origin:
        bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((0, 0, depth / 2)))
    return bm


def box(sx=1.0, sy=1.0, sz=1.0, base_at_origin=False) -> bmesh.types.BMesh:
    bm = _bm()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=Vector((sx, sy, sz)))
    if base_at_origin:
        bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((0, 0, sz / 2)))
    return bm


def capsule(radius=0.1, length=0.5, segments=16) -> bmesh.types.BMesh:
    """Rounded limb hanging down from the origin (top at 0, bottom at -length)."""
    bm = _bm()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=10, radius=radius)
    for v in bm.verts:
        if v.co.z < 0:
            v.co.z -= length - 2 * radius
        v.co.z -= radius
    return bm


def transform(bm: bmesh.types.BMesh, matrix: Matrix) -> bmesh.types.BMesh:
    bmesh.ops.transform(bm, matrix=matrix, verts=bm.verts)
    return bm


def add_subsurf(obj: bpy.types.Object, levels: int = 1) -> None:
    mod = obj.modifiers.new("Subsurf", "SUBSURF")
    mod.levels = levels
    mod.render_levels = levels
