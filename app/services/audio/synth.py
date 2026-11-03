"""Code-generated sound: transition and impact effects plus an ambient music bed.

Everything is synthesised with FFmpeg's audio sources, so there are no samples,
no licences and no external downloads.
"""

from __future__ import annotations

from pathlib import Path

from app.services.rendering.ffmpeg import FFmpeg

SAMPLE_RATE = 48000

# Each effect: (duration seconds, lavfi source, filter chain)
SFX = {
    # Air rushing past: pink noise through a sweeping band-pass.
    "whoosh": (
        0.7,
        "anoisesrc=color=pink:amplitude=0.9:duration={d}",
        "bandpass=f=900:w=1.2,volume='0.9*sin(PI*t/{d})':eval=frame,highpass=f=200",
    ),
    # Deep hit: falling sine thump + short noise burst.
    "impact": (
        1.6,
        "aevalsrc='0.9*sin(2*PI*(55-20*t)*t)*exp(-3.2*t)+0.35*(random(0)-0.5)*exp(-18*t)':d={d}",
        "lowpass=f=1800,aecho=0.6:0.5:60:0.25",
    ),
    # Low earthquake-like rumble.
    "rumble": (
        2.5,
        "anoisesrc=color=brown:amplitude=1.0:duration={d}",
        "lowpass=f=140,volume='0.9*sin(PI*t/{d})':eval=frame",
    ),
    # Gale: filtered noise with gusts.
    "wind": (
        4.0,
        "anoisesrc=color=pink:amplitude=0.8:duration={d}",
        "bandpass=f=500:w=1.5,tremolo=f=0.7:d=0.6,volume='0.8*min(1,t*2)*min(1,({d}-t)*1.5)':eval=frame",
    ),
    # Soft bell for the ending.
    "chime": (
        2.5,
        "aevalsrc='0.35*(sin(2*PI*880*t)+0.5*sin(2*PI*1320*t)+0.25*sin(2*PI*1760*t))*exp(-2.2*t)':d={d}",
        "aecho=0.7:0.6:120:0.3",
    ),
}


def generate_sfx(ffmpeg: FFmpeg, kind: str, output_path: Path) -> Path:
    if kind not in SFX:
        raise ValueError(f"Unknown sound effect '{kind}'. Use one of {sorted(SFX)}.")
    duration, source, chain = SFX[kind]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(
        [
            ffmpeg.ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            source.format(d=duration) + f":sample_rate={SAMPLE_RATE}"
            if "aevalsrc" not in source
            else source.format(d=duration) + f":s={SAMPLE_RATE}",
            "-af",
            chain.format(d=duration) + f",afade=t=out:st={max(0.0, duration - 0.2):.2f}:d=0.2",
            "-ac",
            "2",
            "-ar",
            str(SAMPLE_RATE),
            str(output_path),
        ]
    )
    return output_path


# Calm, slightly mysterious progression (A minor - F - C - G), 4 s per chord.
CHORDS = ((220.00, 261.63, 329.63), (174.61, 220.00, 261.63), (130.81, 164.81, 196.00), (196.00, 246.94, 293.66))


def generate_music(ffmpeg: FFmpeg, duration_seconds: float, output_path: Path, chord_seconds: float = 4.0) -> Path:
    """Ambient pad: soft chord progression with slow swell, a sub-bass pulse and gentle reverb."""
    period = chord_seconds * len(CHORDS)

    def voice(index: int) -> str:
        notes = [chord[index] for chord in CHORDS]
        # Pick the chord's note for the current time slot.
        freq = notes[-1]
        for i in reversed(range(len(CHORDS) - 1)):
            freq = f"if(lt(mod(t,{period}),{chord_seconds * (i + 1)}),{notes[i]},{freq})"
        return f"sin(2*PI*({freq})*t)"

    swell = f"(0.6+0.4*sin(2*PI*t/{chord_seconds}-PI/2))"
    bass = f"0.25*sin(2*PI*({CHORDS[0][0] / 2})*t)*(0.5+0.5*sin(2*PI*t/{chord_seconds * 2}))"
    expression = f"0.12*{swell}*({voice(0)}+0.8*{voice(1)}+0.6*{voice(2)})+{bass}*0.4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(
        [
            ffmpeg.ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"aevalsrc='{expression}':s={SAMPLE_RATE}:d={duration_seconds:.2f}",
            "-af",
            "lowpass=f=2200,aecho=0.8:0.7:180|320:0.35|0.25,"
            f"afade=t=in:d=1.5,afade=t=out:st={max(0.0, duration_seconds - 2.0):.2f}:d=2.0",
            "-ac",
            "2",
            "-ar",
            str(SAMPLE_RATE),
            str(output_path),
        ]
    )
    return output_path
