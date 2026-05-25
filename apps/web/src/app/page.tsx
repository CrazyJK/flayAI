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
const RECENT_STORAGE_KEY = "flayai-chat-recent";
// 첫 화면 제안: examples.json + 최근 질의를 합쳐 최대 9개 (json 우선)
const MAX_SUGGESTIONS = 9;

// 종류 표시 라벨 — 닫힘 상태에선 대문자로 시작하는 값만 노출 (All/Instance/Archive)
const KIND_LABELS: Record<string, string> = { "": "All", instance: "Instance", archive: "Archive" };
const kindLabel = (k: string) => KIND_LABELS[k] ?? "All";

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
  const [recent, setRecent] = useState<string[]>([]);
  // 열려있는 옵션 팝오버 (개수/종류) — 동시에 하나만
  const [openOpt, setOpenOpt] = useState<null | "limit" | "kind">(null);
  // 개수 직접 입력 임시값
  const [customLimit, setCustomLimit] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // limit / kind 선택값을 localStorage 에서 복원 (마운트 후 — SSR 하이드레이션 불일치 방지)
  useEffect(() => {
    const saved = Number(window.localStorage.getItem(LIMIT_STORAGE_KEY));
    if (Number.isFinite(saved) && saved > 0) setLimit(saved);
    const savedKind = window.localStorage.getItem(KIND_STORAGE_KEY) ?? "";
    if (KIND_OPTIONS.some((o) => o.value === savedKind)) setKind(savedKind);
    try {
      const raw = window.localStorage.getItem(RECENT_STORAGE_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      if (Array.isArray(arr)) setRecent(arr.filter((x): x is string => typeof x === "string"));
    } catch {
      // 손상된 저장값 무시
    }
  }, []);

  const updateAssistant = useCallback((id: string, patch: (m: Message) => Message) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? patch(m) : m)));
  }, []);

  // 최근 질의 기록 — 중복 제거 후 맨 앞에 추가, localStorage 보존
  const pushRecent = useCallback((q: string) => {
    const query = q.trim();
    if (!query) return;
    setRecent((prev) => {
      const next = [query, ...prev.filter((x) => x !== query)].slice(0, MAX_SUGGESTIONS);
      window.localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const send = useCallback(
    async (query: string) => {
      if (!query.trim() || busy) return;
      pushRecent(query);
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
    [busy, limit, kind, updateAssistant, pushRecent]
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // 아직 대화가 없는 첫 로딩 상태 — 입력창을 화면 중앙에 크고 밝게 배치
  const empty = messages.length === 0;

  // 첫 화면 제안: examples.json 먼저, 나머지를 최근 질의로 채워 최대 9개
  const suggestions = [...examples, ...recent.filter((q) => !examples.includes(q))].slice(
    0,
    MAX_SUGGESTIONS
  );

  // 입력 폼: 질의 영역 전체를 하나의 박스로 감싸고, 박스 하단에 옵션(개수·종류)과
  // 전송 버튼을 배치(코파일럿/클로드/제미나이 스타일). hero(첫 로딩·중앙·크게) /
  // docked(질의 후·하단 고정) 두 변형으로 크기만 분기.
  const renderForm = (hero: boolean) => (
    <form
      className={hero ? "w-full max-w-[760px]" : "shrink-0 w-full max-w-[900px] mx-auto px-4 py-3"}
      onSubmit={(e) => {
        e.preventDefault();
        const q = input;
        setInput("");
        if (taRef.current) taRef.current.style.height = "auto";
        void send(q);
      }}
    >
      {/* 질의 영역 전체를 감싸는 박스 */}
      <div
        className={
          "flex flex-col gap-2 rounded-2xl transition-colors focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/30 " +
          (hero
            ? "border border-neutral-600 bg-neutral-800 px-4 pt-3.5 pb-2 shadow-lg shadow-black/40"
            : "border border-neutral-700 bg-neutral-900 px-3 pt-3 pb-1.5")
        }
      >
        {/* 상단: 입력 (Enter 전송 / Shift+Enter 줄바꿈, 내용에 따라 높이 자동 확장) */}
        <textarea
          ref={taRef}
          rows={1}
          className={
            "w-full bg-transparent outline-none resize-none placeholder:text-neutral-400 text-neutral-100 " +
            (hero ? "text-lg" : "text-sm")
          }
          style={{ maxHeight: 200 }}
          placeholder="무엇을 찾을까요?"
          value={input}
          disabled={busy}
          autoFocus={hero}
          onChange={(e) => setInput(e.target.value)}
          onInput={(e) => {
            const ta = e.currentTarget;
            ta.style.height = "auto";
            ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
          }}
          onKeyDown={(e) => {
            // IME(한글) 조합 중이 아니고 Shift 없이 Enter → 전송
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
        />

        {/* 하단: 좌측 검색 옵션(개수·종류) / 우측 전송·중단 */}
        <div className="flex items-center gap-2">
          {/* 개수 — 닫힘: 숫자만 / 열림: '개수' 라벨 + 프리셋 + 직접 입력 */}
          <div className="relative">
            <button
              type="button"
              onClick={() => {
                setCustomLimit(String(limit));
                setOpenOpt((o) => (o === "limit" ? null : "limit"));
              }}
              title="결과 개수"
              className="rounded-full border border-neutral-700 bg-neutral-950/60 px-2.5 py-1 text-xs text-neutral-200 hover:border-neutral-600"
            >
              {limit}
            </button>
            {openOpt === "limit" && (
              <>
                <button
                  type="button"
                  aria-label="닫기"
                  className="fixed inset-0 z-10 cursor-default"
                  onClick={() => setOpenOpt(null)}
                />
                <div className="absolute bottom-full left-0 mb-2 z-20 w-48 rounded-lg border border-neutral-700 bg-neutral-900 p-2.5 shadow-xl space-y-2">
                  <div className="text-xs font-semibold text-neutral-400">개수</div>
                  <div className="flex flex-wrap gap-1">
                    {LIMIT_OPTIONS.map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => {
                          setLimit(n);
                          window.localStorage.setItem(LIMIT_STORAGE_KEY, String(n));
                          setOpenOpt(null);
                        }}
                        className={
                          "px-2 py-1 text-xs rounded-md border " +
                          (n === limit
                            ? "border-blue-500 bg-blue-500/20 text-blue-200"
                            : "border-neutral-700 text-neutral-300 hover:bg-neutral-800")
                        }
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      min={1}
                      value={customLimit}
                      onChange={(e) => setCustomLimit(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          const n = parseInt(customLimit, 10);
                          if (Number.isFinite(n) && n > 0) {
                            setLimit(n);
                            window.localStorage.setItem(LIMIT_STORAGE_KEY, String(n));
                          }
                          setOpenOpt(null);
                        }
                      }}
                      placeholder="직접 입력"
                      className="w-20 px-2 py-1 text-xs rounded-md bg-neutral-950 border border-neutral-700 outline-none focus:border-blue-500 text-neutral-200"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        const n = parseInt(customLimit, 10);
                        if (Number.isFinite(n) && n > 0) {
                          setLimit(n);
                          window.localStorage.setItem(LIMIT_STORAGE_KEY, String(n));
                        }
                        setOpenOpt(null);
                      }}
                      className="px-2 py-1 text-xs rounded-md bg-neutral-800 hover:bg-neutral-700 text-neutral-200"
                    >
                      적용
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* 종류 — 닫힘: 값만(All/Instance/Archive) / 열림: '종류' 라벨 + 선택 */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setOpenOpt((o) => (o === "kind" ? null : "kind"))}
              title="종류"
              className="rounded-full border border-neutral-700 bg-neutral-950/60 px-2.5 py-1 text-xs text-neutral-200 hover:border-neutral-600"
            >
              {kindLabel(kind)}
            </button>
            {openOpt === "kind" && (
              <>
                <button
                  type="button"
                  aria-label="닫기"
                  className="fixed inset-0 z-10 cursor-default"
                  onClick={() => setOpenOpt(null)}
                />
                <div className="absolute bottom-full left-0 mb-2 z-20 w-36 rounded-lg border border-neutral-700 bg-neutral-900 p-2.5 shadow-xl space-y-2">
                  <div className="text-xs font-semibold text-neutral-400">종류</div>
                  <div className="flex flex-col gap-1">
                    {KIND_OPTIONS.map((o) => (
                      <button
                        key={o.value}
                        type="button"
                        onClick={() => {
                          setKind(o.value);
                          window.localStorage.setItem(KIND_STORAGE_KEY, o.value);
                          setOpenOpt(null);
                        }}
                        className={
                          "px-2 py-1 text-xs rounded-md text-left border " +
                          (o.value === kind
                            ? "border-blue-500 bg-blue-500/20 text-blue-200"
                            : "border-neutral-700 text-neutral-300 hover:bg-neutral-800")
                        }
                      >
                        {kindLabel(o.value)}
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>

          {busy ? (
            <button
              type="button"
              onClick={abort}
              title="중단"
              aria-label="중단"
              className="ml-auto shrink-0 flex items-center justify-center text-red-400 hover:text-red-300"
            >
              <svg
                width={hero ? 22 : 18}
                height={hero ? 22 : 18}
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            </button>
          ) : (
            <button
              type="submit"
              title="전송"
              aria-label="전송"
              disabled={!input.trim()}
              className="ml-auto shrink-0 flex items-center justify-center text-neutral-300 hover:text-blue-400 disabled:opacity-30 disabled:hover:text-neutral-300"
            >
              {/* 엔터(↵) 모양 — corner-down-left */}
              <svg
                width={hero ? 24 : 20}
                height={hero ? 24 : 20}
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
      </div>
    </form>
  );

  return (
    <main className="flex-1 flex flex-col w-full min-h-0">
      <AppHeader active="chat" />

      {empty ? (
        // 첫 로딩: 구글처럼 입력창을 화면 중앙에 크고 밝게 배치
        <div className="flex-1 min-h-0 flex flex-col items-center justify-center gap-7 px-4 pb-16">
          <h2 className="text-3xl sm:text-4xl font-semibold text-neutral-100">무엇을 찾을까요?</h2>
          {renderForm(true)}
          <div className="flex flex-wrap gap-2 justify-center max-w-[760px]">
            {suggestions.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => send(q)}
                className="px-3 py-1.5 text-sm rounded-full border border-neutral-700 text-neutral-300 hover:bg-neutral-800 hover:text-neutral-100"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      ) : (
        // 질의 후: 대화 영역 + 하단 고정 입력창
        <>
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
          {renderForm(false)}
        </>
      )}
    </main>
  );
}
