Horizontal selector. `variant="segment"` is the filled mode switch (텍스트→포스터 / 이미지→포스터); `variant="text"` is the muted header navigation.

```jsx
<Tabs variant="segment" value={tab} onChange={setTab}
  items={[{key:"text",label:"텍스트 → 포스터"},{key:"image",label:"이미지 → 포스터"}]} />

<Tabs variant="text" value="chat" onChange={go}
  items={[{key:"chat",label:"채팅"},{key:"image",label:"이미지"},{key:"face",label:"얼굴"}]} />
```
