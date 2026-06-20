# flayAI Design System

A design system reconstructed from the **flayAI** product — a personal,
locally-run, AI-powered **video collection manager and search chatbot**. The UI
is Korean-language and follows an **Apple design sensibility** (HIG + apple.com):
restrained surfaces, the Apple system font, Apple system colors, dark/light
theming that defaults to the OS, and a soft, low-contrast shadow language.

> This is a recreation for design + prototyping. It is not the production app.

## Sources

- **Codebase** (primary source of truth): <https://github.com/CrazyJK/flayAI/tree/main/apps/web>
  — the flayAI Next.js 16 / React 19 / Tailwind v4 app (chat, image, face, labels,
  stabilize, subtitle, admin, and diary surfaces). Tokens here are lifted directly
  from `apps/web/src/app/globals.css`.
- **GitHub**: <https://github.com/CrazyJK/flayAI-design> — currently a stub
  (README only). Explore it for future updates to the brand.

Don't assume the reader has access to these; everything needed is captured here.

---

## What the product is

flayAI indexes a local video library and lets you **search it in natural
Korean**. The flagship surface is a chat: you type "온천에서 여러 남자랑 즐기는
영상" and it runs a hybrid (semantic + full-text + usage + recency) search,
streaming back a grid of poster cards with per-result score breakdowns and a
plain-language reason for each pick. Around the chat sit operator tools:

| Surface | Purpose |
|---|---|
| **채팅 (chat)** | Natural-language hybrid search → poster result grid. The hero. |
| **이미지 (image)** | Text→poster and image→poster CLIP similarity search. |
| **얼굴 (face)** / **라벨링 (labels)** | Face clustering and labeling clusters → actresses. |
| **자막 (subtitle)** | Subtitle generation / resync job queue. |
| **안정화 (stabilize)** | Video stabilization. |
| **관리자 (admin)** | Backend dashboard — Qdrant / SQLite / Ollama status + the indexing pipeline. |
| **일기 (diary)** | A private journaling space — warm serif "mood", with memory recall of past entries. |

Tech: a hybrid retrieval stack (Qdrant vectors, SQLite + FTS5, Ollama LLMs:
bge-m3 embeddings, qwen for completion/tools, llava for vision), surfaced over
SSE-streamed chat endpoints.

---

## Content fundamentals

**Language & voice.** The UI is **Korean**, concise and functional. Tool screens
address the user politely and minimally — "무엇을 찾을까요?" (What shall we find?),
"생성 중…" (generating…), "0 items". Buttons are short verbs/nouns: 전송 (send),
중단 (stop), 새로고침 (refresh), 증분 인덱싱 (incremental index).

**The diary breaks voice on purpose.** It drops to warm **반말 (casual banmal)** —
"오늘은 어땠어?" (How was today?), "그냥 떠오르는 대로 적어." (Just write whatever
comes to mind.) This intimacy is a designed contrast to the tools' polite register.

**Casing & numbers.** English technical terms stay lowercase/mono (`instance`,
`archive`, `bge-m3`, `videos_fts`, opus codes like `SSIS-887`). Numbers are
localized (`8,432`) and tabular in mono contexts. Scores show as fixed decimals
(`0.962`) or 2-digit percents (`의미: 96`).

**Emoji & glyphs are used, deliberately and sparingly** as compact data markers,
never decoration: ⭐ rank, 👤 actresses, ▶︎ plays, 💛 likes, ⚙ tool call,
↳ result, ♾ permanent model, ⏱ elapsed; ☀️☁️🌧️❄️ for diary weather. Status uses
✓ / ● / ○ / ✗ / ⏸ marks.

**Vibe.** Calm, dense-but-legible, expert-tool. Information-rich without clutter;
every number earns its place (each result explains *why* it was chosen).

---

## Visual foundations

**Color.** Apple system palette. Light canvas is apple.com's signature
`#f5f5f7` with near-black `#1d1d1f` ink (never pure black); cards are pure white.
Dark mode is true-black `#000` canvas with iOS elevated surfaces (`#1c1c1e`
cards, `#2c2c2e` muted). Primary is Apple blue (`#0071e3` light / `#0a84ff`
dark). Semantics: green `#34c759`/`#30d158`, red `#ff3b30`/`#ff453a`. Accents
are quiet — color is reserved for state (kind badges, scores, status), not
chrome. See `tokens/colors.css`.

**Type.** The **Apple system font stack** (`-apple-system` → SF Pro on Apple
devices, Segoe UI / system-ui elsewhere) — a pure CSS stack, no shipped webfont.
Body carries Apple's signature tight tracking (`-0.01em`) and is antialiased.
**Mono** (SF Mono stack) is heavily used for codes, scores, and counts with
tabular figures. The **diary uses a serif** (`Georgia, "Noto Serif KR"`). We
additionally load Noto Sans/Serif KR for Korean coverage. See `tokens/typography.css`.

**Spacing & layout.** Tailwind 4px base unit. Fixed reading columns from the
product: 900px (header + docked composer), 760px (centered hero), 820px (diary).
Result grids use `auto-fill, minmax(…)` — 440px for poster cards, 300px for DB
tiles. See `tokens/spacing.css`.

**Backgrounds.** Flat solid surfaces — **no gradients as decoration**. The one
gradient use is functional: black **text-protection scrims** over poster images
(top + bottom). Diary tints the canvas warm cream. No textures, no patterns.

**Corner radii.** Small and Apple-restrained: 4px badges, 6px posters/buttons,
8px section cards, 12px DB tiles, 16px composer + message bubbles, full-round for
option pills / suggestion chips / status dots. See `tokens/radius-shadow.css`.

**Cards.** Bordered (`1px var(--border)`) + rounded, mostly **flat** (relying on
border, not shadow). Shadows are soft and low-contrast, reserved for floating
things — the hero composer (`shadow-lg`) and popovers (`shadow-xl`). Message
bubbles tuck one corner (`border-top-*-radius: 6px`).

**Borders & dividers.** 1px hairlines in `--border`; header/section separators
are single bottom borders. Translucent tinted borders (`rgba(…, 0.3–0.5)`) pair
with translucent fills on badges and status cards.

**Transparency & blur.** Translucent tint fills for badges/status
(`rgba(tone, 0.15)` fill + `0.35` border). Diary drag-drop overlay uses a faint
backdrop blur. Otherwise surfaces are opaque.

**Motion.** Subtle and quick. Color/background transitions ~0.15s ease. The one
signature physical cue is the **button press: `transform: scale(0.97)`** (~0.08s).
Loading uses pulsing text ("생성 중…") and a bouncing three-dot typing indicator.
No bounces, parallax, or decorative loops.

**Hover / press states.** Hover = a subtle background tint (`--accent`) or a
muted→foreground text shift; primary buttons darken the fill (`color-mix … 88%`).
Press = the 0.97 scale shrink. Disabled = `opacity: 0.4`, `not-allowed`.

**Focus.** Inputs/composer tint the border Apple-blue and add a soft 2px halo
ring (`--ring`, blue at 0.3–0.4 alpha).

**Imagery.** Real posters (400:269) are the dominant imagery, always under dark
scrims so white text stays legible. No illustration system; iconography is
line-based (below).

**Scrollbars.** Thin (4px), translucent thumb — dark thumb on light, light thumb
on dark (from flayground's scrollbar spec). See `tokens/base.css`.

---

## Iconography

- **Inline line icons, Lucide-style.** Every icon in the app is a hand-inlined
  SVG matching **[Lucide](https://lucide.dev)** exactly: `viewBox="0 0 24 24"`,
  `fill="none"`, `stroke="currentColor"`, `stroke-width="2"`, round caps/joins.
  Seen: sun / moon / monitor (theme), book (diary), image, copy, edit (pencil),
  corner-down-left (send), square (stop), camera. They inherit text color and
  size via width/height.
- **Recommendation for new work:** pull from **Lucide** (CDN
  `https://unpkg.com/lucide-static` or `lucide-react`) at stroke-width 2 to stay
  consistent. The design system's own components inline these directly.
- **Emoji as data markers** (not an icon font): ⭐ 👤 ▶︎ 💛 ⚙ ↳ ♾ ⏱ and weather
  ☀️☁️🌧️❄️. Status marks use Unicode: ✓ ● ○ ✗ ⏸ ▶ ⏸.
- **No raster icon assets, no icon font, no brand logo image** — "flayAI" is set
  as plain text (semibold, system font). There is nothing to copy into `assets/`;
  the Next.js starter SVGs (`file/globe/window`) are unused boilerplate.

---

## Index / manifest

**Root**
- `styles.css` — the entry point consumers link (just `@import`s).
- `tokens/` — `colors.css`, `typography.css`, `fonts.css`, `spacing.css`,
  `radius-shadow.css`, `base.css`.
- `README.md` (this file), `SKILL.md`.

**Components** (`window.FlayAIDesignSystem_105b78.*`)
- `components/core/` — **Button**, **Badge**, **Chip**, **Card**, **Tabs**
- `components/product/` — **VideoCard**, **Composer**, **ToolCallChip**, **ThemeToggle**

**UI kits** (`ui_kits/<product>/index.html`)
- `search-chat/` — the flagship NL search chat (hero → results → docked composer)
- `admin/` — backend dashboard (status panels + indexer pipeline)
- `diary/` — warm serif journaling with memory recall

**Foundation cards** (`guidelines/*.card.html`) — color, type, spacing, radius
specimens shown in the Design System tab.

---

## Font substitution flag

`--font-sans` / `--font-mono` reference **SF Pro / SF Mono**, which are installed
on Apple devices but **cannot be redistributed as webfonts**; on other platforms
they fall back to Segoe UI / system-ui per the stack. This is by design — flayAI
uses system fonts. If you have SF Pro licensed, drop `@font-face` rules into
`tokens/fonts.css`. Korean text is covered by Noto Sans/Serif KR (Google Fonts).
