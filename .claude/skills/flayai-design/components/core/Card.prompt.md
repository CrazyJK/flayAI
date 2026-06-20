Bordered, rounded section container — the workhorse panel of the admin dashboard and tools. Optional header with title, mono `badge`, `available` UP/DOWN pill, and `collapsible` toggle.

```jsx
<Card title="Qdrant 벡터 DB" badge="5개 컬렉션" available>
  …grid of collection tiles…
</Card>
<Card title="SQLite DB" collapsible defaultCollapsed>…</Card>
```

Omit `title` for a plain bordered container.
