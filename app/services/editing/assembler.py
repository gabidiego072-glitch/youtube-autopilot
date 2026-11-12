"""Final edit with FFmpeg only (free).

Timeline: each scene lasts as long as its voice-over plus a short pause. Scenes are
joined with a cross-dissolve ('fade') or a hard cut; to keep the voice in sync, a
scene's clip is rendered longer by the length of the following transition, so the
dissolve eats that tail instead of shifting the timeline.

Audio: voices placed at their exact times, sound effects on cue, a music bed that
ducks under the narration, loudness normalised to YouTube's -14 LUFS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.services.production.formats import FormatSpec
from app.services.rendering.ffmpeg import FFmpeg, ProbeResult, escape_filter_value, write_srt

SCENE_PAUSE = 0.3  # breathing room after each line
VOICE_LEAD = 0.06  # voice starts just after the cut
MIN_SCENE = 1.5
TRANSITIONS = {"cut": 0.0, "fade": 0.35, "flash": 0.3}  # flash: through white, same place, new look
SFX_GAIN = {
    "whoosh": 0.9,
    "impact": 1.0,
    "rumble": 0.8,
    "wind": 0.7,
    "chime": 0.6,
    "heartbeat": 0.9,
    "breath": 0.55,
    "steps": 0.6,
}


@dataclass(frozen=True)
class SceneSlot:
    start: float  # position of the scene in the final video (s)
    duration: float  # time the scene owns before the next one starts (s)
    clip_length: float  # rendered clip length = duration + next transition
    transition_in: str
    transition_seconds: float


def plan_timeline(speech: list[float], transitions: list[str], fps: int, pause: float = SCENE_PAUSE) -> list[SceneSlot]:
    """Scene slots from voice durations. transitions[i] is the transition INTO scene i."""
    if len(speech) != len(transitions):
        raise ValueError("One transition per scene is required.")
    frame = 1 / fps
    # A hard cut is a one-frame dissolve, so the same filter graph handles both.
    lengths = [max(TRANSITIONS.get(t, TRANSITIONS["fade"]), frame) for t in transitions]
    slots, start = [], 0.0
    for i, voice in enumerate(speech):
        duration = round(max(MIN_SCENE, VOICE_LEAD + voice + pause) / frame) * frame
        tail = lengths[i + 1] if i + 1 < len(speech) else 0.0
        slots.append(
            SceneSlot(
                round(start, 4),
                round(duration, 4),
                round(duration + tail, 4),
                transitions[i] if i else "cut",
                lengths[i] if i else 0.0,
            )
        )
        start += duration
    return slots


@dataclass(frozen=True)
class EditScene:
    clip: Path
    voice: Path
    subtitle: str
    speech: float
    slot: SceneSlot
    sfx: list = field(default_factory=list)  # [(path, kind, at_seconds_in_scene)]
    hud: str = ""  # counter shown at the top for the whole scene (POV videos)
    companion: bool = False  # this line is said by the companion (own voice, own subtitle colour)
    phone: str = ""  # a text message from the companion, shown on your phone during the line


@dataclass(frozen=True)
class ColdOpen:
    """The video opens on its most striking moment with the title over it, then the story starts.
    clip: a rendered scene clip; start/length: the excerpt (s); sfx: [(path, kind, at)] during the opening."""

    clip: Path
    start: float
    length: float
    title: str
    sfx: list = field(default_factory=list)


def title_card(title: str, length: float, path: Path, portrait: bool = True) -> Path:
    """Big title over the cold open: fades in and out, centred in the upper part of the frame."""
    w, h = (1080, 1920) if portrait else (1920, 1080)
    size = 100 if portrait else 76
    text = title.replace("{", "(").replace("}", ")").strip()
    words, lines, line = text.split(), [], ""
    for word in words:  # wrap at ~18 characters per line
        if line and len(line) + 1 + len(word) > 16:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    end = f"0:00:{length + 0.4:05.2f}"
    lines = [_highlight_numbers(line) for line in lines]
    path.write_text(
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Title,Liberation Serif,{size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,3,4,"
        "5,60,60,0,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.05,{end},Title,,0,0,0,,{{\\pos({w // 2},{int(h * 0.36)})\\fad(200,300)}}"
        + "\\N".join(lines)
        + "\n",
        encoding="utf-8",
    )
    return path


def _highlight_numbers(line: str) -> str:
    """The premise's number ("100 METROS", "1 AÑO") in big cyan, like the hand-made title cards."""
    words = line.split()
    out, i = [], 0
    while i < len(words):
        if any(ch.isdigit() for ch in words[i]):
            unit = i + 1 < len(words) and words[i + 1].strip("?!.,¿¡").isalpha()
            chunk = words[i] + (f" {words[i + 1]}" if unit else "")
            i += 2 if " " in chunk else 1
            out.append("{\\c&HFFB01E&\\fscx130\\fscy130}" + chunk.upper() + "{\\c&HFFFFFF&\\fscx100\\fscy100}")
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


def subtitle_cues(scenes: list[EditScene], words_per_cue: int) -> list[dict]:
    """Short cues timed across each voice line, proportional to their length in characters."""
    cues = []
    for scene in scenes:
        words = scene.subtitle.split()
        if not words:
            continue
        chunks = [" ".join(words[i : i + words_per_cue]) for i in range(0, len(words), words_per_cue)]
        total = sum(len(c) + 1 for c in chunks)
        t = scene.slot.start + VOICE_LEAD
        colour = COMPANION_COLOUR if scene.companion else ""
        for chunk in chunks:
            length = scene.speech * (len(chunk) + 1) / total
            text = f"{colour}{chunk}</font>" if colour else chunk
            cues.append({"start": round(t, 3), "end": round(t + length, 3), "text": text})
            t += length
    return cues


STORY_WORDS = {
    "es": {"message": "Mensaje", "now": "ahora", "or": "o", "comment": "Comenta A o B · parte 2"},
    "en": {"message": "Message", "now": "now", "or": "or", "comment": "Comment A or B · part 2"},
}
COMPANION_COLOUR = '<font color="#FFD27F">'  # the companion's words in warm yellow, the narrator's in white


def story_overlays(
    scenes: list[EditScene],
    lead: float,
    companion: str,
    choice: dict | None,
    path: Path,
    portrait: bool = True,
    language: str = "es",
) -> Path | None:
    """The personal story on screen: the companion's texts as phone notifications, and the viewer's choice at
    the end ('WHAT WOULD YOU DO? A or B - comment for part 2'), like the reference videos."""
    w, h = (1080, 1920) if portrait else (1920, 1080)
    words = STORY_WORDS.get((language or "es").split("-")[0], STORY_WORDS["es"])
    events = []

    def t(seconds: float) -> str:
        seconds = max(0.0, seconds)
        return f"{int(seconds // 3600)}:{int(seconds % 3600 // 60):02d}:{seconds % 60:05.2f}"

    def clean(text: str) -> str:
        return " ".join(str(text).replace("{", "(").replace("}", ")").split())

    for scene in scenes:
        if not scene.phone.strip():
            continue
        start, end = scene.slot.start + lead + 0.15, scene.slot.start + scene.slot.duration + lead
        name = clean(companion or words["message"])
        events.append(
            f"Dialogue: 1,{t(start)},{t(end)},PhoneHead,,0,0,0,,{{\\pos({w // 2},{int(h * 0.2)})\\fad(150,150)}}"
            f"{name}  ·  {words['now']}"
        )
        events.append(
            f"Dialogue: 1,{t(start)},{t(end)},Phone,,0,0,0,,{{\\pos({w // 2},{int(h * 0.245)})\\fad(150,150)}}"
            f"{clean(scene.phone)}"
        )
    if choice and choice.get("a") and choice.get("b") and scenes:
        last = scenes[-1]
        end = last.slot.start + last.slot.duration + lead
        start = max(last.slot.start + lead, end - 3.2)
        rows = (
            ("Ask", 0.3, clean(choice.get("question") or "?").upper()),
            ("OptA", 0.4, f"A  ·  {clean(choice['a'])}"),
            ("Or", 0.455, words["or"]),
            ("OptB", 0.51, f"B  ·  {clean(choice['b'])}"),
            ("Or", 0.585, words["comment"]),
        )
        for style, y, text in rows:
            place = f"{{\\pos({w // 2},{int(h * y)})\\fad(200,0)}}"
            events.append(f"Dialogue: 2,{t(start)},{t(end)},{style},,0,0,0,,{place}{text}")
    if not events:
        return None
    styles = [
        # name, size, text colour, box colour (BorderStyle 3 = opaque box), bold
        ("PhoneHead", 34, "&H00785AE6", "&H00FFFFFF", 1),
        ("Phone", 44, "&H00202020", "&H00FFFFFF", 0),
        ("Ask", 78, "&H00FFFFFF", "&H00101010", 1),
        ("OptA", 54, "&H00FFFFFF", "&H003C9B1E", 1),
        ("OptB", 54, "&H00FFFFFF", "&H002A2AD0", 1),
        ("Or", 38, "&H00FFFFFF", "&H00101010", 1),
    ]
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {w}",
        f"PlayResY: {h}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
    ]
    for name, size, colour, box, bold in styles:
        boxed = name not in ("Ask", "Or")
        lines.append(
            f"Style: {name},DejaVu Sans,{size},{colour},{colour},{box},{box},{bold},0,0,0,100,100,0,0,"
            f"{3 if boxed else 1},{14 if boxed else 4},0,5,40,40,0,1"
        )
    lines += [
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events,
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def subtitle_style(portrait: bool) -> str:
    size, margin = (15, 78) if portrait else (16, 22)
    return (
        f"FontName=Inter,FontSize={size},Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,"
        f"BackColour=&H64000000,BorderStyle=1,Outline=2.2,Shadow=1.2,Alignment=2,MarginV={margin},"
        f"MarginL=26,MarginR=26"
    )


def hud_style(portrait: bool) -> str:
    size, margin = (13, 40) if portrait else (13, 16)
    return (
        f"FontName=Inter,FontSize={size},Bold=1,PrimaryColour=&H0040D8FF,OutlineColour=&H00101010,"
        f"BorderStyle=1,Outline=1.6,Shadow=0.8,Alignment=6,MarginV={margin},Spacing=1.2"
    )


def assemble_video(
    scenes: list[EditScene],
    output_path: Path,
    *,
    spec: FormatSpec,
    ffmpeg: FFmpeg,
    work_dir: Path,
    music_path: Path | None = None,
    subtitles: bool = True,
    crf: int = 18,
    preset: str = "medium",
    cold_open: ColdOpen | None = None,
    companion: str = "",
    choice: dict | None = None,
    language: str = "es",
) -> ProbeResult:
    if not scenes:
        raise ValueError("Nothing to assemble.")
    work_dir.mkdir(parents=True, exist_ok=True)
    w, h, fps = spec.width, spec.height, spec.fps
    lead = cold_open.length if cold_open else 0.0  # everything of the story starts after the opening
    total = scenes[-1].slot.start + scenes[-1].slot.duration + lead
    args = [ffmpeg.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error"]
    graph = []

    # --- video: normalise every clip, then chain the transitions ----------
    for i, scene in enumerate(scenes):
        args += ["-i", str(scene.clip)]
        graph.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1,"
            f"format=yuv420p,tpad=stop_mode=clone:stop_duration=2,trim=duration={scene.slot.clip_length:.4f},"
            f"setpts=PTS-STARTPTS[c{i}]"
        )
    current = "c0"
    for i, scene in enumerate(scenes[1:], start=1):
        graph.append(
            f"[{current}][c{i}]xfade=transition={'fadewhite' if scene.slot.transition_in == 'flash' else 'fade'}:"
            f"duration={scene.slot.transition_seconds:.4f}:"
            f"offset={scene.slot.start:.4f}[x{i}]"
        )
        current = f"x{i}"
    if cold_open:  # the striking excerpt with the title, then a white flash into the story
        args += ["-i", str(cold_open.clip)]
        graph.append(
            f"[{len(scenes)}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1,"
            f"format=yuv420p,tpad=stop_mode=clone:stop_duration=3,trim=start={cold_open.start:.4f}:"
            f"duration={cold_open.length:.4f},setpts=PTS-STARTPTS[co]"
        )
        graph.append(f"[{current}]fade=t=in:st=0:d=0.25:color=white[story]")
        graph.append("[co][story]concat=n=2:v=1:a=0[opened]")
        card = title_card(cold_open.title, cold_open.length, work_dir / "title.ass", portrait=h > w)
        graph.append(f"[opened]subtitles=filename={escape_filter_value(str(card))}[titled]")
        current = "titled"
    hud_cues = [
        {
            "start": round(s.slot.start + lead, 3),
            "end": round(s.slot.start + s.slot.duration + lead, 3),
            "text": s.hud.strip(),
        }
        for s in scenes
        if s.hud.strip()
    ]
    if hud_cues:  # e.g. "DÍA 2 · 21:10", top of the frame, above everything
        hud = write_srt(hud_cues, work_dir / "hud.srt")
        graph.append(
            f"[{current}]subtitles=filename={escape_filter_value(str(hud))}:force_style='{hud_style(h > w)}'[hud]"
        )
        current = "hud"
    if subtitles:
        cues = [
            {**c, "start": c["start"] + lead, "end": c["end"] + lead} for c in subtitle_cues(scenes, 4 if h > w else 8)
        ]
        srt = write_srt(cues, work_dir / "subtitles.srt")
        graph.append(
            f"[{current}]subtitles=filename={escape_filter_value(str(srt))}:force_style='{subtitle_style(h > w)}'[vout]"
        )
    else:
        graph.append(f"[{current}]null[vout]")
    overlays = story_overlays(
        scenes, lead, companion, choice, work_dir / "story.ass", portrait=h > w, language=language
    )
    if overlays is not None:  # phone notifications and the final choice, on top of everything
        graph[-1] = graph[-1][: graph[-1].rindex("[vout]")] + "[subbed]"
        graph.append(f"[subbed]subtitles=filename={escape_filter_value(str(overlays))}[vout]")

    # --- audio: voices on their exact times, effects on cue, ducked music --
    index = len(scenes) + (1 if cold_open else 0)
    voice_labels, sfx_labels = [], []
    for i, scene in enumerate(scenes):
        args += ["-i", str(scene.voice)]
        delay = round((scene.slot.start + VOICE_LEAD + lead) * 1000)
        graph.append(f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={delay}:all=1[vo{i}]")
        voice_labels.append(f"[vo{i}]")
        index += 1
    effects = [
        (f"{i}_{j}", path, kind, scene.slot.start + at + lead)
        for i, scene in enumerate(scenes)
        for j, (path, kind, at) in enumerate(scene.sfx)
    ]
    if cold_open:  # the opening's own hits, at absolute times
        effects += [(f"open_{j}", path, kind, at) for j, (path, kind, at) in enumerate(cold_open.sfx)]
    for label, path, kind, when in effects:
        args += ["-i", str(path)]
        graph.append(
            f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,volume={SFX_GAIN.get(kind, 0.8)},"
            f"adelay={round(max(0.0, when) * 1000)}:all=1[fx{label}]"
        )
        sfx_labels.append(f"[fx{label}]")
        index += 1
    graph.append(
        f"{''.join(voice_labels)}amix=inputs={len(voice_labels)}:normalize=0:duration=longest,volume=1.6[speech]"
    )
    graph.append("[speech]asplit=2[speech_out][speech_key]")
    mix_inputs = ["[speech_out]"]
    if music_path is not None:
        args += ["-i", str(music_path)]
        graph.append(f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,volume=1.0[music]")
        graph.append("[music][speech_key]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=450[ducked]")
        mix_inputs.append("[ducked]")
        index += 1
    else:
        graph.append("[speech_key]anullsink")
    if sfx_labels:
        graph.append(f"{''.join(sfx_labels)}amix=inputs={len(sfx_labels)}:normalize=0:duration=longest[fxbus]")
        mix_inputs.append("[fxbus]")
    graph.append(
        f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:normalize=0:duration=longest,"
        f"atrim=duration={total:.4f},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    script = work_dir / "filter_graph.txt"
    script.write_text(";\n".join(graph), encoding="utf-8")
    ffmpeg.run(
        [
            *args,
            "-filter_complex_script",
            str(script),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-t",
            f"{total:.4f}",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return ffmpeg.probe(output_path)
