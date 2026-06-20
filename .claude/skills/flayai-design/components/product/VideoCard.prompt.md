The signature flayAI search result — a 400:269 poster with top/bottom protection scrims, amber opus code, kind badge, optional rank stars + score, and a meta row (studio · year · 👤 actresses · ▶︎ plays · 💛 likes).

```jsx
<VideoCard
  hit={{ opus:"ABC-123", title:"제목", studio:"스튜디오", year:2026, month:1,
         kind:"instance", rank:3, score:0.962, play:42, like_count:7,
         actresses:["배우 A"] }}
  poster="https://…/posters/ABC-123"
  onOpen={(opus) => openPopup(opus)}
/>
```

Lay them out in a `repeat(auto-fill, minmax(440px,1fr))` grid. Missing poster falls back to a muted block.
