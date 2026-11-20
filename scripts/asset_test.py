"""Show what free 3D models the system finds by itself (Nov 20): one preview per thing, in asset_test/."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.services.ai.factory import get_ai_provider  # noqa: E402
from app.services.assets import finder  # noqa: E402

THINGS = ["airplane", "cat", "parachute", "meteor", "ambulance", "pizza"]


def main() -> int:
    out = Path("asset_test")
    out.mkdir(exist_ok=True)
    os.environ.setdefault("ASSET_CACHE", str(out / "cache"))
    ai = get_ai_provider(get_settings())
    token = bool(os.environ.get("SKETCHFAB_API_TOKEN"))
    report = {"sketchfab_token": token, "found": {}}
    for thing in THINGS:
        found = finder.find_model(thing, ai=ai, blender=os.environ.get("BLENDER_BINARY") or None)
        report["found"][thing] = found
        preview = Path(finder.cache_dir()) / finder.slug(thing) / "preview.png"
        if preview.exists():
            shutil.copy(preview, out / f"{finder.slug(thing)}.png")
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
