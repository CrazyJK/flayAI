# flayAI — Search Chat UI kit

The flagship product surface: a natural-language search chatbot over a local
video collection. Korean UI, Apple-restrained chrome, dark/light aware.

## Screens / flow
`index.html` is an interactive click-through:
1. **Empty state** — centered hero `Composer` under "무엇을 찾을까요?", with
   example-query `Chip`s (from the real `examples.json`).
2. **Results stream** — clicking a suggestion (or sending) appends a user
   bubble + an assistant block: a `ToolCallChip` trace (`⚙ search_videos(...)`),
   a `↳ N items` line, then a `repeat(auto-fill, minmax(440px,1fr))` grid of
   `VideoCard`s, then a one-line natural-language summary.
3. **Docked composer** — the compact bottom bar once a conversation exists.

## Components used
`Header` (composes `Tabs variant="text"` + `ThemeToggle`), `Composer`,
`Chip` (suggestions + count/kind options), `VideoCard`, `ToolCallChip`.

## Notes
- Posters are tasteful gradient stand-ins (`POSTER_GRADS`) since the real
  collection isn't shipped. In production, `VideoCard poster={…}` loads
  `/static/posters/{opus}`.
- Search is faked with a 900ms timeout returning canned `RESULTS`.
