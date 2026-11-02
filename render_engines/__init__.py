"""Procedural 3D animation engines that run inside Blender (background mode).

Layout:
    core/          pure-Python spec, noise, colour and timeline helpers (no bpy)
    core/blender/  shared Blender utilities (scene, render, materials, camera, animation)
    cinematic/     smooth stylised characters + environments
    voxel/         block-based characters + procedural worlds

Each engine is self-contained: it only depends on `core`, never on the other engine.
"""
