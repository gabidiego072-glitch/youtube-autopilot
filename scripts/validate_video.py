#!/usr/bin/env python3
"""Automatic QA for a produced Short (see app/services/qa/video.py).

python scripts/validate_video.py out/<id>/<id>_draft.mp4 [--frames 8]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.qa.video import check_video  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("--frames", type=int, default=8)
    args = parser.parse_args()
    result = check_video(args.video, args.frames)
    args.video.with_suffix(".qa.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
