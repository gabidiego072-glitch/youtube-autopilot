"""Procedural 3D visualisation engine that runs inside Blender (background mode).

It is the free, GPU-less way to illustrate 'What would happen if...?' scenarios
(scale, growth, motion) when AI image/video generation is not available.

Layout:
    core/          pure-Python spec, noise, colour and timeline helpers (no bpy)
    core/blender/  Blender utilities (scene, render, materials, camera, animation)
    cinematic/     characters, environments, props and the action director
"""
