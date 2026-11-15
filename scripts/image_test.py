"""Test of the AI-illustration format (Nov 15): draws one picture per line of a short story with Gemini's image
models, keeping the same characters and style, and writes the pictures plus a report. No upload, no database.

    python scripts/image_test.py --out image_test
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.services.ai.gemini_images import GeminiImages, ImageError  # noqa: E402

STYLE = (
    "Vertical 9:16 frame. Stylised 3D animated-film look: soft rounded shapes, warm cinematic lighting, rich "
    "saturated colours, expressive faces, clean detailed backgrounds, shallow depth of field. No text, no letters, "
    "no captions, no watermark anywhere in the picture."
)
CAST = (
    "Characters: YOU (seen from your own eyes: only your hands and forearms in a dark green sweater at the bottom "
    "of the frame) and LUCIA, your flatmate: woman about 25, curly dark-brown hair in a bun, round glasses, "
    "mustard-yellow hoodie."
)
STORY = [
    (
        "Estás desayunando con Lucía cuando, de golpe, la Tierra se queda sin aire.",
        "Morning kitchen table seen from your eyes: your hands hold a coffee cup; Lucia sits across, startled, "
        "her toast frozen halfway to her mouth; the window light flickers strangely.",
    ),
    (
        "Lucía: «¡No puedo respirar!»",
        "Close-up of Lucia across the table, both hands at her throat, eyes wide in panic, glasses slipping, chair "
        "tipping back; your hand reaches toward her in the foreground.",
    ),
    (
        "Te estallan los oídos: la presión cae a cero.",
        "Your own point of view, blurred at the edges, your hands pressed against your ears; the kitchen tilts; tiny "
        "bubbles float off the surface of the coffee on the table.",
    ),
    (
        "El café de tu taza empieza a hervir sin fuego.",
        "Extreme close-up of the coffee cup on the table, the coffee violently boiling and spraying droplets, "
        "with no stove or flame anywhere; your hand recoils.",
    ),
    (
        "Fuera, los pájaros caen del cielo y los coches se paran en seco.",
        "View through the kitchen window: a city street where birds drop from the sky and cars have stopped at odd "
        "angles, drivers slumped; Lucia's reflection pressed against the glass.",
    ),
    (
        "Cinco segundos después, el aire vuelve con un estruendo que revienta todos los cristales.",
        "The kitchen window exploding inward in a shower of glittering glass shards from a shockwave of air; Lucia "
        "and your hands shielding faces; curtains whipping.",
    ),
    (
        "¿Te escondes bajo la mesa o sales a ayudar?",
        "Lucia crouched under the kitchen table among broken glass, holding out her hand to you, looking straight "
        "at you; behind her the open window shows people lying in the street.",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("image_test"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    images = GeminiImages(get_settings())
    report: dict = {"lines": [], "model": None}
    first: bytes | None = None
    for i, (line, scene) in enumerate(STORY):
        prompt = f"{STYLE}\n{CAST}\nScene: {scene}"
        if first:
            prompt += "\nKeep exactly the same characters, clothes, kitchen and drawing style as the reference picture."
        started = time.monotonic()
        entry = {"line": line}
        try:
            picture = images.draw(prompt, [first] if first else None)
        except ImageError as exc:
            entry["error"] = str(exc)
            report["lines"].append(entry)
            print(f"[image-test] {i}: {exc}")
            continue
        ext = "jpg" if picture[:3] == b"\xff\xd8\xff" else "png"
        path = args.out / f"scene_{i:02d}.{ext}"
        path.write_bytes(picture)
        first = first or picture
        entry.update(file=path.name, seconds=round(time.monotonic() - started, 1), bytes=len(picture))
        report["lines"].append(entry)
        print(f"[image-test] {i}: {path.name} in {entry['seconds']} s with {images.model}")
    report["model"] = images.model
    report["errors"] = images.errors
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"model": images.model, "made": sum("file" in x for x in report["lines"]), "errors": images.errors},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
