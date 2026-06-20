// flayAI — Diary UI kit.
// The private journaling space: warm cream + serif (.diary-mood), past-entry
// "recall" cards, and a reflective assistant. Composes Composer + ThemeToggle.

const DS = window.FlayAIDesignSystem_105b78;
const { Composer, ThemeToggle, Badge } = DS;

const WEATHER = { sunny: "☀️", cloudy: "☁️", rainy: "🌧️", snowy: "❄️" };

const RECALL = [
  { date: "2025-06-20", weather: "sunny", title: "처음 카메라를 산 날", body: "큰맘 먹고 카메라를 샀다. 손에 쥐니 묵직하고 좋았다. 동네를 한 바퀴 돌며 아무거나 찍었는데, 평범한 골목도 뷰파인더 안에선 달라 보였다." },
  { date: "2025-12-31", weather: "snowy", title: "한 해의 끝", body: "눈이 내렸다. 올해는 유난히 빨리 지나갔다. 사진 폴더를 정리하다 보니 봄에 찍은 벚꽃이 벌써 아득하다." },
];

const SEED = [
  { role: "user", text: "오늘 오랜만에 카메라를 다시 꺼냈어. 작년 이맘때가 자꾸 생각나더라." },
  { role: "assistant", recall: RECALL, text: "작년 6월에 처음 카메라를 샀던 그 설렘이 떠올랐나 봐. 평범한 골목도 뷰파인더 안에선 달라 보인다고 적었었지. 오늘 다시 꺼낸 카메라로는 무엇을 담고 싶어?" },
];

function RecallCard({ s }) {
  return (
    <div style={{ borderRadius: "var(--radius-2xl)", border: "1px solid color-mix(in srgb, var(--apple-amber) 25%, transparent)", background: "color-mix(in srgb, var(--apple-amber) 6%, transparent)", padding: "14px 16px", boxShadow: "var(--shadow-sm)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={{ borderRadius: 9999, background: "color-mix(in srgb, var(--apple-amber) 15%, transparent)", padding: "2px 8px", fontSize: "var(--text-xs)", fontFamily: "var(--font-mono)", color: "var(--apple-amber)" }}>{s.date}</span>
        {s.weather && <span style={{ fontSize: "var(--text-sm)" }}>{WEATHER[s.weather]}</span>}
        {s.title && <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--foreground)" }}>{s.title}</span>}
      </div>
      <p style={{ margin: 0, fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", color: "color-mix(in srgb, var(--foreground) 90%, transparent)" }}>{s.body}</p>
    </div>
  );
}

function DiaryScreen() {
  const [messages, setMessages] = React.useState(SEED);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [isDark, setIsDark] = React.useState(() => document.documentElement.classList.contains("dark"));
  const scrollRef = React.useRef(null);

  React.useEffect(() => {
    const el = document.documentElement;
    const sync = () => setIsDark(el.classList.contains("dark"));
    sync();
    const obs = new MutationObserver(sync);
    obs.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  const send = (q) => {
    const text = (q ?? input).trim();
    if (!text) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }, { role: "assistant", streaming: true }]);
    setBusy(true);
    setTimeout(() => {
      setMessages((m) => m.map((msg, i) => i === m.length - 1 ? { role: "assistant", text: "그렇게 적어두니 좋다. 오늘의 마음이 나중에 또 너에게 말을 걸어줄 거야." } : msg));
      setBusy(false);
    }, 1100);
  };

  React.useEffect(() => { scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight); }, [messages]);

  return (
    <main className={"diary-mood" + (isDark ? " diary-mood-dark" : "")} style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, background: "var(--background)", color: "var(--foreground)" }}>
      <header style={{ flexShrink: 0, margin: "0 auto", width: "100%", maxWidth: "var(--col-diary)", padding: "16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "baseline", gap: 10, fontFamily: "var(--font-sans)" }}>
        <h1 style={{ fontSize: "var(--text-lg)", fontWeight: 600, margin: 0 }}>flayAI</h1>
        <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "var(--text-xs)", color: "var(--apple-amber)" }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" /></svg>
          일기
        </span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          <button style={{ background: "none", border: "none", cursor: "pointer", fontSize: "var(--text-xs)", color: "var(--muted-foreground)", fontFamily: "var(--font-sans)" }}>+ 새 대화</button>
          <ThemeToggle />
        </div>
      </header>

      <div ref={scrollRef} style={{ flex: 1, minHeight: 0, overflowY: "auto", width: "100%", maxWidth: "var(--col-diary)", margin: "0 auto", padding: "16px", display: "flex", flexDirection: "column", gap: 20 }}>
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} style={{ display: "flex", justifyContent: "flex-end" }}>
              <div style={{ borderRadius: "var(--radius-2xl)", borderTopRightRadius: "var(--radius-md)", background: "var(--primary)", color: "#fff", padding: "10px 14px", fontSize: "15px", maxWidth: "82%", boxShadow: "var(--shadow-sm)", lineHeight: "var(--leading-relaxed)" }}>{m.text}</div>
            </div>
          ) : (
            <div key={i} style={{ display: "flex", justifyContent: "flex-start" }}>
              <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 10 }}>
                {m.recall && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "var(--text-xs)", color: "var(--muted-foreground)", fontFamily: "var(--font-sans)" }}>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>
                      그때 일기 {m.recall.length}건
                    </div>
                    {m.recall.map((s) => <RecallCard key={s.date} s={s} />)}
                  </div>
                )}
                {m.streaming ? (
                  <div style={{ display: "inline-flex", alignItems: "center", gap: 4, alignSelf: "flex-start", borderRadius: "var(--radius-2xl)", borderTopLeftRadius: "var(--radius-md)", background: "color-mix(in srgb, var(--muted) 60%, transparent)", padding: "12px 16px" }}>
                    {[0, 0.15, 0.3].map((d) => <span key={d} style={{ width: 6, height: 6, borderRadius: 9999, background: "var(--muted-foreground)", animation: `db 1s ${d}s infinite` }}></span>)}
                  </div>
                ) : m.text && (
                  <div style={{ display: "inline-block", maxWidth: "88%", alignSelf: "flex-start", borderRadius: "var(--radius-2xl)", borderTopLeftRadius: "var(--radius-md)", background: "color-mix(in srgb, var(--muted) 60%, transparent)", padding: "10px 16px", fontSize: "15px", lineHeight: "var(--leading-relaxed)", color: "var(--foreground)" }}>{m.text}</div>
                )}
              </div>
            </div>
          )
        )}
      </div>

      <div style={{ flexShrink: 0, width: "100%", maxWidth: "var(--col-diary)", margin: "0 auto", padding: "12px 16px" }}>
        <Composer value={input} onChange={setInput} onSubmit={send} busy={busy} placeholder="오늘 있었던 일, 떠오른 생각…" />
      </div>
    </main>
  );
}

window.DiaryScreen = DiaryScreen;
