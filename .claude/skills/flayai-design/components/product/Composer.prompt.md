The chat input box (Copilot/Claude-style): rounded card, auto-growing textarea, an options row beneath (left: your option chips; right: send/stop). Enter submits, Shift+Enter newlines, IME-safe. Focus tints the border blue.

```jsx
<Composer hero value={input} onChange={setInput} busy={busy}
  onSubmit={send} onStop={abort}
  options={<><Chip role="option">10</Chip><Chip role="option">All</Chip></>} />
```

Use `hero` for the centered empty-state; omit for the compact docked bar (max-width 900px, auto-centered).
