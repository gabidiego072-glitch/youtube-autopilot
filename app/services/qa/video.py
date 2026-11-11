"""Automatic QA for a produced video: technical data, empty or frozen segments, silences,
subtitles inside their voice line, loudness, and a contact sheet for human review.

Every FFmpeg/FFprobe command is checked: a failed analysis or contact sheet is reported as a QA problem,
never silently ignored."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


class QAError(RuntimeError):
    """The video could not be analysed at all (missing executable, unreadable file)."""


def _last_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else "no output"


def run(args: list[str]) -> tuple[int, str]:
    """Run an analysis command; (exit code, stderr). A missing executable is exit code 127."""
    try:
        done = subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return 127, f"executable not found: {args[0]}"
    return done.returncode, done.stderr


def probe(path: Path, ffprobe: str = "ffprobe") -> dict:
    code, out, err = _probe_json(path, ffprobe)
    if code != 0:
        raise QAError(f"ffprobe could not read {path} (exit {code}): {_last_line(err)}")
    try:
        info = json.loads(out)
    except json.JSONDecodeError as exc:
        raise QAError(f"ffprobe gave unreadable output for {path}: {exc}") from exc
    if not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
        raise QAError(f"{path} has no video stream")
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    num, den = video["r_frame_rate"].split("/")
    return {
        "container": info["format"]["format_name"],
        "duration_seconds": round(float(info["format"]["duration"]), 3),
        "size_mb": round(int(info["format"]["size"]) / 1e6, 2),
        "bitrate_kbps": round(int(info["format"]["bit_rate"]) / 1000),
        "video": {
            "codec": video["codec_name"],
            "profile": video.get("profile"),
            "width": video["width"],
            "height": video["height"],
            "fps": round(int(num) / int(den), 3),
            "pix_fmt": video["pix_fmt"],
            "frames": int(video.get("nb_frames", 0)),
        },
        "audio": None
        if audio is None
        else {"codec": audio["codec_name"], "sample_rate": int(audio["sample_rate"]), "channels": audio["channels"]},
    }


def _probe_json(path: Path, ffprobe: str) -> tuple[int, str, str]:
    args = [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        done = subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return 127, "", f"executable not found: {ffprobe}"
    return done.returncode, done.stdout, done.stderr


def segments(log: str, start_key: str, end_key: str) -> list[tuple[float, float]]:
    starts = [float(x) for x in re.findall(rf"{start_key}:\s*([\d.]+)", log)]
    ends = [float(x) for x in re.findall(rf"{end_key}:\s*([\d.]+)", log)]
    return [(round(a, 2), round(b, 2)) for a, b in zip(starts, ends, strict=False)]


def check_video(
    video: Path,
    frames: int = 8,
    report_path: Path | None = None,
    srt: Path | None = None,
    *,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> dict:
    """`ffmpeg`/`ffprobe` are the executables the app is configured with (settings.ffmpeg_binary and
    settings.ffprobe_binary), so QA runs the same tools as the render. A command that fails is a QA problem."""
    info = probe(video, ffprobe)
    duration = info["duration_seconds"]
    analysis_errors: list[str] = []

    def analyse(name: str, filters: list[str]) -> str:
        code, log = run([ffmpeg, "-hide_banner", "-i", str(video), *filters, "-f", "null", "-"])
        if code != 0:
            analysis_errors.append(f"{name} analysis failed (exit {code}): {_last_line(log)}")
            return ""
        return log

    black = segments(
        analyse("black frames", ["-vf", "blackdetect=d=0.25:pix_th=0.06", "-an"]), "black_start", "black_end"
    )
    frozen = segments(
        analyse("frozen frames", ["-vf", "freezedetect=n=0.0015:d=1.2", "-an"]), "freeze_start", "freeze_end"
    )
    silence = segments(
        analyse("silence", ["-af", "silencedetect=n=-45dB:d=0.8", "-vn"]), "silence_start", "silence_end"
    )
    loud = analyse("loudness", ["-af", "ebur128=peak=true", "-vn"])
    integrated = re.findall(r"I:\s*(-?[\d.]+) LUFS", loud)
    true_peak = re.findall(r"Peak:\s*(-?[\d.]+) dBFS", loud)

    report_path = report_path or video.with_suffix(".report.json")
    subtitle_issues, cue_count = [], 0
    srt = srt or video.parent / video.stem.split("_")[-1] / "edit" / "subtitles.srt"
    if report_path.is_file() and srt.is_file():
        report = json.loads(report_path.read_text())
        lead = float(report.get("lead_seconds", 0.0))  # the cold open shifts the whole story
        windows = [(s["start"] + lead + 0.06, s["start"] + lead + 0.06 + s["voice_seconds"]) for s in report["scenes"]]
        for block in srt.read_text(encoding="utf-8").strip().split("\n\n"):
            lines = block.splitlines()
            times = re.findall(r"(\d+):(\d+):(\d+),(\d+)", lines[1])
            a, b = [int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000 for h, m, s, ms in times]
            cue_count += 1
            if not any(w0 - 0.05 <= a and b <= w1 + 0.05 for w0, w1 in windows):
                subtitle_issues.append({"cue": lines[2], "start": a, "end": b})

    sheet = video.with_name(video.stem + "_frames.png")
    times = [duration * (i + 0.5) / frames for i in range(frames)]
    select = "+".join(f"eq(n\\,{round(t * info['video']['fps'])})" for t in times)
    cols = 4 if frames > 4 else frames
    rows = -(-frames // cols)
    sheet.unlink(missing_ok=True)  # never report an old sheet as this video's
    code, log = run(
        [
            ffmpeg,
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            f"select='{select}',scale=270:-2,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='%{{pts\\:hms}}':x=6:y=6:fontsize=16:fontcolor=yellow:box=1:boxcolor=black@0.6,"
            f"tile={cols}x{rows}",
            "-frames:v",
            "1",
            "-vsync",
            "0",
            str(sheet),
        ]
    )
    sheet_error = None
    if code != 0 or not sheet.is_file() or sheet.stat().st_size == 0:
        sheet_error = f"contact sheet failed (exit {code}): {_last_line(log)}"

    problems = list(analysis_errors)
    if sheet_error:
        problems.append(sheet_error)
    if black:
        problems.append(f"black segments: {black}")
    if frozen:
        problems.append(f"frozen segments: {frozen}")
    if any(b - a > 1.2 for a, b in silence):
        problems.append(f"long silences: {silence}")
    if subtitle_issues:
        problems.append(f"{len(subtitle_issues)} subtitle cues outside their voice line")
    result = {
        "file": str(video),
        **info,
        "loudness_lufs": float(integrated[-1]) if integrated else None,
        "true_peak_dbfs": float(true_peak[-1]) if true_peak else None,
        "black_segments": black,
        "frozen_segments": frozen,
        "silences": silence,
        "subtitle_cues": cue_count,
        "subtitle_issues": subtitle_issues,
        "contact_sheet": None if sheet_error else str(sheet),
        "analysis_errors": analysis_errors + ([sheet_error] if sheet_error else []),
        "frame_times": [round(t, 2) for t in times],
        "problems": problems,
        "passed": not problems,
    }
    return result
