"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AppHeader from "./_components/AppHeader";
import examples from "./examples.json";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ai.kamoru.jk:8000";
const LIMIT_OPTIONS = [5, 10, 20, 30, 50];
const LIMIT_STORAGE_KEY = "flayai-chat-limit";
// instance(지금 볼 수 있는) / archive(보관) 필터. "" = 전체
const KIND_OPTIONS = [
  { value: "", label: "전체" },
  { value: "instance", label: "instance" },
  { value: "archive", label: "archive" },
] as const;
const KIND_STORAGE_KEY = "flayai-chat-kind";

type VideoHit = {
  opus: string;
  title?: string | null;
  title_jp?: string | null;
  title_ko?: string | null;
  studio?: string | null;
  year?: number | null;
  month?: number | null;
  kind?: "instance" | "archive" | null;
  rank?: number | null;
  play?: number | null;
  like_count?: number | null;
  actresses?: string[];
  score?: number;
};

type ToolEvent = { name: string; args?: Record<string, unknown> };
type ToolResult = { name: string; result: unknown };

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  toolCalls: ToolEvent[];
  toolResults: ToolResult[];
  status: "streaming" | "done" | "error" | "aborted";
  error?: string;
};

function extractHits(result: unknown): VideoHit[] {
  if (Array.isArray(result)) return result as VideoHit[];
  if (
    result &&
    typeof result === "object" &&
    Array.isArray((result as { items?: unknown }).items)
  ) {
    return (result as { items: VideoHit[] }).items;
  }
  return [];
}

function KindBadge({ kind }: { kind?: string | null }) {
  if (!kind) return null;
  const isInstance = kind === "instance";
  return (
    <span
      className={
        "px-1.5 py-0.5 text-xs rounded font-mono " +
        (isInstance
          ? "bg-emerald-500/30 text-emerald-200 border border-emerald-500/50"
          : "bg-neutral-500/30 text-neutral-200 border border-neutral-500/50")
      }
    >
      {isInstance ? "INSTANCE" : "ARCHIVE"}
    </span>
  );
}

function openFlayPopup(opus: string) {
  window.open(
    `https://flay.kamoru.jk/dist/popup.flay.html?opus=${encodeURIComponent(opus)}`,
    `flay_${opus}`,
    "width=900,height=1400,resizable=yes,scrollbars=yes"
  );
}

function VideoCard({ hit }: { hit: VideoHit }) {
  const title = hit.title || hit.title_ko || hit.title_jp || hit.opus;
  const posterUrl = `${API_BASE}/static/posters/${encodeURIComponent(hit.opus)}`;
  return (
    <div
      className="relative aspect-[400/269] rounded-md overflow-hidden border border-neutral-800 cursor-pointer"
      onClick={() => openFlayPopup(hit.opus)}
      title={`팝업으로 열기: ${hit.opus}`}
    >
      {/* 배경 포스터 이미지 */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={posterUrl}
        alt={hit.opus}
        className="absolute inset-0 w-full h-full object-cover bg-neutral-900"
      />

      {/* 상단 오버레이: opus, 배지, 스코어 */}
      <div className="absolute top-0 inset-x-0 bg-gradient-to-b from-black/90 via-black/45 to-transparent px-2 py-2 [text-shadow:0_1px_2px_rgba(0,0,0,0.9)]">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-mono text-sm text-amber-300">{hit.opus}</span>
          <KindBadge kind={hit.kind} />
          {typeof hit.rank === "number" && hit.rank > 0 && (
            <span className="px-1.5 py-0.5 text-xs rounded bg-yellow-500/30 text-yellow-100">
              {"⭐".repeat(hit.rank)}
            </span>
          )}
          {typeof hit.score === "number" && (
            <span className="ml-auto font-mono text-xs text-neutral-200">
              {hit.score.toFixed(3)}
            </span>
          )}
        </div>
      </div>

      {/* 하단 오버레이: 제목, 메타 정보 */}
      <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/95 via-black/65 to-transparent px-2 pt-8 pb-2 [text-shadow:0_1px_2px_rgba(0,0,0,0.95)]">
        <div className="font-semibold text-base text-white truncate">{title}</div>
        <div className="mt-0.5 text-sm text-neutral-200 flex flex-wrap gap-x-2 gap-y-0">
          {hit.studio && <span>{hit.studio}</span>}
          {hit.year && (
            <span>
              {hit.year}
              {hit.month ? `-${String(hit.month).padStart(2, "0")}` : ""}
            </span>
          )}
          {hit.actresses && hit.actresses.length > 0 && <span>👤 {hit.actresses.join(", ")}</span>}
          {typeof hit.play === "number" && hit.play > 0 && (
            <span title="재생 수">▶︎ {hit.play}</span>
          )}
          {typeof hit.like_count === "number" && hit.like_count > 0 && (
            <span title="좋아요 수">💛 {hit.like_count}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function ToolCallChip({ ev }: { ev: ToolEvent }) {
  const [expanded, setExpanded] = useState(false);
  const argsStr = ev.args ? JSON.stringify(ev.args) : "";
  const truncatable = argsStr.length > 80;
  const displayed = truncatable && !expanded ? argsStr.slice(0, 80) + "…" : argsStr;
  return (
    <div className="text-xs font-mono text-neutral-400 flex items-start gap-1 flex-wrap justify-center">
      <span className="text-cyan-300 shrink-0">⚙ {ev.name}</span>
      <span className="text-neutral-600 break-all">
        {argsStr.length > 0 ? `(${displayed})` : "()"}
      </span>
      {truncatable && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="shrink-0 text-neutral-500 hover:text-neutral-300 leading-none"
          title={expanded ? "접기" : "펼치기"}
        >
          {expanded ? "▲" : "▼"}
        </button>
      )}
    </div>
  );
}

function AssistantBlock({ msg }: { msg: Message }) {
  // 모든 toolResults의 VideoHit를 opus 기준으로 중복 제거하여 합산
  const allHits: VideoHit[] = [];
  const seenOpus = new Set<string>();
  for (const r of msg.toolResults) {
    for (const h of extractHits(r.result)) {
      if (!seenOpus.has(h.opus)) {
        seenOpus.add(h.opus);
        allHits.push(h);
      }
    }
  }
  const emptyResults = msg.toolResults.filter((r) => extractHits(r.result).length === 0);

  return (
    <div className="space-y-2">
      {msg.toolCalls.map((c, i) => (
        <ToolCallChip key={`c-${i}`} ev={c} />
      ))}
      {emptyResults.map((r, i) => (
        <div key={`r-empty-${i}`} className="text-xs text-neutral-500 font-mono text-center">
          ↳ {r.name} → 0 items
        </div>
      ))}
      {allHits.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs text-neutral-500 font-mono text-center">↳ {allHits.length} items</div>
          <div className="grid gap-2 grid-cols-[repeat(auto-fill,minmax(440px,1fr))]">
            {allHits.map((h) => (
              <VideoCard key={h.opus} hit={h} />
            ))}
          </div>
        </div>
      )}
      {msg.text && (
        <div className="whitespace-pre-wrap text-neutral-100 leading-relaxed text-center">
          {msg.text}
        </div>
      )}
      {msg.status === "streaming" && (
        <div className="text-xs text-neutral-500 animate-pulse text-center">생성 중…</div>
      )}
      {msg.status === "aborted" && (
        <div className="text-xs text-amber-400 text-center">⏹ 중단됨</div>
      )}
      {msg.status === "error" && (
        <div className="text-xs text-red-400 text-center">⚠ {msg.error}</div>
      )}
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [limit, setLimit] = useState(10);
  const [kind, setKind] = useState<string>("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // limit / kind 선택값을 localStorage 에서 복원 (마운트 후 — SSR 하이드레이션 불일치 방지)
  useEffect(() => {
    const saved = Number(window.localStorage.getItem(LIMIT_STORAGE_KEY));
    if (LIMIT_OPTIONS.includes(saved)) setLimit(saved);
    const savedKind = window.localStorage.getItem(KIND_STORAGE_KEY) ?? "";
    if (KIND_OPTIONS.some((o) => o.value === savedKind)) setKind(savedKind);
  }, []);

  const updateAssistant = useCallback((id: string, patch: (m: Message) => Message) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? patch(m) : m)));
  }, []);

  const send = useCallback(
    async (query: string) => {
      if (!query.trim() || busy) return;
      const userMsg: Message = {
        id: `u-${Date.now()}`,
        role: "user",
        text: query,
        toolCalls: [],
        toolResults: [],
        status: "done",
      };
      const asstId = `a-${Date.now()}`;
      const asstMsg: Message = {
        id: asstId,
        role: "assistant",
        text: "",
        toolCalls: [],
        toolResults: [],
        status: "streaming",
      };
      setMessages((prev) => [...prev, userMsg, asstMsg]);
      setBusy(true);

      const ac = new AbortController();
      abortRef.current = ac;
      try {
        const r = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "content-type": "application/json", accept: "text/event-stream" },
          body: JSON.stringify({ query, limit, kind: kind || undefined }),
          signal: ac.signal,
        });
        if (!r.ok || !r.body) {
          throw new Error(`HTTP ${r.status}`);
        }
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          // SSE 이벤트 경계: 빈 줄 (\n\n 또는 \r\n\r\n)
          const parts = buf.split(/\r?\n\r?\n/);
          buf = parts.pop() ?? "";
          for (const evBlock of parts) {
            // 한 이벤트 내 모든 data: 라인을 모음
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
              case "tool_call":
                updateAssistant(asstId, (m) => ({
                  ...m,
                  toolCalls: [
                    ...m.toolCalls,
                    {
                      name: String(ev.name ?? ""),
                      args: ev.args as Record<string, unknown> | undefined,
                    },
                  ],
                }));
                break;
              case "tool_result":
                updateAssistant(asstId, (m) => ({
                  ...m,
                  toolResults: [
                    ...m.toolResults,
                    { name: String(ev.name ?? ""), result: ev.result },
                  ],
                }));
                break;
              case "token":
                updateAssistant(asstId, (m) => ({ ...m, text: m.text + String(ev.text ?? "") }));
                break;
              case "done":
                updateAssistant(asstId, (m) => ({
                  ...m,
                  text: m.text || String(ev.message ?? ""),
                  status: "done",
                }));
                break;
              case "error":
                updateAssistant(asstId, (m) => ({
                  ...m,
                  status: "error",
                  error: String(ev.error ?? ev.message ?? "unknown error"),
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
    [busy, limit, kind, updateAssistant]
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return (
    <main className="flex-1 flex flex-col w-full min-h-0">
      <AppHeader active="chat" />

      <div className="flex-1 min-h-0 overflow-y-auto w-full px-4 xl:px-6 py-4 space-y-6">
        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="flex justify-end">
              <div className="rounded-lg bg-blue-600/30 border border-blue-500/40 px-3 py-2 text-sm max-w-[80%]">
                {m.text}
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
        <div ref={bottomRef} />
      </div>

      {messages.length === 0 && (
        <div className="shrink-0 mx-auto w-full max-w-[900px] px-4 pb-1 text-sm text-neutral-400 space-y-2">
          <p className="text-center">자연어로 비디오 컬렉션을 검색하세요. 예시:</p>
          <div className="flex flex-wrap gap-2 justify-center">
            {examples.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => send(q)}
                className="px-2.5 py-1 text-xs rounded border border-neutral-700 hover:bg-neutral-800"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      <form
        className="shrink-0 mx-auto w-full max-w-[900px] px-4 py-3 border-t border-neutral-800 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const q = input;
          setInput("");
          void send(q);
        }}
      >
        <input
          className="flex-1 px-3 py-2 rounded-md bg-neutral-900 border border-neutral-700 outline-none focus:border-blue-500 text-sm"
          placeholder="무엇을 찾을까요?"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
        />
        {/* 검색 설정(개수·종류) — 톱니바퀴 버튼 → 팝오버 */}
        <div className="relative shrink-0">
          <button
            type="button"
            onClick={() => setSettingsOpen((v) => !v)}
            className="relative px-3 py-2 rounded-md bg-neutral-900 border border-neutral-700 text-neutral-300 hover:bg-neutral-800"
            title="검색 설정 (개수·종류)"
            aria-label="검색 설정"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            {/* 비-기본 필터 적용 시 표시 점 (kind 가 설정됨) */}
            {kind && (
              <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-blue-500 border border-neutral-900" />
            )}
          </button>
          {settingsOpen && (
            <>
              {/* 바깥 클릭 시 닫기 */}
              <button
                type="button"
                aria-label="설정 닫기"
                className="fixed inset-0 z-10 cursor-default"
                onClick={() => setSettingsOpen(false)}
              />
              <div className="absolute bottom-full right-0 mb-2 z-20 w-56 rounded-lg border border-neutral-700 bg-neutral-900 p-3 shadow-xl space-y-3">
                <div className="text-xs font-semibold text-neutral-300">검색 설정</div>
                <label className="block space-y-1">
                  <span className="text-xs text-neutral-400">결과 개수</span>
                  <select
                    className="w-full px-2 py-1.5 rounded-md bg-neutral-950 border border-neutral-700 text-sm text-neutral-200 outline-none focus:border-blue-500"
                    value={limit}
                    onChange={(e) => {
                      const n = Number(e.target.value);
                      setLimit(n);
                      window.localStorage.setItem(LIMIT_STORAGE_KEY, String(n));
                    }}
                  >
                    {LIMIT_OPTIONS.map((n) => (
                      <option key={n} value={n}>
                        {n}개
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block space-y-1">
                  <span className="text-xs text-neutral-400">종류 (instance/archive)</span>
                  <select
                    className="w-full px-2 py-1.5 rounded-md bg-neutral-950 border border-neutral-700 text-sm text-neutral-200 outline-none focus:border-blue-500"
                    value={kind}
                    onChange={(e) => {
                      const v = e.target.value;
                      setKind(v);
                      window.localStorage.setItem(KIND_STORAGE_KEY, v);
                    }}
                  >
                    {KIND_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </>
          )}
        </div>
        {busy ? (
          <button
            type="button"
            onClick={abort}
            className="px-4 py-2 text-sm rounded-md bg-red-600 hover:bg-red-500"
          >
            중단
          </button>
        ) : (
          <button
            type="submit"
            className="px-4 py-2 text-sm rounded-md bg-blue-600 hover:bg-blue-500 disabled:opacity-50"
            disabled={!input.trim()}
          >
            전송
          </button>
        )}
      </form>
    </main>
  );
}
