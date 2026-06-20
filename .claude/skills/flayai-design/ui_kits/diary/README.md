# flayAI — Diary UI kit

The "private space" counterpart to the tool screens. Same app shell, but the
`.diary-mood` scope re-tints the semantic tokens to a warm cream palette and
switches the body to a serif (`--font-serif`), so the whole surface reads as a
journal rather than a utility.

## Screen
`index.html` — a reflective chat:
- **Recall cards** — when the assistant remembers past entries it surfaces
  amber-tinted `RecallCard`s (date pill + weather glyph + title + original text)
  under a "그때 일기 N건" label.
- **Bubbles** — user messages are Apple-blue, right-aligned with a tucked
  corner; the assistant replies in a soft muted bubble. A bouncing three-dot
  typing indicator shows while streaming.
- **Composer** — the same `Composer` primitive, with the journaling placeholder.

## Components used
`Composer`, `ThemeToggle`, plus bespoke `RecallCard` / bubbles specific to the
diary.

## Notes
The warm tone, casual banmal copy, and weather glyphs are core to the diary's
identity — see README "Content fundamentals" + "Diary mood".
