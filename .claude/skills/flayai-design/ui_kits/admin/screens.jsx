// flayAI — Admin dashboard UI kit.
// Service status (Qdrant / SQLite / Ollama) + indexer KPIs + pipeline flow.
// Composes Card, Badge, Tabs, ThemeToggle from the design system.

const DS = window.FlayAIDesignSystem_105b78;
const { Card, Badge, Tabs, ThemeToggle, Button } = DS;

const fmt = (n) => n.toLocaleString("ko-KR");

const QDRANT = [
  { name: "videos", desc: "영상 텍스트 임베딩 (bge-m3)", points: 8432, dim: 1024, status: "green" },
  { name: "posters_clip", desc: "포스터 이미지 임베딩 (CLIP ViT-L/14)", points: 8120, dim: 768, status: "green" },
  { name: "faces", desc: "얼굴 벡터 (InsightFace buffalo_l)", points: 19284, dim: 512, status: "green" },
  { name: "poster_ocr", desc: "포스터 OCR 텍스트 임베딩 (bge-m3)", points: 7651, dim: 1024, status: "yellow" },
];

const OLLAMA = [
  { name: "bge-m3:latest", param: "567M", quant: "F16", size: "1.2 GB", caps: ["embedding"], loaded: true, permanent: true },
  { name: "qwen2.5:7b", param: "7.6B", quant: "Q4_K_M", size: "4.7 GB", caps: ["completion", "tools"], loaded: true, permanent: false },
  { name: "llava:13b", param: "13B", quant: "Q4_0", size: "8.0 GB", caps: ["vision"], loaded: false },
];

const KPIS = [
  { label: "영상", value: 8432, sub: "번역 98% · 임베딩 100%" },
  { label: "포스터", value: 8120, sub: "CLIP 100% · OCR 94% · 얼굴 91%" },
  { label: "배우", value: 1247, sub: "6.8편/명" },
  { label: "얼굴 클러스터", value: 2103, sub: "라벨 1,842 · 88%" },
  { label: "클러스터 라벨", value: 1842, sub: "미라벨 261" },
];

const PIPELINE = [
  { label: "JSON 로드", group: "메타", status: "done" },
  { label: "포스터 스캔", group: "메타", status: "done" },
  { label: "번역", group: "AI", status: "done", pct: 98 },
  { label: "포스터 캡션", group: "AI", status: "running", pct: 62 },
  { label: "텍스트 임베딩", group: "AI", status: "idle", pct: 0 },
  { label: "이미지 임베딩", group: "AI", status: "idle", pct: 0 },
  { label: "얼굴 추출", group: "AI", status: "idle", pct: 0 },
  { label: "포스터 OCR", group: "AI", status: "idle", pct: 0 },
  { label: "페이로드 동기화", group: "메타", status: "idle" },
];

function ProgressBar({ pct }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
      <div style={{ flex: 1, height: 6, background: "var(--muted)", borderRadius: 9999, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: "var(--success)", borderRadius: 9999 }}></div>
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", color: "var(--muted-foreground)", width: 30, textAlign: "right" }}>{pct}%</span>
    </div>
  );
}

const STATUS_MARK = { done: ["✓", "var(--success)"], running: ["●", "#d97706"], idle: ["○", "var(--muted-foreground)"], failed: ["✗", "var(--destructive)"] };

function AdminScreen() {
  return (
    <main style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <header style={{ flexShrink: 0, margin: "0 auto", width: "100%", maxWidth: 1100, padding: "16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "baseline", gap: 12 }}>
        <h1 style={{ fontSize: "var(--text-lg)", fontWeight: 600, margin: 0, color: "var(--foreground)" }}>flayAI</h1>
        <span style={{ fontSize: "var(--text-sm)", color: "var(--muted-foreground)" }}>관리자</span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          <Button variant="secondary" size="sm">↻ 새로고침</Button>
          <ThemeToggle />
        </div>
      </header>

      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", width: "100%", maxWidth: 1100, margin: "0 auto", padding: "20px 16px", display: "flex", flexDirection: "column", gap: 16 }}>

        <Card title="인덱서" available>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 12, marginBottom: 20 }}>
            {KPIS.map((k) => (
              <div key={k.label} style={{ background: "var(--card)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)", padding: "10px 12px" }}>
                <div style={{ color: "var(--muted-foreground)", fontSize: "var(--text-xs)" }}>{k.label}</div>
                <div style={{ color: "var(--foreground)", fontFamily: "var(--font-mono)", fontSize: "var(--text-xl)", fontWeight: 600, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{fmt(k.value)}</div>
                <div style={{ fontSize: 11, color: "var(--muted-foreground)", marginTop: 4 }}>{k.sub}</div>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <Button variant="secondary" size="sm">증분 인덱싱 · 신규 124건</Button>
            <Button variant="danger" size="sm">⚠ 전체 재인덱싱</Button>
          </div>
          <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fill,minmax(300px,1fr))" }}>
            {PIPELINE.map((s) => {
              const [mark, color] = STATUS_MARK[s.status];
              const border = s.status === "running" ? "color-mix(in srgb, #d97706 50%, var(--border))" : s.status === "done" ? "color-mix(in srgb, var(--success) 35%, var(--border))" : "var(--border)";
              return (
                <div key={s.label} style={{ borderRadius: "var(--radius-lg)", border: `1px solid ${border}`, background: "color-mix(in srgb, var(--card) 60%, transparent)", padding: "10px 12px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 16, textAlign: "center", color }}>{mark}</span>
                    <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--foreground)" }}>{s.label}</span>
                    <Badge tone={s.group === "AI" ? "running" : "neutral"} style={{ marginLeft: "auto", fontSize: 10 }}>{s.group}</Badge>
                  </div>
                  {s.pct !== undefined && s.status !== "idle" && <ProgressBar pct={s.pct} />}
                </div>
              );
            })}
          </div>
        </Card>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <Card title="Qdrant 벡터 DB" badge="4개 컬렉션" available>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {QDRANT.map((c) => (
                <div key={c.name} style={{ borderRadius: "var(--radius-md)", border: "1px solid color-mix(in srgb, var(--border) 60%, transparent)", background: "color-mix(in srgb, var(--card) 50%, transparent)", padding: "8px 12px", display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--foreground)" }}>{c.name}</div>
                    <div style={{ fontSize: 11, color: "var(--muted-foreground)", marginTop: 2 }}>{c.desc}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--foreground)" }}>{fmt(c.points)}</div>
                    <div style={{ fontSize: 11, color: "var(--muted-foreground)" }}>포인트</div>
                  </div>
                  <Badge tone={c.status === "green" ? "success" : "warning"}>{c.status}</Badge>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Ollama LLM" badge="3개 설치 · 2개 VRAM 로드" available>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {OLLAMA.map((m) => (
                <div key={m.name} style={{ borderRadius: "var(--radius-md)", border: `1px solid ${m.loaded ? "color-mix(in srgb, var(--success) 40%, var(--border))" : "var(--border)"}`, background: m.loaded ? "color-mix(in srgb, var(--success) 5%, transparent)" : "color-mix(in srgb, var(--card) 50%, transparent)", padding: "8px 12px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 9999, flexShrink: 0, background: m.loaded ? "var(--success)" : "var(--muted)" }}></span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--foreground)" }}>{m.name}</span>
                    {m.permanent && <Badge tone="warning" style={{ marginLeft: "auto", fontSize: 10 }}>♾ 영구</Badge>}
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "2px 12px", fontSize: 11, color: "var(--muted-foreground)", marginTop: 4 }}>
                    <span>파라미터 {m.param}</span><span>양자화 {m.quant}</span><span>크기 {m.size}</span>
                  </div>
                  <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
                    {m.caps.map((c) => <Badge key={c} tone="neutral" style={{ fontSize: 10 }}>{c}</Badge>)}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

      </div>
    </main>
  );
}

window.AdminScreen = AdminScreen;
