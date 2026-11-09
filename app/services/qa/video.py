"""Automatic QA for a produced video: technical data, empty or frozen segments, silences,
subtitles inside their voice line, loudness, and a contact sheet for human review."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=False).stderr


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    info = json.loads(out)
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


def segments(log: str, start_key: str, end_key: str) -> list[tuple[float, float]]:
    starts = [float(x) for x in re.findall(rf"{start_key}:\s*([\d.]+)", log)]
    ends = [float(x) for x in re.findall(rf"{end_key}:\s*([\d.]+)", log)]
    return [(round(a, 2), round(b, 2)) for a, b in zip(starts, ends, strict=False)]


def check_video(video: Path, frames: int = 8, report_path: Path | None = None, srt: Path | None = None) -> dict:
    info = probe(video)
    duration = info["duration_seconds"]

    black = segments(
        run(["ffmpeg", "-i", str(video), "-vf", "blackdetect=d=0.25:pix_th=0.06", "-an", "-f", "null", "-"]),
        "black_start",
        "black_end",
    )
    frozen = segments(
        run(["ffmpeg", "-i", str(video), "-vf", "freezedetect=n=0.0015:d=1.2", "-an", "-f", "null", "-"]),
        "freeze_start",
        "freeze_end",
    )
    silence = segments(
        run(["ffmpeg", "-i", str(video), "-af", "silencedetect=n=-45dB:d=0.8", "-vn", "-f", "null", "-"]),
        "silence_start",
        "silence_end",
    )
    loud = run(["ffmpeg", "-i", str(video), "-af", "ebur128=peak=true", "-vn", "-f", "null", "-"])
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
    subprocess.run(
        [
            "ffmpeg",
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
        ],
        check=False,
    )

    problems = []
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
        "contact_sheet": str(sheet),
        "frame_times": [round(t, 2) for t in times],
        "problems": problems,
        "passed": not problems,
    }
    return result
