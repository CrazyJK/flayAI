"use client";

import { memo, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import AppHeader from "../_components/AppHeader";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ai.kamoru.jk:8000";
const MAX_IMAGES = 8;
const MAX_IMAGE_BYTES = 10 * 1024 * 1024; // 10MB (config.upload_max_bytes 와 일치)

// 회상된 과거 세션(그때 일기 원문 전체)
type RecallMessage = {
  role: string;
  content: string;
  raw_html?: string | null;
  created_at: string;
};
type RecallSession = {
  session_id: number;
  date: string;
  title?: string | null;
  weather?: string | null;
  score?: number;
  messages: RecallMessage[];
};

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  images?: string[]; // 사용자 첨부 이미지(미리보기 dataURL)
  recall?: RecallSession[];
  status: "streaming" | "done" | "error" | "aborted";
  error?: string;
};

// 레거시 일기 HTML 의 이미지 src(/static/diary-assets/..)를 API 절대경로로 치환
function withImageHost(html: string): string {
  return html.replaceAll('src="/static/diary-assets/', `src="${API_BASE}/static/diary-assets/`);
}

// 메시지 id(`u-<ts>`/`a-<ts>`)에서 작성 시각을 복원해 "오후 9:24" 형태로
function msgTime(id: string): string {
  const ts = Number(id.replace(/^[ua]-/, ""));
  if (!Number.isFinite(ts)) return "";
  return new Date(ts).toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit" });
}

// 오늘 날짜 구분선 라벨 — "2026년 6월 20일 · 오늘"
function todayLabel(): string {
  const d = new Date();
  const date = d.toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric" });
  return `${date} · 오늘`;
}

/* ---------- 라인 아이콘(stroke 1.6, currentColor) ---------- */
function Ico({ size = 16, sw = 1.6, children }: { size?: number; sw?: number; children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={sw}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
    >
      {children}
    </svg>
  );
}
const SunIco = ({ size }: { size?: number }) => (
  <Ico size={size}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M5 5l1.4 1.4M17.6 17.6L19 19M2 12h2M20 12h2M5 19l1.4-1.4M17.6 6.4L19 5" />
  </Ico>
);
const CloudIco = ({ size }: { size?: number }) => (
  <Ico size={size}>
    <path d="M17.5 19a4.5 4.5 0 0 0 0-9 6 6 0 0 0-11.6 1.5A4 4 0 0 0 6.5 19h11Z" />
  </Ico>
);
const RainIco = ({ size }: { size?: number }) => (
  <Ico size={size}>
    <path d="M17.5 16a4.5 4.5 0 0 0 0-9 6 6 0 0 0-11.6 1.5A4 4 0 0 0 6.5 16" />
    <path d="M8 19l-1 2M12 19l-1 2M16 19l-1 2" />
  </Ico>
);
const SnowIco = ({ size }: { size?: number }) => (
  <Ico size={size}>
    <path d="M17.5 16a4.5 4.5 0 0 0 0-9 6 6 0 0 0-11.6 1.5A4 4 0 0 0 6.5 16" />
    <path d="M8 19h.01M12 21h.01M16 19h.01" />
  </Ico>
);
const BookmarkIco = ({ size }: { size?: number }) => (
  <Ico size={size}>
    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
  </Ico>
);
const ImageIco = ({ size }: { size?: number }) => (
  <Ico size={size}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <circle cx="9" cy="9" r="1.8" />
    <path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21" />
  </Ico>
);
const SendIco = ({ size }: { size?: number }) => (
  <Ico size={size}>
    <polyline points="9 10 4 15 9 20" />
    <path d="M20 4v7a4 4 0 0 1-4 4H4" />
  </Ico>
);

// 날씨 → 라인 아이콘(이모지 대체). 미지의 값은 원문 텍스트로 폴백.
const WEATHER_MAP: Record<string, ({ size }: { size?: number }) => ReactNode> = {
  sunny: SunIco,
  cloudy: CloudIco,
  rainy: RainIco,
  snowy: SnowIco,
};
function WeatherIcon({ weather, size = 15 }: { weather?: string | null; size?: number }) {
  if (!weather) return null;
  const C = WEATHER_MAP[weather];
  return C ? <C size={size} /> : <span className="font-sans text-xs">{weather}</span>;
}

// 날짜 구분선 — 양쪽 hairline + 가운데 대문자 라벨
function DateDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-4">
      <div className="flex-1 h-px bg-border" />
      <span className="font-sans text-xs uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </span>
      <div className="flex-1 h-px bg-border" />
    </div>
  );
}

// AI 응답 = 여백의 동행 노트(보조 톤) — 좌측 거터에 작은 강조점 + 세리프 이탤릭
function Companion({ children }: { children: ReactNode }) {
  return (
    <div className="flex gap-3.5 pl-1 pr-0.5 py-0.5">
      <div className="shrink-0 w-[22px] flex justify-center pt-[7px]">
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--diary-accent)] opacity-80" />
      </div>
      <div className="italic text-base leading-[1.7] text-muted-foreground max-w-[560px]">
        {children}
      </div>
    </div>
  );
}

// 타이핑 인디케이터(점 3개 + 경과초) — 동행 노트와 같은 거터/강조색
function TypingDots() {
  const [sec, setSec] = useState(0);
  useEffect(() => {
    const start = performance.now();
    const id = setInterval(() => setSec(Math.floor((performance.now() - start) / 1000)), 200);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="flex gap-3.5 pl-1 pr-0.5 py-0.5 items-center">
      <div className="shrink-0 w-[22px] flex justify-center">
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--diary-accent)] opacity-80" />
      </div>
      <div className="inline-flex items-center gap-2">
        <span className="inline-flex items-center gap-1">
          {[0, 0.15, 0.3].map((d) => (
            <span
              key={d}
              className="h-1.5 w-1.5 rounded-full bg-[var(--diary-accent)] opacity-60 animate-bounce"
              style={{ animationDelay: `${d}s` }}
            />
          ))}
        </span>
        {sec >= 1 && <span className="font-sans text-xs tabular-nums text-muted-foreground">{sec}s</span>}
      </div>
    </div>
  );
}

// 회상 = '그때의 기억' 타임라인 노드 + 종이 카드. memo — 스트리밍 토큰마다 리렌더되어
// 흔들리지 않게(부모 text 변경과 무관, s 참조 고정).
const RecallCard = memo(function RecallCard({ s, last }: { s: RecallSession; last?: boolean }) {
  return (
    <div className="flex gap-4">
      {/* 타임라인 레일 — 속 빈 강조 노드 + 세로 룰 */}
      <div className="shrink-0 w-3.5 flex flex-col items-center">
        <span className="w-[11px] h-[11px] rounded-full bg-background border-2 border-[var(--diary-accent)] mt-[18px]" />
        {!last && <span className="flex-1 w-0.5 bg-border mt-1" />}
      </div>
      {/* 기억 카드 — 종이 + 상단 강조 룰 + 부드러운 그림자 */}
      <div className="relative flex-1 mb-[18px] overflow-hidden rounded-2xl border border-border bg-card px-[18px] pt-4 pb-[18px] shadow-[0_8px_24px_rgba(0,0,0,0.05)]">
        <div className="absolute top-0 inset-x-0 h-[3px] bg-[var(--diary-accent)] opacity-50" />
        <div className="flex items-center gap-2.5 mb-3">
          <span className="font-mono text-[11.5px] text-[var(--diary-accent)] bg-[var(--diary-accent-soft)] px-2.5 py-[3px] rounded-full tracking-[0.02em]">
            {s.date}
          </span>
          {s.weather && (
            <span className="text-[var(--diary-accent)]">
              <WeatherIcon weather={s.weather} size={15} />
            </span>
          )}
          {s.title && <span className="text-[15px] font-semibold text-foreground">{s.title}</span>}
        </div>
        <div className="flex flex-col gap-1">
          {s.messages.map((m, i) =>
            m.raw_html ? (
              <div
                key={i}
                className="diary-html text-[15px] leading-[1.7] text-foreground [&_img]:max-w-full [&_img]:rounded-lg [&_img]:my-2 [&_h3]:font-semibold [&_p]:my-1"
                dangerouslySetInnerHTML={{ __html: withImageHost(m.raw_html) }}
              />
            ) : m.role === "user" ? (
              <p key={i} className="m-0 text-[15px] leading-[1.7] text-foreground whitespace-pre-wrap">
                {m.content}
              </p>
            ) : (
              <p
                key={i}
                className="m-0 pl-3 border-l-2 border-[var(--diary-accent-soft)] text-[13.5px] leading-[1.65] text-muted-foreground italic whitespace-pre-wrap"
              >
                {m.content}
              </p>
            )
          )}
        </div>
      </div>
    </div>
  );
});

function AssistantBlock({ msg }: { msg: Message }) {
  return (
    <div className="space-y-3">
      {/* AI 응답(동행 노트) */}
      {msg.text && <Companion>{msg.text}</Companion>}
      {msg.status === "streaming" && !msg.text && <TypingDots />}
      {/* 회상 타임라인 — 노트 아래에 '그때의 기억'을 펼침 */}
      {msg.recall && msg.recall.length > 0 && (
        <div className="mt-1">
          <div className="font-sans flex items-center gap-1.5 mb-3.5 text-[12.5px] tracking-[0.04em] text-muted-foreground">
            <span className="text-[var(--diary-accent)]">
              <BookmarkIco size={14} />
            </span>
            그때의 기억 · {msg.recall.length}
          </div>
          {msg.recall.map((s, i) => (
            <RecallCard key={s.session_id} s={s} last={i === msg.recall!.length - 1} />
          ))}
        </div>
      )}
      {msg.status === "error" && (
        <div className="font-sans text-xs text-destructive">⚠ {msg.error}</div>
      )}
    </div>
  );
}

export default function DiaryPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<string[]>([]); // 전송 대기 첨부 이미지(dataURL)
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState(false); // 이미지 드래그 오버 표시
  const dragDepth = useRef(0); // 자식 위를 지날 때 dragleave 오작동 방지(깊이 카운트)
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pendingTopRef = useRef<string | null>(null); // 상단 정렬 대기 중인 질문 id
  const pinDeadlineRef = useRef(0); // 이 시각까지만 상단 정렬 시도(회상 도착 대기)
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const readAsDataUrl = (file: File) =>
    new Promise<string>((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => resolve(String(fr.result));
      fr.onerror = () => reject(fr.error);
      fr.readAsDataURL(file);
    });

  const addFiles = useCallback(async (files: FileList | File[] | null) => {
    if (!files) return;
    const imgs = Array.from(files).filter((f) => f.type.startsWith("image/"));
    const urls: string[] = [];
    for (const f of imgs) {
      if (f.size > MAX_IMAGE_BYTES) {
        alert(`${f.name || "이미지"} 은(는) 10MB 를 넘어 건너뜁니다.`);
        continue;
      }
      urls.push(await readAsDataUrl(f));
    }
    if (urls.length) setPending((prev) => [...prev, ...urls].slice(0, MAX_IMAGES));
  }, []);

  // 클립보드에서 이미지(스샷 등) 붙여넣기 → 첨부
  const onPaste = useCallback(
    (e: React.ClipboardEvent) => {
      const files = Array.from(e.clipboardData?.items ?? [])
        .filter((it) => it.kind === "file" && it.type.startsWith("image/"))
        .map((it) => it.getAsFile())
        .filter((f): f is File => !!f);
      if (files.length) {
        e.preventDefault(); // 이미지일 때만 텍스트 입력 대신 첨부
        void addFiles(files);
      }
    },
    [addFiles]
  );

  useEffect(() => {
    // 보낸 질문을 화면 맨 위로 올린다. 회상/답변 내용이 아래에 채워져야 올릴 수 있으므로
    // (회상은 빠르게 도착) 상단에 닿을 때까지 렌더마다 시도하고, 닿으면(또는 시간 초과) 멈춘다.
    const id = pendingTopRef.current;
    const c = scrollRef.current;
    if (!id || !c) return;
    const el = c.querySelector(`[data-mid="${id}"]`) as HTMLElement | null;
    if (!el) return;
    const top = () => el.getBoundingClientRect().top - c.getBoundingClientRect().top;
    if (top() > 8) c.scrollTop += top() - 8; // 내용이 부족하면 자연 클램프(끝까지 못 올라감)
    if (top() <= 9 || performance.now() > pinDeadlineRef.current) pendingTopRef.current = null;
  }, [messages]);

  const updateAssistant = useCallback((id: string, patch: (m: Message) => Message) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? patch(m) : m)));
  }, []);

  const newConversation = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setSessionId(null);
    setPending([]);
  }, []);

  const send = useCallback(
    async (query: string, images: string[] = []) => {
      if ((!query.trim() && images.length === 0) || busy) return;
      const userMsg: Message = {
        id: `u-${Date.now()}`,
        role: "user",
        text: query,
        images: images.length ? images : undefined,
        status: "done",
      };
      pendingTopRef.current = userMsg.id; // 보낸 질문을 화면 상단으로(회상 도착까지 잠깐 재시도)
      pinDeadlineRef.current = performance.now() + 2000;
      const asstId = `a-${Date.now()}`;
      const asstMsg: Message = { id: asstId, role: "assistant", text: "", status: "streaming" };
      setMessages((prev) => [...prev, userMsg, asstMsg]);
      setBusy(true);

      const ac = new AbortController();
      abortRef.current = ac;
      try {
        const r = await fetch(`${API_BASE}/api/diary/chat`, {
          method: "POST",
          headers: { "content-type": "application/json", accept: "text/event-stream" },
          body: JSON.stringify({
            query,
            session_id: sessionId ?? undefined,
            images: images.length ? images : undefined,
          }),
          signal: ac.signal,
        });
        if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`);
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split(/\r?\n\r?\n/);
          buf = parts.pop() ?? "";
          for (const evBlock of parts) {
            const dataLines = evBlock
              .split(/\r?\n/)
              .filter((l) => l.startsWith("data:"))
              .map((l) => l.slice(5).trimStart());
            if (dataLines.length === 0) continue;
            const payload = dataLines.join("\n").trim();
            if (!payload) continue;
            let ev: { type?: string; [k: string]: unknown };
            try {
              ev = JSON.parse(payload);
            } catch {
              continue;
            }
            switch (ev.type) {
              case "session":
                setSessionId(Number(ev.session_id));
                break;
              case "recall":
                updateAssistant(asstId, (m) => ({
                  ...m,
                  recall: ev.sessions as RecallSession[],
                }));
                break;
              case "token":
                updateAssistant(asstId, (m) => ({ ...m, text: m.text + String(ev.text ?? "") }));
                break;
              case "done":
                // 정리된 최종본으로 교체(스트리밍 중 섞인 노이즈를 done 에서 정정)
                updateAssistant(asstId, (m) => ({
                  ...m,
                  text: String(ev.message ?? m.text),
                  status: "done",
                }));
                break;
              case "error":
                updateAssistant(asstId, (m) => ({
                  ...m,
                  status: "error",
                  error: String(ev.message ?? "unknown error"),
                }));
                break;
            }
          }
        }
        updateAssistant(asstId, (m) => (m.status === "streaming" ? { ...m, status: "done" } : m));
      } catch (e) {
        const aborted = ac.signal.aborted;
        updateAssistant(asstId, (m) => ({
          ...m,
          status: aborted ? "aborted" : "error",
          error: aborted ? undefined : (e as Error).message,
        }));
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    [busy, sessionId, updateAssistant]
  );

  const abort = useCallback(() => abortRef.current?.abort(), []);
  const empty = messages.length === 0;

  // 화면 위로 이미지(파일) 드래그 → 첨부로 인식
  const hasFiles = (e: React.DragEvent) =>
    Array.from(e.dataTransfer?.types ?? []).includes("Files");

  // 컴포저(글 쓰는 면) — hero(빈 화면·중앙) / docked(작성 후·하단) 두 변형으로 크기만 분기.
  // 종이 면: rounded-[18px] + 상단 얇은 강조 룰 + 세리프 입력 + 강조색 포커스 링.
  const composer = (hero: boolean) => (
    <form
      className={hero ? "w-full max-w-[600px] mx-auto" : "shrink-0 w-full max-w-[720px] mx-auto px-4 py-3"}
      onSubmit={(e) => {
        e.preventDefault();
        const q = input;
        const imgs = pending;
        setInput("");
        setPending([]);
        if (taRef.current) taRef.current.style.height = "auto";
        void send(q, imgs);
      }}
    >
      <div
        className={
          "rounded-[18px] border border-border bg-card shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-[border-color,box-shadow] duration-200 focus-within:border-[var(--diary-accent)] focus-within:ring-4 focus-within:ring-[var(--diary-accent-soft)] " +
          (hero ? "px-5 pt-5 pb-3.5" : "px-[18px] pt-4 pb-3")
        }
      >
        {/* 첨부 이미지 미리보기 — 박스 안, 강조 룰 위에 배치 */}
        {pending.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {pending.map((src, i) => (
              <div key={i} className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={src}
                  alt="첨부 미리보기"
                  className="h-16 w-16 object-cover rounded-md border border-border"
                />
                <button
                  type="button"
                  onClick={() => setPending((prev) => prev.filter((_, j) => j !== i))}
                  aria-label="첨부 제거"
                  className="absolute -top-1.5 -right-1.5 h-5 w-5 rounded-full bg-black/70 text-white text-xs leading-none flex items-center justify-center hover:bg-black"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        {/* 상단 얇은 강조 룰 */}
        <div
          className={"h-px bg-[var(--diary-accent)] opacity-[0.28] " + (hero ? "mb-4" : "mb-3")}
        />
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => {
            void addFiles(e.target.files);
            e.target.value = ""; // 같은 파일 재선택 허용
          }}
        />
        <textarea
          ref={taRef}
          rows={hero ? 3 : 2}
          className={
            "w-full bg-transparent outline-none resize-none leading-relaxed text-foreground placeholder:text-muted-foreground " +
            (hero ? "text-lg" : "text-base")
          }
          style={{ maxHeight: 200 }}
          placeholder="오늘 있었던 일, 떠오른 생각…"
          value={input}
          disabled={busy}
          autoFocus
          onPaste={onPaste}
          onChange={(e) => setInput(e.target.value)}
          onInput={(e) => {
            const ta = e.currentTarget;
            ta.style.height = "auto";
            ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <div className="flex items-center mt-2">
          {/* 사진 첨부 */}
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy || pending.length >= MAX_IMAGES}
            title="사진 첨부"
            aria-label="사진 첨부"
            className="p-1 text-muted-foreground hover:text-[var(--diary-accent)] disabled:opacity-30"
          >
            <ImageIco size={19} />
          </button>
          <span className="flex-1" />
          {busy ? (
            <button
              type="button"
              onClick={abort}
              title="중단"
              aria-label="중단"
              className="p-1 text-destructive hover:opacity-80"
            >
              <svg width={18} height={18} viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            </button>
          ) : (
            <button
              type="submit"
              title="기록"
              aria-label="기록"
              disabled={!input.trim() && pending.length === 0}
              className="p-1 text-[var(--diary-accent)] hover:opacity-80 disabled:opacity-30"
            >
              <SendIco size={19} />
            </button>
          )}
        </div>
      </div>
    </form>
  );

  return (
    <main
      className="relative flex-1 flex flex-col w-full min-h-0"
      onDragEnter={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        dragDepth.current += 1;
        setDragOver(true);
      }}
      onDragOver={(e) => {
        if (hasFiles(e)) e.preventDefault(); // drop 허용
      }}
      onDragLeave={(e) => {
        if (!hasFiles(e)) return;
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) setDragOver(false);
      }}
      onDrop={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        dragDepth.current = 0;
        setDragOver(false);
        void addFiles(e.dataTransfer.files);
      }}
    >
      {dragOver && (
        <div className="absolute inset-0 z-50 m-2 flex items-center justify-center rounded-2xl border-2 border-dashed border-[var(--diary-accent)] bg-[var(--diary-accent-soft)] backdrop-blur-[1px] pointer-events-none">
          <div className="rounded-xl bg-card px-5 py-3 text-sm font-semibold text-[var(--diary-accent)] shadow-lg">
            여기에 놓으면 사진 첨부
          </div>
        </div>
      )}
      <AppHeader
        active="diary"
        actions={
          !empty ? (
            <button
              type="button"
              onClick={newConversation}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              + 새 대화
            </button>
          ) : undefined
        }
      />

      {empty ? (
        // 빈 상태 = 글쓰기 초대. 중앙에 hero 컴포저를 노출(현행은 비어 있던 가운데).
        <div className="flex-1 min-h-0 flex flex-col items-center justify-center gap-7 px-6 pb-16">
          <div className="text-center">
            <div className="text-[32px] font-semibold text-foreground tracking-[0.01em]">
              오늘은 어땠어?
            </div>
            <div className="text-base italic text-muted-foreground mt-2.5">
              그냥 떠오르는 대로 적어. 예전 일이 궁금하면 물어봐도 돼.
            </div>
          </div>
          {composer(true)}
        </div>
      ) : (
        <>
          <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto w-full">
            <div className="max-w-[720px] mx-auto px-6 pt-6 pb-2 flex flex-col gap-[18px]">
              <DateDivider label={todayLabel()} />
              {messages.map((m) =>
                m.role === "user" ? (
                  // 사용자 글 = 페이지의 주인공(민무늬 — 캔버스 위 세리프 본문)
                  <article key={m.id} data-mid={m.id} className="px-0.5 pt-1 pb-2">
                    {msgTime(m.id) && (
                      <div className="font-sans flex items-center gap-2 mb-3 text-[12.5px] tracking-[0.02em] text-muted-foreground">
                        <span>{msgTime(m.id)}</span>
                      </div>
                    )}
                    {m.text && (
                      <div
                        className="whitespace-pre-wrap text-[20px] leading-[1.75] text-foreground"
                        style={{ letterSpacing: "0.005em" }}
                      >
                        {m.text}
                      </div>
                    )}
                    {m.images && m.images.length > 0 && (
                      <div className="flex flex-wrap gap-3 mt-4">
                        {m.images.map((src, i) => (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            key={i}
                            src={src}
                            alt="첨부 이미지"
                            className="w-[180px] max-h-[240px] object-cover rounded-[10px] border border-border"
                          />
                        ))}
                      </div>
                    )}
                  </article>
                ) : (
                  <div key={m.id}>
                    <AssistantBlock msg={m} />
                  </div>
                )
              )}
            </div>
          </div>
          {composer(false)}
        </>
      )}
    </main>
  );
}
