"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

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
  playable?: boolean;
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
        "px-1.5 py-0.5 text-[10px] rounded font-mono " +
        (isInstance
          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
          : "bg-neutral-500/20 text-neutral-300 border border-neutral-500/40")
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
  return (
    <div className="rounded-md border border-neutral-800 bg-neutral-900/60 p-3 text-sm">
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className="font-mono text-xs text-amber-300 cursor-pointer hover:text-amber-200 hover:underline"
          onClick={() => openFlayPopup(hit.opus)}
          title={`팝업으로 열기: ${hit.opus}`}
        >
          {hit.opus}
        </span>
        <KindBadge kind={hit.kind} />
        {hit.playable && (
          <span className="px-1.5 py-0.5 text-[10px] rounded bg-blue-500/20 text-blue-300 border border-blue-500/40">
            ▶ PLAYABLE
          </span>
        )}
        {typeof hit.rank === "number" && hit.rank > 0 && (
          <span className="px-1.5 py-0.5 text-[10px] rounded bg-yellow-500/20 text-yellow-200">
            ★ {hit.rank}
          </span>
        )}
        {typeof hit.score === "number" && (
          <span className="ml-auto font-mono text-[10px] text-neutral-500">
            score {hit.score.toFixed(3)}
          </span>
        )}
      </div>
      <div className="mt-1 font-medium text-neutral-100">{title}</div>
      <div className="mt-1 text-xs text-neutral-400 flex flex-wrap gap-x-3 gap-y-0.5">
        {hit.studio && <span>🏷 {hit.studio}</span>}
        {hit.year && (
          <span>
            📅 {hit.year}
            {hit.month ? `-${String(hit.month).padStart(2, "0")}` : ""}
          </span>
        )}
        {hit.actresses && hit.actresses.length > 0 && <span>👤 {hit.actresses.join(", ")}</span>}
        {typeof hit.play === "number" && hit.play > 0 && <span>▶︎ {hit.play}</span>}
        {typeof hit.like_count === "number" && hit.like_count > 0 && (
          <span>♥ {hit.like_count}</span>
        )}
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
    <div className="text-xs font-mono text-neutral-400 flex items-start gap-1 flex-wrap">
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
        <div key={`r-empty-${i}`} className="text-xs text-neutral-500 font-mono">
          ↳ {r.name} → 0 items
        </div>
      ))}
      {allHits.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs text-neutral-500 font-mono">↳ {allHits.length} items</div>
          <div className="grid gap-2 grid-cols-1 md:grid-cols-2">
            {allHits.map((h) => (
              <VideoCard key={h.opus} hit={h} />
            ))}
          </div>
        </div>
      )}
      {msg.text && (
        <div className="whitespace-pre-wrap text-neutral-100 leading-relaxed">{msg.text}</div>
      )}
      {msg.status === "streaming" && (
        <div className="text-xs text-neutral-500 animate-pulse">생성 중…</div>
      )}
      {msg.status === "aborted" && <div className="text-xs text-amber-400">⏹ 중단됨</div>}
      {msg.status === "error" && <div className="text-xs text-red-400">⚠ {msg.error}</div>}
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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
          body: JSON.stringify({ query }),
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
    [busy, updateAssistant]
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const examples = [
    "Alice Smith 출연작 5개 추천해줘",
    "2023년 7월 발매작 보여줘",
    "StudioA 제작사 평점 4 이상 영상",
    "지금 볼 수 있는 회사 배경 영상",
  ];

  return (
    <main className="flex-1 flex flex-col mx-auto w-full max-w-4xl px-4">
      <header className="py-4 border-b border-neutral-800 flex items-baseline gap-2">
        <h1 className="text-lg font-semibold">flayAI</h1>
        <span className="text-xs text-neutral-500 font-mono">{API_BASE}</span>
        <nav className="ml-auto flex items-center gap-3 text-xs">
          <Link href="/" className="text-neutral-200">
            채팅
          </Link>
          <a href="/image" className="text-neutral-400 hover:text-neutral-200">
            이미지
          </a>
          <a href="/face" className="text-neutral-400 hover:text-neutral-200">
            얼굴
          </a>
          <a href="/labels" className="text-neutral-400 hover:text-neutral-200">
            라벨링
          </a>
        </nav>
      </header>

      <div className="flex-1 overflow-y-auto py-4 space-y-6">
        {messages.length === 0 && (
          <div className="text-sm text-neutral-400 space-y-3">
            <p>자연어로 비디오 컬렉션을 검색하세요. 예시:</p>
            <div className="flex flex-wrap gap-2">
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

      <form
        className="py-3 border-t border-neutral-800 flex gap-2"
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
