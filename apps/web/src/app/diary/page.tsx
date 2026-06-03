"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
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

const WEATHER_ICON: Record<string, string> = {
  sunny: "☀️",
  cloudy: "☁️",
  rainy: "🌧️",
  snowy: "❄️",
};

// 레거시 일기 HTML 의 이미지 src(/static/diary-assets/..)를 API 절대경로로 치환
function withImageHost(html: string): string {
  return html.replaceAll('src="/static/diary-assets/', `src="${API_BASE}/static/diary-assets/`);
}

// 회상 카드: 그때 일기 한 건(날짜·제목·날씨 + 원문). memo — 스트리밍 토큰마다 리렌더되어
// 흔들리지 않게(부모 text 변경과 무관, s 참조 고정).
const RecallCard = memo(function RecallCard({ s }: { s: RecallSession }) {
  return (
    <div className="rounded-2xl border border-amber-500/25 bg-amber-500/[0.06] dark:bg-amber-400/[0.05] px-4 py-3.5 shadow-sm">
      <div className="flex items-center gap-2 mb-2.5">
        <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-mono text-amber-700 dark:text-amber-300">
          {s.date}
        </span>
        {s.weather && (
          <span className="text-sm" title={s.weather}>
            {WEATHER_ICON[s.weather] ?? s.weather}
          </span>
        )}
        {s.title && (
          <span className="text-sm font-semibold text-foreground truncate">{s.title}</span>
        )}
      </div>
      <div className="space-y-1.5">
        {s.messages.map((m, i) =>
          m.raw_html ? (
            <div
              key={i}
              className="diary-html text-sm leading-relaxed text-foreground/90 [&_img]:max-w-full [&_img]:rounded-lg [&_img]:my-1.5 [&_h3]:font-semibold [&_p]:my-0.5"
              dangerouslySetInnerHTML={{ __html: withImageHost(m.raw_html) }}
            />
          ) : m.role === "user" ? (
            <p key={i} className="text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap">
              {m.content}
            </p>
          ) : (
            <p
              key={i}
              className="border-l-2 border-amber-500/20 pl-2.5 text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap"
            >
              {m.content}
            </p>
          )
        )}
      </div>
    </div>
  );
});

// 타이핑 인디케이터(점 3개) + 경과 초(1s, 2s…) — 대기 길어질 때(비전 캡션 등) 표시
function TypingDots() {
  const [sec, setSec] = useState(0);
  useEffect(() => {
    const start = performance.now();
    const id = setInterval(() => setSec(Math.floor((performance.now() - start) / 1000)), 200);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="inline-flex items-center gap-2 rounded-2xl rounded-tl-md bg-muted/60 dark:bg-muted/40 px-4 py-3">
      <span className="inline-flex items-center gap-1">
        {[0, 0.15, 0.3].map((d) => (
          <span
            key={d}
            className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60 animate-bounce"
            style={{ animationDelay: `${d}s` }}
          />
        ))}
      </span>
      {sec >= 1 && <span className="text-xs tabular-nums text-muted-foreground">{sec}s</span>}
    </div>
  );
}

function AssistantBlock({ msg }: { msg: Message }) {
  return (
    <div className="space-y-2.5">
      {msg.recall && msg.recall.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </svg>
            그때 일기 {msg.recall.length}건
          </div>
          {msg.recall.map((s) => (
            <RecallCard key={s.session_id} s={s} />
          ))}
        </div>
      )}
      {msg.text && (
        <div className="inline-block max-w-[88%] rounded-2xl rounded-tl-md bg-muted/60 dark:bg-muted/40 px-4 py-2.5 text-[15px] leading-relaxed text-foreground whitespace-pre-wrap">
          {msg.text}
        </div>
      )}
      {msg.status === "streaming" && !msg.text && <TypingDots />}
      {msg.status === "error" && (
        <div className="text-xs text-red-600 dark:text-red-400">⚠ {msg.error}</div>
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

  const addFiles = useCallback(async (files: FileList | null) => {
    if (!files) return;
    const imgs = Array.from(files).filter((f) => f.type.startsWith("image/"));
    const urls: string[] = [];
    for (const f of imgs) {
      if (f.size > MAX_IMAGE_BYTES) {
        alert(`${f.name} 은(는) 10MB 를 넘어 건너뜁니다.`);
        continue;
      }
      urls.push(await readAsDataUrl(f));
    }
    if (urls.length) setPending((prev) => [...prev, ...urls].slice(0, MAX_IMAGES));
  }, []);

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
        <div className="absolute inset-0 z-50 m-2 flex items-center justify-center rounded-2xl border-2 border-dashed border-blue-500 bg-blue-500/10 backdrop-blur-[1px] pointer-events-none">
          <div className="rounded-xl bg-card px-5 py-3 text-sm font-medium text-blue-600 dark:text-blue-300 shadow-lg">
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
        <div className="flex-1 min-h-0 flex flex-col items-center justify-center gap-3 px-4 pb-24">
          <h2 className="text-2xl font-semibold text-foreground">오늘은 어땠어?</h2>
          <p className="text-sm text-muted-foreground">
            그냥 떠오르는 대로 적어. 예전 일이 궁금하면 물어봐도 돼.
          </p>
        </div>
      ) : (
        <div
          ref={scrollRef}
          className="flex-1 min-h-0 overflow-y-auto w-full max-w-[820px] mx-auto px-4 py-4 space-y-5"
        >
          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} data-mid={m.id} className="flex justify-end">
                <div className="rounded-2xl rounded-tr-md bg-blue-500 text-white dark:bg-blue-600 px-3.5 py-2.5 text-[15px] max-w-[82%] space-y-2 shadow-sm">
                  {m.images && m.images.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {m.images.map((src, i) => (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          key={i}
                          src={src}
                          alt="첨부 이미지"
                          className="max-h-48 rounded-lg border border-white/20"
                        />
                      ))}
                    </div>
                  )}
                  {m.text && <div className="whitespace-pre-wrap leading-relaxed">{m.text}</div>}
                </div>
              </div>
            ) : (
              <div key={m.id} className="flex justify-start">
                <div className="w-full">
                  <AssistantBlock msg={m} />
                </div>
              </div>
            )
          )}
        </div>
      )}

      {/* 입력창 — 하단 고정 */}
      <form
        className="shrink-0 w-full max-w-[820px] mx-auto px-4 py-3"
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
        {/* 첨부 이미지 미리보기 */}
        {pending.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {pending.map((src, i) => (
              <div key={i} className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={src} alt="첨부 미리보기" className="h-16 w-16 object-cover rounded-md border border-border" />
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
        <div className="flex items-end gap-2 rounded-2xl border border-border bg-card px-3 py-2 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/30">
          {/* 이미지 첨부 */}
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
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy || pending.length >= MAX_IMAGES}
            title="사진 첨부"
            aria-label="사진 첨부"
            className="shrink-0 text-muted-foreground hover:text-blue-500 disabled:opacity-30"
          >
            <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="9" cy="9" r="2" />
              <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
            </svg>
          </button>
          <textarea
            ref={taRef}
            rows={1}
            className="flex-1 bg-transparent outline-none resize-none text-sm text-foreground placeholder:text-muted-foreground"
            style={{ maxHeight: 200 }}
            placeholder="오늘 있었던 일, 떠오른 생각…"
            value={input}
            disabled={busy}
            autoFocus
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
          {busy ? (
            <button
              type="button"
              onClick={abort}
              title="중단"
              aria-label="중단"
              className="shrink-0 text-red-500 hover:text-red-600"
            >
              <svg width={18} height={18} viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            </button>
          ) : (
            <button
              type="submit"
              title="전송"
              aria-label="전송"
              disabled={!input.trim() && pending.length === 0}
              className="shrink-0 text-muted-foreground hover:text-blue-500 disabled:opacity-30"
            >
              <svg
                width={20}
                height={20}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="9 10 4 15 9 20" />
                <path d="M20 4v7a4 4 0 0 1-4 4H4" />
              </svg>
            </button>
          )}
        </div>
      </form>
    </main>
  );
}
