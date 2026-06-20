Small tinted status/label pill — for video kind (instance/archive), job status (queued/running/done/failed), or service UP/DOWN. Translucent fill + matching border + mono text.

```jsx
<Badge tone="instance">INSTANCE</Badge>
<Badge tone="archive">ARCHIVE</Badge>
<Badge tone="success">UP</Badge>
<Badge tone="running">running</Badge>
<Badge tone="failed">DOWN</Badge>
```

Tones: `instance` `archive` `success` `running` `info` `failed` `warning` `neutral`. Set `mono={false}` for prose labels.
