Apple-style action button — `primary` is a full Action-Blue **pill** (the signature CTA); press state shrinks (scale 0.95), hover darkens the fill.

```jsx
<Button variant="primary" size="md" onClick={send}>전송</Button>
<Button variant="secondary" icon={<SearchIcon/>}>검색</Button>
<Button variant="ghost" size="sm">취소</Button>
<Button variant="danger">삭제</Button>
```

Variants: `primary` (Action-Blue pill), `secondary` (muted fill + 8px hairline utility), `ghost` (text only), `danger` (red outline). Sizes: `sm` | `md` | `lg` (pad 8×15 / 11×22 / 14×28). Pass `icon` for a leading glyph. Pill radius is reserved for `primary`.
