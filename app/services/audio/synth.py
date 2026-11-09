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
    # First person: a heartbeat (lub-dub, ~75 bpm) for fear.
    "heartbeat": (
        1.6,
        "aevalsrc='0.95*sin(2*PI*52*t)*(exp(-26*(t))*gte(t,0)+0.7*exp(-26*(t-0.24))*gte(t,0.24)"
        "+exp(-26*(t-0.8))*gte(t,0.8)+0.7*exp(-26*(t-1.04))*gte(t,1.04))':d={d}",
        "lowpass=f=140,volume=1.3",
    ),
    # First person: panting while running (two breaths a second, in and out).
    "breath": (
        2.0,
        "anoisesrc=color=pink:amplitude=0.9:duration={d}",
        "bandpass=f=1300:w=1.4,volume='2.4*pow(sin(2*PI*t),4)':eval=frame,lowpass=f=3500",
    ),
    # First person: running footsteps on pavement (three a second).
    "steps": (
        2.0,
        "aevalsrc='(random(0)-0.5)*1.6*exp(-38*mod(t,0.33))+0.6*sin(2*PI*90*t)*exp(-50*mod(t,0.33))':d={d}",
        "lowpass=f=1100,highpass=f=60",
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

# Chord progressions as semitones above A3 (220 Hz) for root, third and fifth. Every video picks one
# progression, a key shift and a tempo from its seed, so the channel's music never sounds like a template.
PROGRESSIONS = (
    ((0, 3, 7), (-4, 0, 3), (-9, -5, -2), (-2, 2, 5)),  # Am F C G (wistful)
    ((0, 3, 7), (-2, 2, 5), (-4, 0, 3), (-5, -1, 2)),  # Am G F E-ish (descending, tense)
    ((-9, -5, -2), (-2, 2, 5), (0, 3, 7), (-4, 0, 3)),  # C G Am F (bright)
    ((0, 3, 7), (5, 8, 12), (-4, 0, 3), (-2, 2, 5)),  # Am Dm F G (curious)
    ((-4, 0, 3), (-2, 2, 5), (0, 3, 7), (0, 3, 7)),  # F G Am Am (rising)
)
KEY_SHIFTS = (-3, -2, 0, 2, 3)
CHORD_SECONDS = (3.5, 4.0, 4.5, 5.0)


def music_variant(variant: int) -> tuple[tuple[tuple[float, ...], ...], float]:
    """Chords (Hz) and seconds per chord for a variant number (e.g. the video's seed)."""
    progression = PROGRESSIONS[variant % len(PROGRESSIONS)]
    shift = KEY_SHIFTS[(variant // len(PROGRESSIONS)) % len(KEY_SHIFTS)]
    seconds = CHORD_SECONDS[(variant // 7) % len(CHORD_SECONDS)]
    chords = tuple(tuple(round(220.0 * 2 ** ((n + shift) / 12), 2) for n in chord) for chord in progression)
    return chords, seconds


def generate_music(
    ffmpeg: FFmpeg,
    duration_seconds: float,
    output_path: Path,
    chord_seconds: float = 4.0,
    variant: int | None = None,
) -> Path:
    """Ambient pad: soft chord progression with slow swell, a sub-bass pulse and gentle reverb.
    With a variant number the key, progression and tempo change (one variant per video)."""
    chords = CHORDS
    if variant is not None:
        chords, chord_seconds = music_variant(variant)
    period = chord_seconds * len(chords)

    def voice(index: int) -> str:
        notes = [chord[index] for chord in chords]
        # Pick the chord's note for the current time slot.
        freq = notes[-1]
        for i in reversed(range(len(chords) - 1)):
            freq = f"if(lt(mod(t,{period}),{chord_seconds * (i + 1)}),{notes[i]},{freq})"
        return f"sin(2*PI*({freq})*t)"

    swell = f"(0.6+0.4*sin(2*PI*t/{chord_seconds}-PI/2))"
    bass = f"0.25*sin(2*PI*({chords[0][0] / 2})*t)*(0.5+0.5*sin(2*PI*t/{chord_seconds * 2}))"
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
