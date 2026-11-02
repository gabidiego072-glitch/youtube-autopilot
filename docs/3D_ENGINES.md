# 3D science-visualisation engine

A procedural 3D engine that runs inside **Blender in background mode** and renders with **Cycles on the CPU**
(no GPU needed). It illustrates "What would happen if...?" scenarios that are about scale, growth or motion
(a person growing with every step, objects at extreme speed...) when AI image/video generation is not
available, at zero cost. **FFmpeg** is used only at the end, to encode, add audio and burn in subtitles.

The earlier voxel / game-style engine was removed when the channel's editorial line was fixed (no video games);
it remains in git history.

| Engine | Builds | Example |
| --- | --- | --- |
| `cinematic` | characters from primitives on a pivot rig, procedural meadow (terrain, trees, rocks, flowers, hills), Nishita sky, sun/fill/practical lights, depth of field, motion blur, lens glow; actions: walk, grow, turn, raise_arm, wave, jump, look_at, light_on | `examples/scenes/what_if_grow_each_step.json` |

## Requirements

- Blender 4.5 LTS (tested with 4.5.15): `scripts/install_blender.sh` downloads the official build and verifies
  its SHA-256 checksum. Point `BLENDER_BINARY` at it, or put it on `PATH`.
- FFmpeg with libx264 and libass (subtitles).
- The backend's Python environment (`pip install -r requirements-dev.txt`).

```bash
scripts/install_blender.sh /opt/blender
export BLENDER_BINARY=/opt/blender/blender-4.5.15-linux-x64/blender
```

## Render the example

Run from the repository root. Blender renders the frames, then FFmpeg encodes
`out/<spec>_<aspect>.mp4` with a synthesized ambient soundtrack and the spec's captions burned in.

```bash
# "¿Qué pasaría si cada paso que das crecieras un centímetro?" (8 s)
python scripts/render_3d.py examples/scenes/what_if_grow_each_step.json --aspect 9:16 --quality draft --ambient
python scripts/render_3d.py examples/scenes/what_if_grow_each_step.json --aspect 16:9 --quality draft --ambient
```

Useful options: `--quality test|draft|preview|final`, `--output path.mp4`, `--max-frames N` (quick check),
`--scale 0.25` / `--samples 4` (override resolution and samples), `--audio file.wav` (your own soundtrack),
`--no-subtitles`, `--reuse-frames` (re-encode without re-rendering), `--threads N`.

Quick 1-second smoke test (about 15 s):

```bash
python scripts/render_3d.py examples/scenes/what_if_grow_each_step.json --quality test --max-frames 24 -o out/smoke.mp4
```

### Blender only (no backend)

The engines need nothing but Blender. This renders PNG frames directly:

```bash
blender --background --factory-startup --python render_engines/run.py -- \
  --spec examples/scenes/what_if_grow_each_step.json --aspect 9:16 --quality draft --frames-dir out/frames
```

Add `--save-blend out/scene.blend` to inspect the generated scene in the Blender UI.

### Quality presets and measured speed

| Preset | 16:9 size | Samples | Use |
| --- | --- | --- | --- |
| `test` | 192×108 | 1 | automated tests |
| `draft` | 960×540 | 12 | iteration, examples |
| `preview` | 1280×720 | 24 | review |
| `final` | 1920×1080 | 64 | publishing |

Draft speed on 4 CPU cores (this sandbox): roughly 6–10 s per frame, so an 8-second, 192-frame clip takes
about 20–30 minutes per aspect ratio. A GPU or more cores reduces that roughly linearly.

## Scene specs

A spec is a JSON file.

```jsonc
{
  "engine": "cinematic",
  "duration_seconds": 8,          // 1-60
  "fps": 24,                      // 24, 25, 30 or 60
  "seed": 7,                      // same seed = same world
  "environment": {...},           // engine-specific (see below)
  "characters": [{"id": "pip", "start": [x, y], "facing": degrees, "palette": {...}}],
  "props": [{"id": "lantern", "type": "lantern_post", "location": [x, y, z], "facing": degrees}],
  "actions": [{"type": "walk", "character": "pip", "from": [x, y], "to": [x, y], "start": s, "end": s}],
  "camera": {
    "fstop": 2.8, "handheld": 0.02, "portrait_lens_scale": 1.2,
    "shots": [{"time": s, "location": [x, y, z], "target": "pip", "lens": 35}]
  },
  "captions": [{"start": s, "end": s, "text": "..."}]
}
```

- **Camera**: position and focal length are keyframed per shot with smooth easing. The camera always aims at
  the shot's `target` (a character, a prop, or `[x, y, z]`), follows moving characters, and blends smoothly when
  the target changes. Focus follows the target. In 9:16 the lens is multiplied by `portrait_lens_scale`.
- **Actions**: `walk`, `grow` (`to_scale`, smooth time-lapse growth; the camera keeps the head framed),
  `turn` (`facing` or `towards`), `raise_arm`, `wave`, `jump`, `look_at` (any id or `camera`), `light_on`
  (lantern). Characters also breathe and blink on their own.
  Environment: `time_of_day` (`dawn`, `day`, `dusk`), `trees`, `rocks`, `flowers`, `fireflies`, `hill_height`.
Walk paths are kept free of trees automatically.

## Code layout

```
render_engines/
  run.py                 Blender entry point (parses args after "--")
  core/                  pure Python, unit-tested without Blender:
    spec.py              spec validation, aspect ratios, quality presets, frame maths
    noise.py             seeded value noise / fBm
    timeline.py          position tracks the camera uses to follow characters
    colors.py            sRGB hex -> linear
  core/blender/          shared bpy helpers: scene/render setup, materials, lights, meshes, camera, keyframes
  cinematic/             character rig, environment, props, action director
app/services/rendering/
  blender.py             runs Blender headless, checks the frames
  ffmpeg.py              encode, audio mux, ambient audio synthesis, subtitles
  scene3d.py             spec -> frames -> MP4 pipeline
scripts/render_3d.py     command-line entry for the pipeline
```

## Known limits (next steps)

- Characters are rigid parts on pivots (no skinned meshes or facial animation yet).
- No lip sync or voice-over yet; audio is a synthesized ambient bed or a file you pass in.
- Renders run locally and one at a time; queueing and cloud workers come later.
