# Hand-written scripts (Claude), Nov 18

A planned topic in `planned_topics.json` may carry `"script"`: the full script JSON (the same fields the AI
writer returns). The pipeline then uses it as it is: Gemini does not write or rewrite it, the storyboard is built
from each line's `shot`, and a fact-check only stops it for an *incorrect* claim. Topics are used in order, one
per run, per language (`"language": "es"` or `"en"`); when the queue is empty the AI writes as before.

Rules each script must pass (`structure_problems`): first beat `hook`, last `ending`, at least 2 `escalation`,
hook at most 12 words, each line at most 16 words (aim for 10), every escalation/climax with `human_subject`,
`consequence` and a claim, English scripts with no Spanish words.

Shot vocabulary (only what the 3D engine shows well):
- recipe: street_watch, street_run, waterfront, park, kitchen, living_room via room_view, reaction (room cafe /
  kitchen / living_room, object), meet_person, hand_action, wake_up, dark_room, theater, space.
- event: none, fire, smoke, explosion, flood, crack, collapse, float (people rise upright), fly (people are flung
  up; NOT cars), freeze (frost).
- time_of_day: day, golden, dusk, night. threat: none, panic, fire, flood, collapse, zombies.

Formula (owner's references): one place, one subject, one continuous journey; a hero counter in `hud`; short
lines; time jumps; dry humour; a twist at the end. Say only what the shot shows.

## Continuity (Nov 23, the owner: "scene by scene, each one following from the last")
- ONE journey in time order: each line happens right after the previous one, where the previous one left you.
  Say the move ("Sales a la calle", "Vuelves al parque", "Llegas al río") whenever the place changes.
- Few places, revisited: the same recipe is the same place (same seed) - start somewhere, go out, come back.
- No jumps to unrelated places or to space unless the line says how you got there.

## The owner's reference "la firma" (Nov 23, 69 s, blocky 3D, 9.9/10 for the owner)
What makes it work, to copy in every script:
1. A protagonist with a goal and a problem in the first 3 s ("everyone shows their fail to their mother...
   except me: I sign for her").
2. ONE recurring object / gag in EVERY scene (the blue 3-loop signature + its sound "¡HUS!"), escalating:
   the exam -> the blackboard -> a bald head -> the whole class pays for it -> the facade -> the football field.
   Ours: the counter is not enough; give each video one thing that comes back in every line (your coffee cup
   in the gravity video, the meteor's light, your phone's 8:20 timer...) and one signature sound for it.
3. Cause -> effect: every scene is the consequence of the previous one, in one small world (school, home).
4. Close-ups that fill the screen with the object (the exam with the big red "2") between the wide shots.
5. A callback twist at the end that uses the recurring gag (the tutor... "cien firmas. Todas mías").
6. Story length: ~70 s works when every second moves the story.

## Better parts for custom kits (Nov 24)

The owner liked the steps video but asked for better cars, crashes, landings and buildings. New kits must build
those with `render_engines/custom/parts.py` instead of plain boxes: `car()` + `drive()`, `building()` / `city()`
(windows, parapet, roof units, door), `landing()` + `shake()`, `crash()`.

## Shorter, looping, opening on the climax (Nov 28, from the channel data)

- 9-10 scenes (~30 s). Since 16 Nov, 55-70 % of viewers swipe away in the first seconds. The best retention so
  far is the steps video, which looped (108 % average viewed).
- Loop ending: the last line leads back into the first (bed → "...que sigue siendo elástica" → the hook).
  `ending_type: "surprising_conclusion"`, `ending_line` = the last line, and no `visual_bible.choice` (the A/B
  card got 0-2 comments per video).
- The video opens on the `climax` scene (1.6 s, with the title) and the hook line plays over it from 0.28 s.
  Put `"cold_open": true` on another scene to open on that one instead (e.g. the plane, the neighbourhood ball
  pit).
- Parts for new kits: `parts.bedroom()` (a kid's room set), `parts.ball_batch()` (thousands of balls in one
  mesh per colour), `rope`, `clouds`, `houses`. Balloon, trampoline and bouncy-ball kits reuse the suburb from
  `balloons.py`.
- Ico subdivisions: 1 = 20 faces (faceted, fine far away), 2 = 80 faces (round, near the camera). Keep a stage
  under ~500k faces.
- Before shipping, test-render every stage: a camera inside a tree crown (street trees at y = STREET_Y ± 8)
  or a house shows a wall of green or white.
