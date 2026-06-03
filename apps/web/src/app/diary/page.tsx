"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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

// 회상 카드: 그때 일기 한 건(날짜·제목·날씨 + 원문)
function RecallCard({ s }: { s: RecallSession }) {
  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 dark:bg-amber-400/5 p-3 space-y-2">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="font-mono text-amber-700 dark:text-amber-300">{s.date}</span>
        {s.weather && <span>{WEATHER_ICON[s.weather] ?? s.weather}</span>}
        {s.title && <span className="font-semibold text-foreground">{s.title}</span>}
      </div>
      <div className="space-y-2">
        {s.messages.map((m, i) =>
          m.raw_html ? (
            <div
              key={i}
              className="diary-html text-sm leading-relaxed text-foreground [&_img]:max-w-full [&_img]:rounded-md [&_h3]:font-semibold"
              dangerouslySetInnerHTML={{ __html: withImageHost(m.raw_html) }}
            />
          ) : (
            <div
              key={i}
              className={
                m.role === "user"
                  ? "text-sm whitespace-pre-wrap text-foreground"
                  : "text-sm whitespace-pre-wrap text-muted-foreground"
              }
            >
              {m.content}
            </div>
          )
        )}
      </div>
    </div>
  );
}

function AssistantBlock({ msg }: { msg: Message }) {
  return (
    <div className="space-y-2">
      {msg.recall && msg.recall.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-muted-foreground">↳ 그때 일기 {msg.recall.length}건</div>
          {msg.recall.map((s) => (
            <RecallCard key={s.session_id} s={s} />
          ))}
        </div>
      )}
      {msg.text && (
        <div className="whitespace-pre-wrap text-foreground leading-relaxed">{msg.text}</div>
      )}
      {msg.status === "streaming" && !msg.text && (
        <div className="text-xs text-muted-foreground animate-pulse">…</div>
      )}
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
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const stickRef = useRef(true); // 하단 근처면 자동 스크롤 유지, 위로 올리면 멈춤
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  // 스크롤이 하단 근처인지 추적(위로 올려 일기 읽는 중엔 자동 스크롤 안 함)
  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (el) stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }, []);
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
    // 하단 근처일 때만 즉시(애니메이션 없이) 하단으로 — 스트리밍 중 덜컹임 방지
    if (!stickRef.current) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
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
      stickRef.current = true; // 새로 보내면 하단으로 따라가기 재개
      const userMsg: Message = {
        id: `u-${Date.now()}`,
        role: "user",
        text: query,
        images: images.length ? images : undefined,
        status: "done",
      };
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

  return (
    <main className="flex-1 flex flex-col w-full min-h-0">
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
          onScroll={onScroll}
          className="flex-1 min-h-0 overflow-y-auto w-full max-w-[820px] mx-auto px-4 py-4 space-y-5"
        >
          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="flex justify-end">
                <div className="rounded-lg bg-blue-500/15 dark:bg-blue-600/30 border border-blue-500/40 px-3 py-2 text-sm max-w-[80%] space-y-2">
                  {m.images && m.images.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {m.images.map((src, i) => (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          key={i}
                          src={src}
                          alt="첨부 이미지"
                          className="max-h-48 rounded-md border border-blue-500/30"
                        />
                      ))}
                    </div>
                  )}
                  {m.text && <div className="whitespace-pre-wrap">{m.text}</div>}
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
