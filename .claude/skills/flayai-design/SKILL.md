---
name: flayai-design
description: Use this skill to generate well-branded interfaces and assets for flayAI, either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files.
If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.
If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

## Quick orientation
- **Brand**: flayAI — a Korean-language, locally-run AI video-collection search chatbot, with an Apple (HIG + apple.com) design sensibility. Dark/light, system-default.
- **Tokens**: link `styles.css`; everything is CSS custom properties (see `tokens/`). Reference semantic vars (`--primary`, `--card`, `--muted-foreground`, `--border`, `--font-sans`, `--font-mono`, `--radius-md`, `--shadow-sm`). Dark mode = `.dark` on `<html>`. Diary mode = `.diary-mood` wrapper.
- **Components**: live on `window.FlayAIDesignSystem_105b78` after loading `_ds_bundle.js` — Button, Badge, Chip, Card, Tabs, VideoCard, Composer, ToolCallChip, ThemeToggle. Each has a `.prompt.md` next to it with usage.
- **UI kits**: `ui_kits/{search-chat,admin,diary}/index.html` — full interactive product recreations to copy from.
- **Fonts**: Apple system stack (no webfont to ship) + Noto Sans/Serif KR for Korean. Icons: inline Lucide-style line SVGs (stroke 2); emoji used only as compact data markers.

## Do / don't
- DO keep it calm, dense-but-legible, system-font, flat surfaces with hairline borders, soft shadows only on floating elements, the 0.95 button-press shrink. Primary action = full Action-Blue pill; utility buttons = 8px radius.
- DO use mono + tabular figures for codes/scores/counts; localize Korean numbers.
- DON'T add decorative gradients (only functional poster scrims), textures, heavy shadows, or invent a logo — "flayAI" is plain semibold text.
