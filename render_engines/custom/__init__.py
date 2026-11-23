"""Scenes written by hand for one video (Nov 23, the owner: "every video its own world, with sense").

A scene spec with "custom": {"module": "steps", "params": {...}} is built by render_engines/custom/<module>.py,
whose build(spec, ctx, scene, params) makes the whole scene (world, character, camera, light). The module is
in the repo, so every render machine has it; the pipeline still adds the voice, captions, music and upload.
"""

from __future__ import annotations

import importlib


def run_custom(spec: dict, ctx, scene) -> None:
    custom = spec["custom"]
    name = str(custom.get("module", "")).strip()
    if not name.isidentifier():
        raise ValueError(f"bad custom module {name!r}")
    module = importlib.import_module(f"render_engines.custom.{name}")
    module.build(spec, ctx, scene, dict(custom.get("params") or {}))
