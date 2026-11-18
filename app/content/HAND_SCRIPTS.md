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
