"""One scene per sentence: long narration lines are split into short beats, each with its own scene.

Audit of Nov 11: the daily videos had one static scene per line, and lines of 18-27 words (5-9 s), so the
homeless video showed the same street for 31 s across four lines. Splitting each line at its sentences (and,
for long sentences, at a clause) gives every idea its own picture of about 2-4 s, like the reference videos.
The voice stays one clip per line (natural prosody); only the picture is split: the line's clip is made of
one sub-scene per beat, cut together.
"""

from __future__ import annotations

import re

MIN_WORDS = 5  # shorter pieces join their neighbour (a 1-second scene reads as a glitch)
MAX_WORDS = 11  # a sentence longer than this is split at a clause if it has one
MAX_PIECES = 3
CLAUSE = re.compile(r",\s+|\s+(?=(?:y|pero|mientras|and|but|while|so)\s)", re.IGNORECASE)
SENTENCE = re.compile(r"(?<=[.!?;:…])\s+")


def split_line(text: str) -> list[str]:
    """A narration line in short pieces that each say one thing (text is kept exactly, word for word)."""
    pieces: list[str] = []
    for sentence in (s for s in SENTENCE.split(text.strip()) if s):
        if len(sentence.split()) <= MAX_WORDS:
            pieces.append(sentence)
            continue
        parts, start = [], 0
        for m in CLAUSE.finditer(sentence):
            left = sentence[start : m.start() + (1 if sentence[m.start()] == "," else 0)].strip()
            if len(left.split()) >= MIN_WORDS and len(sentence[m.end() :].split()) >= MIN_WORDS:
                parts.append(left)
                start = m.end()
        parts.append(sentence[start:].strip())
        pieces += [p for p in parts if p]
    merged: list[str] = []
    lead_in = ""  # a short opening clause ("Al tercer día,") goes with what follows it
    for piece in pieces:
        if lead_in:
            piece, lead_in = f"{lead_in} {piece}", ""
        if len(piece.split()) < MIN_WORDS:
            if piece.rstrip().endswith(",") or not merged:
                lead_in = piece
            else:
                merged[-1] = f"{merged[-1]} {piece}"
            continue
        merged.append(piece)
    if lead_in:
        merged = [*merged[:-1], f"{merged[-1]} {lead_in}"] if merged else [lead_in]
    while len(merged) > MAX_PIECES:  # join the shortest neighbouring pair
        k = min(range(len(merged) - 1), key=lambda i: len(merged[i].split()) + len(merged[i + 1].split()))
        merged[k : k + 2] = [f"{merged[k]} {merged[k + 1]}"]
    return merged or [text]


def beats_for(scenes: list[dict]) -> list[dict]:
    """Every line's pieces as beats {line, narration, share, hud, visual}; the last line (the ending, which
    loops back into the start) stays whole. `share` is the piece's part of the line, by words."""
    beats: list[dict] = []
    for i, scene in enumerate(scenes):
        pieces = [scene["narration"]] if i == len(scenes) - 1 else split_line(scene["narration"])
        total = sum(len(p.split()) for p in pieces) or 1
        for piece in pieces:
            beats.append(
                {
                    "line": i,
                    "narration": piece,
                    "share": len(piece.split()) / total,
                    "hud": scene.get("hud", ""),
                    "visual": scene.get("visual", ""),
                    "speaker": scene.get("speaker", ""),
                }
            )
    return beats
