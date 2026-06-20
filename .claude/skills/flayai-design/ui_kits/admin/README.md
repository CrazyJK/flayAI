# flayAI — Admin dashboard UI kit

The operator's view of the indexing backend. A single scrolling column of
`Card` panels:

- **인덱서** — five KPI tiles (videos / posters / actresses / face clusters /
  labels), incremental + full re-index buttons, and the AI pipeline as a
  `repeat(auto-fill, minmax(300px,1fr))` grid of stage cards with ✓ / ● / ○
  status marks and green progress bars. The running stage (포스터 캡션) shows
  an amber border + live %.
- **Qdrant 벡터 DB** — collection rows with point counts and green/yellow
  status `Badge`s.
- **Ollama LLM** — installed models, VRAM-loaded highlight, capability badges,
  ♾ permanent-resident marker.

## Components used
`Card` (every panel), `Badge` (status / kind / capabilities), `Button`
(refresh, index actions), `ThemeToggle`.

## Notes
All figures are representative sample data, mirroring the shapes the real
`/api/admin/dashboard` endpoint returns.
