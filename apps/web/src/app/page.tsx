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
  // 채택 근거: ranker 의 정규화 기여도(결과셋 내 상대값, 0~1). 메타전용 질의엔 없음.
  score_breakdown?: { semantic: number; fts: number; usage: number; recency: number };
  caption?: string | null; // 채택 이유(키워드 매칭) 표시용
};

// 채택 이유 문장 생성용 — 질의에서 무시할 흔한 단어(조사·동사·일반어)
const REASON_STOPWORDS = new Set([
  "영상",
  "보여줘",
  "보여",
  "추천",
  "해줘",
  "찾아",
  "찾아줘",
  "나오는",
  "나온",
  "있는",
  "하는",
  "그리고",
  "또는",
  "느낌",
  "같은",
  "관련",
]);

// 질의어 중 hit 텍스트(캡션·제목·배우 등)에 실제로 등장하는 키워드 추출.
// 한국어 조사 대응: 끝 글자를 하나씩 떼며 본문 포함 여부 확인(최소 2자). 최대 4개.
function matchedKeywords(query: string, haystack: string): string[] {
  if (!query || !haystack) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of query.split(/[\s,./·]+/)) {
    const tok = raw.trim();
    if (tok.length < 2 || REASON_STOPWORDS.has(tok)) continue;
    let cand = tok;
    let found = "";
    while (cand.length >= 2) {
      if (haystack.includes(cand)) {
        found = cand;
        break;
      }
      cand = cand.slice(0, -1);
    }
    if (found) {
      // 표시용으로 끝 조사 제거(소파에→소파, 온천에서→온천). 남은 어간이 2자 미만이면 원형 유지.
      const stem = found.replace(
        /(에서|에게서|에게|으로서|으로|부터|까지|에|은|는|이|가|을|를|와|과|이랑|랑|도|만|의|께)$/,
        ""
      );
      const disp = stem.length >= 2 ? stem : found;
      if (!seen.has(disp) && !REASON_STOPWORDS.has(disp)) {
        seen.add(disp);
        out.push(disp);
        if (out.length >= 4) break;
      }
    }
  }
  return out;
}

// hit + 질의 → 사람이 읽는 채택 이유 한 줄(규칙 기반, LLM 미사용).
function buildReason(hit: VideoHit, query: string): string {
  const b = hit.score_breakdown;
  const haystack = [hit.caption, hit.title, hit.title_ko, hit.title_jp, hit.studio, ...(hit.actresses ?? [])]
    .filter(Boolean)
    .join(" ");
  const kws = matchedKeywords(query, haystack);
  const parts: string[] = [];
  if (kws.length) parts.push(`키워드 ${kws.map((w) => `'${w}'`).join("·")} 일치`);
  if (b) {
    if (!kws.length && b.semantic >= 0.5) parts.push("의미가 유사");
    else if (kws.length && b.semantic >= 0.7) parts.push("의미도 유사");
    if (b.usage >= 0.6) parts.push("인기"); // 재생수·평점은 메타 줄에 이미 표시
    if (b.recency >= 0.5) parts.push("최근");
  }
  if (!parts.length) parts.push("관련도 기반 선택");
  return parts.join(" · ");
}

// 점수 기여도 신호 (의미/키워드/인기/최근) — 한 줄 텍스트로 표시
const SCORE_SIGNALS = [
  { key: "semantic", label: "의미" },
  { key: "fts", label: "키워드" },
  { key: "usage", label: "인기" },
  { key: "recency", label: "최근" },
] as const;

// 0~1 정규화 기여도를 100점 만점 정수로 (2자리 0-패딩, 예: 0.96→"96", 0→"00")
const pct100 = (v: number) =>
  String(Math.round(Math.max(0, Math.min(1, v)) * 100)).padStart(2, "0");

// 점수 수치 한 줄 문자열 ("의미: 96, 키워드: 00, ...")
function scoreText(b: NonNullable<VideoHit["score_breakdown"]>): string {
  return SCORE_SIGNALS.map(({ key, label }) => `${label}: ${pct100(b[key] ?? 0)}`).join(", ");
}

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

function VideoCard({ hit, query = "" }: { hit: VideoHit; query?: string }) {
  const title = hit.title || hit.title_ko || hit.title_jp || hit.opus;
  const posterUrl = `${API_BASE}/static/posters/${encodeURIComponent(hit.opus)}`;
  const reason = buildReason(hit, query);
  const scores = hit.score_breakdown ? scoreText(hit.score_breakdown) : "";
  const detailFull = [scores, reason].filter(Boolean).join(" · ");
  return (
    <div
      className="relative aspect-[400/269] rounded-md overflow-hidden border border-border cursor-pointer"
      onClick={() => openFlayPopup(hit.opus)}
      title={`팝업으로 열기: ${hit.opus}`}
    >
      {/* 배경 포스터 이미지 */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={posterUrl}
        alt={hit.opus}
        className="absolute inset-0 w-full h-full object-cover bg-muted"
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
        {/* 채택 근거: 수치 + 사람이 읽는 이유를 한 줄로(넘치면 …, 호버 시 전체) */}
        {detailFull && (
          <div className="mt-1 text-[10px] truncate" title={detailFull}>
            <span className="text-neutral-300 font-mono tabular-nums">{scores}</span>
            {reason && (
              <span className="text-neutral-400">
                {scores ? " · " : ""}
                {reason}
              </span>
            )}
          </div>
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
    <div className="text-xs font-mono text-muted-foreground flex items-start gap-1 flex-wrap justify-center">
      <span className="text-cyan-600 dark:text-cyan-300 shrink-0">⚙ {ev.name}</span>
      <span className="text-muted-foreground break-all">
        {argsStr.length > 0 ? `(${displayed})` : "()"}
      </span>
      {truncatable && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="shrink-0 text-muted-foreground hover:text-foreground leading-none"
          title={expanded ? "접기" : "펼치기"}
        >
          {expanded ? "▲" : "▼"}
        </button>
      )}
    </div>
  );
}

// 말풍선 아래 보조 액션 버튼 공통 스타일 (작고 은은하게)
const ACTION_BTN =
  "flex items-center gap-1 px-1.5 py-0.5 text-xs rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors";

// 질문 복사 — 클릭 시 클립보드에 쓰고 잠시 '복사됨' 으로 표시
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      title="질문 복사"
      className={ACTION_BTN}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // 클립보드 접근 실패(비보안 컨텍스트 등) 무시 — 앱은 HTTPS 라 정상 동작
        }
      }}
    >
      {copied ? (
        <>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          복사됨
        </>
      ) : (
        <>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
          복사
        </>
      )}
    </button>
  );
}

// 질문 말풍선 + 호버/포커스 시 나타나는 액션(복사·다시 묻기).
// '다시 묻기' 는 자동 전송하지 않고 입력창에 내용만 채운다(편집 후 직접 전송).
function UserBubble({ text, onReask }: { text: string; onReask: (t: string) => void }) {
  return (
    <div className="group flex flex-col items-end gap-1 max-w-[80%]">
      <div className="rounded-lg bg-blue-500/15 dark:bg-blue-600/30 border border-blue-500/40 px-3 py-2 text-sm whitespace-pre-wrap break-words">
        {text}
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
        <CopyButton text={text} />
        <button
          type="button"
          title="이 질문을 입력창에 채우기"
          className={ACTION_BTN}
          onClick={() => onReask(text)}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
          다시 묻기
        </button>
      </div>
    </div>
  );
}

function AssistantBlock({ msg }: { msg: Message }) {
  // 채택 이유(키워드 매칭)용 — 실제 search_videos 에 넘어간 질의어
  const searchQuery = String(
    msg.toolCalls.find((c) => c.name === "search_videos")?.args?.query ?? ""
  );
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
        <div key={`r-empty-${i}`} className="text-xs text-muted-foreground font-mono text-center">
          ↳ {r.name} → 0 items
        </div>
      ))}
      {allHits.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs text-muted-foreground font-mono text-center">↳ {allHits.length} items</div>
          <div className="grid gap-2 grid-cols-[repeat(auto-fill,minmax(440px,1fr))]">
            {allHits.map((h) => (
              <VideoCard key={h.opus} hit={h} query={searchQuery} />
            ))}
          </div>
        </div>
      )}
      {msg.text && (
        <div className="whitespace-pre-wrap text-foreground leading-relaxed text-center">
          {msg.text}
        </div>
      )}
      {msg.status === "streaming" && (
        <div className="text-xs text-muted-foreground animate-pulse text-center">생성 중…</div>
      )}
      {msg.status === "aborted" && (
        <div className="text-xs text-amber-600 dark:text-amber-400 text-center">⏹ 중단됨</div>
      )}
      {msg.status === "error" && (
        <div className="text-xs text-red-600 dark:text-red-400 text-center">⚠ {msg.error}</div>
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

  // 질문 말풍선의 '다시 묻기' — 입력창에 내용을 채우고 포커스(자동 전송 X, 편집 가능)
  const fillInput = useCallback((text: string) => {
    setInput(text);
    const ta = taRef.current;
    if (!ta) return;
    ta.focus();
    // 값이 DOM 에 반영된 다음 프레임에 높이 재계산 + 커서를 끝으로
    requestAnimationFrame(() => {
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
      const len = ta.value.length;
      ta.setSelectionRange(len, len);
    });
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
            ? "border border-border bg-card px-4 pt-3.5 pb-2 shadow-lg shadow-black/5 dark:shadow-black/40"
            : "border border-border bg-card px-3 pt-3 pb-1.5 shadow-sm dark:shadow-none")
        }
      >
        {/* 상단: 입력 (Enter 전송 / Shift+Enter 줄바꿈, 내용에 따라 높이 자동 확장) */}
        <textarea
          ref={taRef}
          rows={1}
          className={
            "w-full bg-transparent outline-none resize-none text-foreground placeholder:text-muted-foreground " +
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
              className="rounded-full border border-border bg-muted px-2.5 py-1 text-xs text-foreground hover:bg-accent"
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
                <div className="absolute bottom-full left-0 mb-2 z-20 w-48 rounded-lg border border-border bg-popover p-2.5 shadow-xl space-y-2">
                  <div className="text-xs font-semibold text-muted-foreground">개수</div>
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
                            ? "border-blue-500 bg-blue-500/20 text-blue-700 dark:text-blue-200"
                            : "border-border text-foreground hover:bg-accent")
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
                      className="w-20 px-2 py-1 text-xs rounded-md bg-background border border-input outline-none focus:border-blue-500 text-foreground"
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
                      className="px-2 py-1 text-xs rounded-md bg-muted hover:bg-accent text-foreground"
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
              className="rounded-full border border-border bg-muted px-2.5 py-1 text-xs text-foreground hover:bg-accent"
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
                <div className="absolute bottom-full left-0 mb-2 z-20 w-36 rounded-lg border border-border bg-popover p-2.5 shadow-xl space-y-2">
                  <div className="text-xs font-semibold text-muted-foreground">종류</div>
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
                            ? "border-blue-500 bg-blue-500/20 text-blue-700 dark:text-blue-200"
                            : "border-border text-foreground hover:bg-accent")
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
              className="ml-auto shrink-0 flex items-center justify-center text-red-500 hover:text-red-600 dark:text-red-400 dark:hover:text-red-300"
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
              className="ml-auto shrink-0 flex items-center justify-center text-muted-foreground hover:text-blue-500 disabled:opacity-30"
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
          <h2 className="text-3xl sm:text-4xl font-semibold text-foreground">무엇을 찾을까요?</h2>
          {renderForm(true)}
          <div className="flex flex-wrap gap-2 justify-center max-w-[760px]">
            {suggestions.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => send(q)}
                className="px-3 py-1.5 text-sm rounded-full border border-border bg-card text-muted-foreground hover:bg-accent hover:text-foreground"
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
                  <UserBubble text={m.text} onReask={fillInput} />
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
