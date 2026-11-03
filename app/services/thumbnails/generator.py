"""Thumbnails from the rendered video itself (never AI images): the most striking frame plus
2-5 bold words, as 1280x720 (YouTube's standard thumbnail) and a 9:16 cover for Shorts."""

from __future__ import annotations

from pathlib import Path

from app.services.rendering.ffmpeg import FFmpeg, escape_filter_value

FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
    "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _font() -> str | None:
    return next((f for f in FONT_CANDIDATES if Path(f).is_file()), None)


def _text_filter(text: str, size_expr: str, y_expr: str) -> str:
    font = _font()
    font_arg = f"fontfile={escape_filter_value(font)}:" if font else ""
    safe = escape_filter_value(text.upper())
    return (
        f"drawtext={font_arg}text={safe}:fontsize={size_expr}:fontcolor=white:borderw=8:bordercolor=black@0.85:"
        f"x=(w-text_w)/2:y={y_expr}:line_spacing=10"
    )


def generate_thumbnails(ffmpeg: FFmpeg, video: Path, at_seconds: float, text: str, out_dir: Path) -> dict:
    """Returns {"landscape": path (1280x720 JPEG), "vertical": path (1080x1920 JPEG)}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = out_dir / "thumbnail_frame.png"
    ffmpeg.run(
        [
            ffmpeg.ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{at_seconds:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(frame),
        ]
    )
    landscape, vertical = out_dir / "thumbnail_1280x720.jpg", out_dir / "thumbnail_1080x1920.jpg"
    # Landscape: blurred, zoomed copy fills the frame behind the sharp shot, then the words on top.
    ffmpeg.run(
        [
            ffmpeg.ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(frame),
            "-filter_complex",
            "[0]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,gblur=sigma=18,eq=brightness=-0.08[bg];"
            "[0]scale=-2:720[fg];[bg][fg]overlay=(W-w)/2:0,eq=contrast=1.08:saturation=1.15,"
            + _text_filter(text, "88", "h-text_h-60"),
            "-q:v",
            "2",
            str(landscape),
        ]
    )
    ffmpeg.run(
        [
            ffmpeg.ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(frame),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=contrast=1.08:saturation=1.15,"
            + _text_filter(text, "110", "h*0.18"),
            "-q:v",
            "2",
            str(vertical),
        ]
    )
    return {"landscape": landscape, "vertical": vertical}


def best_moment(report: dict) -> tuple[int, float]:
    """(scene index, seconds into that scene) of the most striking image: 60 % into the climax scene,
    else into the last escalation. Taken from the scene's clip, so no subtitles are burned in."""
    scenes = report.get("scenes", [])
    for beat in ("climax", "escalation"):
        chosen = [s for s in scenes if s.get("beat") == beat]
        if chosen:
            scene = chosen[0] if beat == "climax" else chosen[-1]
            return scene["index"], scene["duration"] * 0.6
    return (scenes[0]["index"], scenes[0]["duration"] * 0.5) if scenes else (0, 0.5)
