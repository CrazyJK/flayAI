// flayAI — Search Chat UI kit screens.
// Composes design-system components (window.FlayAIDesignSystem_105b78) into the
// real chat product: centered hero empty-state → results stream with tool chips
// and VideoCard grid → docked composer. Posters are tasteful gradient stand-ins.

const DS = window.FlayAIDesignSystem_105b78;
const { Button, Badge, Chip, Tabs, VideoCard, Composer, ToolCallChip, ThemeToggle } = DS;

const SUGGESTIONS = [
  "사무실에서 즐겁게 일하는 영상 보여줘",
  "2026년 1월에 찍은 영상 보여줘",
  "2026년 나온 영상에서 인기가 높은 영상",
  "온천에서 여러 남자랑 즐기는 영상",
];

const POSTER_GRADS = [
  "linear-gradient(135deg,#3a4a63,#1c2533)",
  "linear-gradient(135deg,#6b4a52,#2b1d22)",
  "linear-gradient(135deg,#46603f,#1f2b1c)",
  "linear-gradient(135deg,#5a4b6b,#241d2b)",
  "linear-gradient(135deg,#63563a,#2b251c)",
  "linear-gradient(135deg,#3a5a63,#1c2a2d)",
];

const RESULTS = [
  { opus: "SSIS-887", title: "사무실의 즐거운 하루", studio: "S1 NO.1 STYLE", year: 2026, month: 1, kind: "instance", rank: 3, score: 0.962, play: 124, like_count: 18, actresses: ["미카미 유아"] },
  { opus: "ABW-321", title: "야근 후의 비밀", studio: "Prestige", year: 2026, month: 1, kind: "instance", rank: 2, score: 0.918, play: 88, like_count: 11, actresses: ["카와키타 사이카"] },
  { opus: "PRED-540", title: "온천 여행의 추억", studio: "Premium", year: 2025, month: 11, kind: "archive", score: 0.881, play: 203, like_count: 27, actresses: ["아마미야 코토네", "유메노 아이카"] },
  { opus: "MIDV-112", title: "출근길의 설렘", studio: "MOODYZ", year: 2026, month: 2, kind: "instance", rank: 1, score: 0.844, play: 41, like_count: 6, actresses: ["히메노 코토하"] },
  { opus: "STARS-998", title: "회의실의 긴장", studio: "SOD Create", year: 2025, month: 12, kind: "archive", score: 0.802, play: 67, like_count: 9, actresses: ["토다 마코토"] },
  { opus: "FSDSS-743", title: "퇴근 후 한 잔", studio: "FALENO", year: 2026, month: 1, kind: "instance", score: 0.771, play: 35, like_count: 4, actresses: ["미야지마 메이"] },
];

function Header({ go, active }) {
  const NAV = [
    { key: "chat", label: "채팅" }, { key: "image", label: "이미지" },
    { key: "face", label: "얼굴" }, { key: "labels", label: "라벨링" },
    { key: "subtitle", label: "자막" }, { key: "admin", label: "관리자" },
  ];
  return (
    <header style={{ flexShrink: 0, margin: "0 auto", width: "100%", maxWidth: "var(--col-header)", padding: "16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "baseline", gap: 8 }}>
      <h1 style={{ fontSize: "var(--text-lg)", fontWeight: 600, margin: 0, color: "var(--foreground)" }}>flayAI</h1>
      <nav style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14 }}>
        <Tabs variant="text" value={active} onChange={go} items={NAV} />
        <span style={{ height: 12, width: 1, background: "var(--border)" }}></span>
        <a style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "var(--text-xs)", color: "var(--apple-amber)", textDecoration: "none", cursor: "pointer" }} onClick={() => go("diary")}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" /></svg>
          일기
        </a>
        <ThemeToggle />
      </nav>
    </header>
  );
}

function OptionsRow({ limit, setLimit, kind, setKind }) {
  return (
    <>
      <Chip role="option" selected={false}>{limit}</Chip>
      <Chip role="option" selected={kind !== "전체"}>{kind}</Chip>
    </>
  );
}

function ChatScreen() {
  const [messages, setMessages] = React.useState([]);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const scrollRef = React.useRef(null);

  const send = (q) => {
    const query = (q ?? input).trim();
    if (!query) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: query }, { role: "assistant", streaming: true, query }]);
    setBusy(true);
    setTimeout(() => {
      setMessages((m) => m.map((msg, i) => i === m.length - 1 ? { ...msg, streaming: false, hits: RESULTS, text: `'${query}' 와 관련된 영상 ${RESULTS.length}편을 찾았어요.` } : msg));
      setBusy(false);
    }, 900);
  };

  React.useEffect(() => { scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight); }, [messages]);

  const empty = messages.length === 0;
  const options = <OptionsRow limit={10} kind={"전체"} />;

  return (
    <main style={{ flex: 1, display: "flex", flexDirection: "column", width: "100%", minHeight: 0 }}>
      <Header go={() => {}} active="chat" />
      {empty ? (
        <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 28, padding: "16px 16px 64px" }}>
          <h2 style={{ fontSize: "var(--text-3xl)", fontWeight: 600, color: "var(--foreground)", margin: 0 }}>무엇을 찾을까요?</h2>
          <Composer hero value={input} onChange={setInput} onSubmit={send} busy={busy} options={options} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", maxWidth: "var(--col-hero)" }}>
            {SUGGESTIONS.map((q) => <Chip key={q} onClick={() => send(q)}>{q}</Chip>)}
          </div>
        </div>
      ) : (
        <>
          <div ref={scrollRef} style={{ flex: 1, minHeight: 0, overflowY: "auto", width: "100%", padding: "16px 24px", display: "flex", flexDirection: "column", gap: 24 }}>
            {messages.map((m, i) =>
              m.role === "user" ? (
                <div key={i} style={{ display: "flex", justifyContent: "flex-end" }}>
                  <div style={{ maxWidth: "80%", borderRadius: "var(--radius-lg)", background: "color-mix(in srgb, var(--primary) 15%, transparent)", border: "1px solid color-mix(in srgb, var(--primary) 40%, transparent)", padding: "8px 12px", fontSize: "var(--text-sm)", color: "var(--foreground)" }}>{m.text}</div>
                </div>
              ) : (
                <div key={i} style={{ display: "flex", justifyContent: "flex-start" }}>
                  <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 8 }}>
                    <ToolCallChip name="search_videos" args={{ query: m.query, limit: 10 }} />
                    {m.streaming ? (
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--muted-foreground)", textAlign: "center" }}>생성 중…</div>
                    ) : (
                      <>
                        <ToolCallChip result={`${m.hits.length} items`} />
                        <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fill,minmax(440px,1fr))" }}>
                          {m.hits.map((h, j) => <VideoCard key={h.opus} hit={h} style={{ background: POSTER_GRADS[j % POSTER_GRADS.length] }} onOpen={() => {}} />)}
                        </div>
                        <div style={{ whiteSpace: "pre-wrap", color: "var(--foreground)", lineHeight: "var(--leading-relaxed)", textAlign: "center" }}>{m.text}</div>
                      </>
                    )}
                  </div>
                </div>
              )
            )}
          </div>
          <div style={{ flexShrink: 0, padding: "12px 16px" }}>
            <Composer value={input} onChange={setInput} onSubmit={send} busy={busy} options={options} />
          </div>
        </>
      )}
    </main>
  );
}

window.ChatScreen = ChatScreen;
