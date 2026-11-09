"""Looks: the same scene drawn in another way, for "what if physics changed" moments.

- xray: everything turns into glowing outlines on black (the scene's edges drawn as light, Freestyle),
  surfaces become nearly invisible dark glass, and the ground is a field of tiny sparkling points (atoms).
  The camera move stays the same, so the edit can cut or flash between the normal render and this one
  at any instant: the world seems to change in front of you.
"""

from __future__ import annotations

import bpy

from render_engines.core.colors import hex_to_linear

GROUND_NAMES = ("Road", "Sidewalk", "Plinth", "Ground", "ground", "t_floor", "Promenade", "Beach", "cross_road")


def apply(look: str, scene, color: str = "#bcd7ff") -> None:
    if look == "xray":
        xray(scene, color)


def _xray_surface(color: str):
    """Almost black, a faint rim where surfaces turn away from the camera (dark glass)."""
    mat = bpy.data.materials.new("look_xray_surface")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = hex_to_linear(color)
    rim = nodes.new("ShaderNodeLayerWeight")
    rim.inputs["Blend"].default_value = 0.15
    power = nodes.new("ShaderNodeMath")
    power.operation = "MULTIPLY"
    power.inputs[1].default_value = 0.16
    links.new(rim.outputs["Facing"], power.inputs[0])
    links.new(power.outputs[0], emit.inputs["Strength"])
    links.new(emit.outputs[0], out.inputs["Surface"])
    return mat


def _sparkle_ground(color: str):
    """Black ground covered with tiny glowing points that twinkle (the atoms of the ground)."""
    mat = bpy.data.materials.new("look_xray_ground")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    coord = nodes.new("ShaderNodeTexCoord")
    vor = nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "F1"
    vor.inputs["Scale"].default_value = 9.0
    links.new(coord.outputs["Object"], vor.inputs["Vector"])
    dots = nodes.new("ShaderNodeMapRange")
    dots.inputs["From Min"].default_value = 0.0
    dots.inputs["From Max"].default_value = 0.16
    dots.inputs["To Min"].default_value = 9.0
    dots.inputs["To Max"].default_value = 0.0
    links.new(vor.outputs["Distance"], dots.inputs["Value"])
    pick = nodes.new("ShaderNodeMath")  # only some cells shine
    pick.operation = "GREATER_THAN"
    pick.inputs[1].default_value = 0.4
    links.new(vor.outputs["Color"], pick.inputs[0])
    strength = nodes.new("ShaderNodeMath")
    strength.operation = "MULTIPLY"
    links.new(dots.outputs["Result"], strength.inputs[0])
    links.new(pick.outputs[0], strength.inputs[1])
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = hex_to_linear(color)
    links.new(strength.outputs[0], emit.inputs["Strength"])
    links.new(emit.outputs[0], out.inputs["Surface"])
    return mat


def xray(scene, color: str = "#bcd7ff") -> None:
    surface, ground = _xray_surface(color), _sparkle_ground(color)
    for obj in scene.objects:
        if obj.type in ("MESH", "CURVE", "FONT"):
            mat = ground if obj.name.startswith(GROUND_NAMES) else surface
            data = obj.data
            if hasattr(data, "materials"):
                if len(data.materials) == 0:
                    data.materials.append(mat)
                for i in range(len(data.materials)):
                    data.materials[i] = mat
        elif obj.type == "LIGHT":
            obj.hide_render = True
    world = scene.world
    if world and world.use_nodes:
        for node in world.node_tree.nodes:
            if node.type == "BACKGROUND":
                for link in list(node.inputs["Color"].links):  # unplug the sky
                    world.node_tree.links.remove(link)
                for link in list(node.inputs["Strength"].links):
                    world.node_tree.links.remove(link)
                node.inputs["Color"].default_value = hex_to_linear("#03050a")
                node.inputs["Strength"].default_value = 1.0
            elif node.type == "TEX_SKY":
                node.mute = True
    tree = scene.node_tree if scene.use_nodes else None
    for node in tree.nodes if tree else []:  # the city haze would tint the black sky
        if node.type == "MIX_RGB":
            node.inputs[2].default_value = hex_to_linear("#03050a")
    # Glowing outlines: silhouettes, creases and borders drawn as light.
    scene.render.use_freestyle = True
    scene.render.line_thickness_mode = "RELATIVE"
    layer = scene.view_layers[0]
    layer.use_freestyle = True
    settings = layer.freestyle_settings
    lineset = settings.linesets[0] if settings.linesets else settings.linesets.new("xray")
    lineset.select_by_visibility = True
    lineset.select_by_edge_types = True
    lineset.select_silhouette = lineset.select_border = lineset.select_crease = True
    style = lineset.linestyle or bpy.data.linestyles.new("xray_lines")
    lineset.linestyle = style
    style.color = hex_to_linear(color)[:3]
    style.thickness = 1.4
    style.alpha = 0.95
