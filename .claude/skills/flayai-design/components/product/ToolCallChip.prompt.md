The agentic trace line in the chat stream — centered, mono, muted, with a cyan ⚙ tool name and JSON args (truncated past 80 chars, ▼ to expand). Pass `result` instead for the "↳ N items" summary line.

```jsx
<ToolCallChip name="search_videos" args={{ query:"온천", limit:10 }} />
<ToolCallChip result="12 items" />
<ToolCallChip result="search_videos → 0 items" />
```
