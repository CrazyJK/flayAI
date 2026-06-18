"use client";

import { useCallback, useEffect, useState } from "react";
import AppHeader from "../_components/AppHeader";
import SectionCard from "../_components/SectionCard";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ai.kamoru.jk:8000";

// 자막 큐 잡 — /api/subtitle/requests
type SubtitleJob = {
  id: number;
  opus: string;
  task: string; // generate | resync | both
  status: string; // queued | running | done | failed | skipped | canceled
  stage?: string | null;
  progress?: number | null;
  note?: string | null;
  error?: string | null;
};

// 무자막 후보 — /api/subtitle/candidates
type Candidate = {
  opus: string;
  title: string;
  studio?: string | null;
  year?: number | null;
  play?: number | null;
  like_count?: number | null;
  has_caption?: boolean;
};

// 자막 보유(resync 대상) — /api/subtitle/subbed
type Subbed = {
  opus: string;
  title: string;
  fmt: string; // srt | smi
  n_pairs?: number | null;
  resync_status?: string | null; // done | skipped | null
  resync_note?: string | null;
};

const SUB_TASK_LABEL: Record<string, string> = { generate: "생성", resync: "싱크수정", both: "자동" };
const STAGE_LABEL: Record<string, string> = {
  start: "시작",
  transcribe: "전사",
  translate: "번역",
  align: "정렬",
  write: "작성",
};
const SUB_STATUS_STYLE: Record<string, string> = {
  queued: "bg-muted text-muted-foreground border border-border",
  running: "bg-blue-500/15 text-blue-400 border border-blue-500/30",
  done: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
  failed: "bg-red-500/15 text-red-400 border border-red-500/30",
  skipped: "bg-amber-500/15 text-amber-400 border border-amber-500/30",
  canceled: "bg-muted text-muted-foreground border border-border",
};

const fmtNum = (n: number | null | undefined) => (n ?? 0).toLocaleString("ko-KR");
const posterUrl = (opus: string) => `${API_BASE}/static/posters/${encodeURIComponent(opus)}`;
const pctFromNote = (note?: string | null): string | null => {
  const m = note ? note.match(/(\d+)%/) : null;
  return m ? `${m[1]}%` : null;
};

function PosterThumb({ opus }: { opus: string }) {
  const [ok, setOk] = useState(true);
  return (
    <div className="w-9 h-12 rounded bg-muted flex items-center justify-center shrink-0 overflow-hidden">
      {ok ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={posterUrl(opus)}
          alt=""
          className="w-full h-full object-cover"
          onError={() => setOk(false)}
        />
      ) : (
        <span className="text-muted-foreground text-xs">▦</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 새 자막 생성 — 무자막 목록에서 선택
// ---------------------------------------------------------------------------

const SORTS = [
  { key: "like", label: "인기순" },
  { key: "play", label: "재생순" },
  { key: "recent", label: "최신순" },
  { key: "opus", label: "opus순" },
];

function GenerateSection({ onSubmitted }: { onSubmitted: () => void }) {
  const [items, setItems] = useState<Candidate[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState(""); // 실제 적용된 검색어
  const [sort, setSort] = useState("like");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [lastScan, setLastScan] = useState<number | null>(null);
  const PAGE = 60;

  const load = useCallback(
    async (offset: number) => {
      setLoading(true);
      try {
        const u = new URL(`${API_BASE}/api/subtitle/candidates`);
        u.searchParams.set("sort", sort);
        u.searchParams.set("limit", String(PAGE));
        u.searchParams.set("offset", String(offset));
        if (query) u.searchParams.set("q", query);
        const r = await fetch(u);
        if (!r.ok) return;
        const j = (await r.json()) as { total: number; items: Candidate[]; last_scan: number | null };
        setTotal(j.total);
        setLastScan(j.last_scan);
        setItems((prev) => (offset === 0 ? j.items : [...prev, ...j.items]));
      } finally {
        setLoading(false);
      }
    },
    [sort, query],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load(0);
  }, [load]);

  function toggle(opus: string) {
    setSel((prev) => {
      const next = new Set(prev);
      if (next.has(opus)) next.delete(opus);
      else next.add(opus);
      return next;
    });
  }

  async function submitSelected() {
    if (sel.size === 0) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch(`${API_BASE}/api/subtitle/requests/bulk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ opuses: [...sel], task: "generate" }),
      });
      const b = (await r.json().catch(() => ({}))) as { created?: number; skipped?: number };
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setMsg(`신청 ${b.created ?? 0}건 (이미 대기 ${b.skipped ?? 0})`);
      setSel(new Set());
      onSubmitted();
    } catch (e) {
      setMsg(`실패: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function submitAll() {
    if (!window.confirm(`무자막 ${fmtNum(total)}편을 모두 자막 생성 신청합니다. 계속할까요?`)) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch(`${API_BASE}/api/subtitle/enqueue-all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task: "generate", q: query || null }),
      });
      const b = (await r.json().catch(() => ({}))) as { created?: number; skipped?: number };
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setMsg(`전체 신청 ${b.created ?? 0}건 (이미 대기 ${b.skipped ?? 0})`);
      onSubmitted();
    } catch (e) {
      setMsg(`실패: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function rescan() {
    setBusy(true);
    setMsg("스캔 중…");
    try {
      const r = await fetch(`${API_BASE}/api/subtitle/scan`, { method: "POST" });
      const b = (await r.json().catch(() => ({}))) as {
        seen?: number;
        has_sub?: number;
        none?: number;
        offline?: number;
      };
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setMsg(`스캔 완료 — 무자막 ${fmtNum(b.none)} · 자막 ${fmtNum(b.has_sub)} · 오프라인 ${fmtNum(b.offline)}`);
      void load(0);
    } catch (e) {
      setMsg(`스캔 실패: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <SectionCard title="새 자막 생성" badge={`무자막 ${fmtNum(total)}편`}>
      {/* 검색·정렬·스캔 */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") setQuery(q.trim());
          }}
          placeholder="제목·배우·opus 검색 (Enter)"
          className="px-2.5 py-1.5 text-sm rounded border border-border bg-background w-64"
        />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="px-2 py-1.5 text-sm rounded border border-border bg-background"
        >
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void rescan()}
          disabled={busy}
          title="자막 유무를 디스크에서 다시 스캔(드라이브 온라인 필요)"
          className="px-2.5 py-1.5 text-xs rounded border border-border hover:bg-accent disabled:opacity-50"
        >
          ↻ 목록 스캔
        </button>
        <span className="text-xs text-muted-foreground">
          {lastScan ? `마지막 스캔 ${new Date(lastScan * 1000).toLocaleString("ko-KR")}` : "미스캔(코퍼스 기준)"}
        </span>
      </div>

      {/* 목록 */}
      <div className="border border-border/60 rounded-lg divide-y divide-border/40">
        {items.map((c) => (
          <label
            key={c.opus}
            className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-accent/30"
          >
            <input type="checkbox" checked={sel.has(c.opus)} onChange={() => toggle(c.opus)} />
            <PosterThumb opus={c.opus} />
            <div className="min-w-0 flex-1">
              <div className="font-mono text-sm text-foreground">{c.opus}</div>
              <div className="text-xs text-muted-foreground truncate">
                {c.has_caption && <span className="text-emerald-400/80">캡션 · </span>}
                {c.title || "—"}
              </div>
            </div>
            <div className="text-[11px] text-muted-foreground text-right shrink-0">
              {[c.studio, c.year].filter(Boolean).join(" · ")}
              <div>재생 {fmtNum(c.play)} · ♥ {fmtNum(c.like_count)}</div>
            </div>
          </label>
        ))}
        {items.length === 0 && !loading && (
          <p className="text-sm text-muted-foreground px-3 py-6 text-center">대상이 없습니다.</p>
        )}
      </div>

      {/* 더 보기 */}
      {items.length < total && (
        <button
          type="button"
          onClick={() => void load(items.length)}
          disabled={loading}
          className="mt-2 w-full py-1.5 text-sm rounded border border-border hover:bg-accent disabled:opacity-50"
        >
          {loading ? "불러오는 중…" : `더 보기 (${fmtNum(total - items.length)}편 남음)`}
        </button>
      )}

      {/* 신청 */}
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <button
          type="button"
          onClick={() => void submitSelected()}
          disabled={busy || sel.size === 0}
          className="px-3 py-1.5 text-sm rounded border border-blue-500/40 bg-blue-500/10 text-blue-300 hover:bg-blue-500/20 disabled:opacity-40"
        >
          선택 {sel.size}편 자막 생성 신청
        </button>
        <button
          type="button"
          onClick={() => void submitAll()}
          disabled={busy || total === 0}
          className="px-3 py-1.5 text-sm rounded border border-border hover:bg-accent disabled:opacity-50"
        >
          {query ? "검색결과" : "무자막"} 전체 신청 ({fmtNum(total)})
        </button>
        {msg && <span className="text-xs text-muted-foreground">{msg}</span>}
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// 싱크 수정(resync) — opus 입력 또는 목록
// ---------------------------------------------------------------------------

function ResyncSection({ onSubmitted }: { onSubmitted: () => void }) {
  const [items, setItems] = useState<Subbed[]>([]);
  const [total, setTotal] = useState(0);
  const [opus, setOpus] = useState("");
  const [onlyReverted, setOnlyReverted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const u = new URL(`${API_BASE}/api/subtitle/subbed`);
      u.searchParams.set("limit", "300");
      if (onlyReverted) u.searchParams.set("only_reverted", "true");
      const r = await fetch(u);
      if (!r.ok) return;
      const j = (await r.json()) as { total: number; items: Subbed[] };
      setTotal(j.total);
      setItems(j.items);
    } catch {
      /* 무시 */
    }
  }, [onlyReverted]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function requestResync(op: string) {
    const target = op.trim();
    if (!target) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch(`${API_BASE}/api/subtitle/requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ opus: target, task: "resync" }),
      });
      const b = (await r.json().catch(() => ({}))) as { detail?: string; created?: boolean };
      if (!r.ok) throw new Error(b.detail ?? `HTTP ${r.status}`);
      setMsg(b.created === false ? `이미 대기 중: ${target}` : `싱크수정 신청: ${target}`);
      onSubmitted();
    } catch (e) {
      setMsg(`실패: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function retryAllReverted() {
    if (!window.confirm("원본복원된 자막을 모두 다시 싱크 수정 신청합니다. 계속할까요?")) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch(`${API_BASE}/api/subtitle/enqueue-all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task: "resync", only_reverted: true }),
      });
      const b = (await r.json().catch(() => ({}))) as { created?: number; skipped?: number };
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setMsg(`재시도 신청 ${b.created ?? 0}건 (이미 대기 ${b.skipped ?? 0})`);
      onSubmitted();
    } catch (e) {
      setMsg(`실패: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <SectionCard title="싱크 수정" badge={`자막 보유 ${fmtNum(total)}편`}>
      {/* opus 직접 입력 + 필터 */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <input
          value={opus}
          onChange={(e) => setOpus(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void requestResync(opus);
          }}
          placeholder="opus 입력 (예: SNIS-360)"
          className="px-2.5 py-1.5 text-sm rounded border border-border bg-background font-mono w-56"
        />
        <button
          type="button"
          onClick={() => void requestResync(opus)}
          disabled={busy || !opus.trim()}
          className="px-3 py-1.5 text-sm rounded border border-border bg-accent hover:bg-accent/80 disabled:opacity-50"
        >
          싱크 수정 신청
        </button>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer ml-1">
          <input
            type="checkbox"
            checked={onlyReverted}
            onChange={(e) => setOnlyReverted(e.target.checked)}
          />
          원본복원만
        </label>
        {onlyReverted && items.length > 0 && (
          <button
            type="button"
            onClick={() => void retryAllReverted()}
            disabled={busy}
            className="px-2.5 py-1.5 text-xs rounded border border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 disabled:opacity-50"
          >
            전체 재시도
          </button>
        )}
        {msg && <span className="text-xs text-muted-foreground">{msg}</span>}
      </div>

      {/* 목록 */}
      <div className="border border-border/60 rounded-lg divide-y divide-border/40 max-h-96 overflow-y-auto">
        {items.map((s) => {
          const reverted = s.resync_status === "skipped";
          const done = s.resync_status === "done";
          const pct = pctFromNote(s.resync_note);
          return (
            <div key={s.opus} className="flex items-center gap-3 px-3 py-2">
              <div className="font-mono text-sm w-24 shrink-0">{s.opus}</div>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted/50 text-muted-foreground shrink-0">
                .{s.fmt}
              </span>
              <span className="text-xs text-muted-foreground shrink-0">{fmtNum(s.n_pairs)}쌍</span>
              <div className="min-w-0 flex-1 text-xs text-muted-foreground truncate" title={s.title}>
                {s.title}
              </div>
              <span
                className={
                  "text-[11px] px-2 py-0.5 rounded whitespace-nowrap shrink-0 " +
                  (done
                    ? "bg-emerald-500/15 text-emerald-400"
                    : reverted
                      ? "bg-amber-500/15 text-amber-400"
                      : "bg-muted text-muted-foreground")
                }
                title={s.resync_note ?? ""}
              >
                {done ? "싱크완료" : reverted ? "원본복원" : "미시도"}
                {pct ? ` · ${pct}` : ""}
              </span>
              <button
                type="button"
                onClick={() => void requestResync(s.opus)}
                disabled={busy}
                className="text-xs px-2 py-0.5 rounded border border-border hover:bg-accent disabled:opacity-50 shrink-0"
              >
                싱크 수정
              </button>
            </div>
          );
        })}
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground px-3 py-6 text-center">
            {onlyReverted ? "원본복원된 자막이 없습니다." : "자막 보유 영상이 없습니다."}
          </p>
        )}
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// 처리 큐 · 진행
// ---------------------------------------------------------------------------

function QueueSection({ jobs, onReload }: { jobs: SubtitleJob[]; onReload: () => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const pending = jobs.filter((j) => j.status === "queued" || j.status === "running").length;

  async function drainNow() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch(`${API_BASE}/api/subtitle/drain`, { method: "POST" });
      const b = (await r.json().catch(() => ({}))) as { detail?: string; pending?: number };
      if (!r.ok) throw new Error(b.detail ?? `HTTP ${r.status}`);
      setMsg(`드레인 시작 — 대기 ${b.pending ?? "?"}건 처리 중`);
      onReload();
    } catch (e) {
      setMsg(`실패: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    try {
      await fetch(`${API_BASE}/api/subtitle/requests/${id}`, { method: "DELETE" });
      onReload();
    } catch {
      /* 무시 */
    }
  }

  return (
    <SectionCard title="처리 큐 · 진행" badge={pending ? `대기 ${pending}` : undefined}>
      <div className="flex items-center gap-2 mb-3">
        <button
          type="button"
          onClick={() => void drainNow()}
          disabled={busy}
          title="큐를 지금 처리(보통은 야간 스케줄러). localhost 전용"
          className="px-3 py-1.5 text-sm rounded border border-border hover:bg-accent disabled:opacity-50"
        >
          지금 처리
        </button>
        {msg && <span className="text-xs text-muted-foreground">{msg}</span>}
      </div>

      {jobs.length === 0 ? (
        <p className="text-sm text-muted-foreground">신청 내역이 없습니다.</p>
      ) : (
        <div className="border border-border/60 rounded-lg divide-y divide-border/40 max-h-96 overflow-y-auto">
          {jobs.map((j) => {
            const running = j.status === "running";
            return (
              <div key={j.id} className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm">{j.opus}</span>
                  <span className="text-xs text-muted-foreground">{SUB_TASK_LABEL[j.task] ?? j.task}</span>
                  <span
                    className={
                      "ml-auto text-xs px-1.5 py-0.5 rounded font-mono whitespace-nowrap " +
                      (SUB_STATUS_STYLE[j.status] ?? "bg-muted text-muted-foreground")
                    }
                  >
                    {running ? `${STAGE_LABEL[j.stage ?? ""] ?? j.stage ?? "처리"} ${j.progress ?? 0}%` : j.status}
                  </span>
                  {!running && (
                    <button
                      type="button"
                      onClick={() => void remove(j.id)}
                      className="text-xs text-muted-foreground hover:text-red-400"
                    >
                      삭제
                    </button>
                  )}
                </div>
                {running && (
                  <div className="h-1.5 bg-muted rounded-full mt-2 overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all"
                      style={{ width: `${Math.min(100, j.progress ?? 0)}%` }}
                    />
                  </div>
                )}
                {(j.note || j.error) && (
                  <div
                    className="text-[11px] text-muted-foreground mt-1 truncate"
                    title={j.note ?? j.error ?? ""}
                  >
                    {j.note ?? j.error}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// 페이지 — 큐 폴링을 상위에서 소유하고 각 섹션에 갱신 콜백 전달
// ---------------------------------------------------------------------------

export default function SubtitlePage() {
  const [jobs, setJobs] = useState<SubtitleJob[]>([]);

  const loadJobs = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/subtitle/requests?limit=80`);
      if (!r.ok) return;
      const j = (await r.json()) as { jobs: SubtitleJob[] };
      setJobs(j.jobs ?? []);
    } catch {
      /* 폴링 실패는 조용히 무시 */
    }
  }, []);

  const active = jobs.some((j) => j.status === "running" || j.status === "queued");
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadJobs();
    const ms = active ? 2000 : 6000;
    const t = setInterval(() => {
      if (!document.hidden) void loadJobs();
    }, ms);
    return () => clearInterval(t);
  }, [loadJobs, active]);

  return (
    <main className="flex-1 flex flex-col w-full min-h-0">
      <AppHeader active="subtitle" />
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
        <div className="mx-auto w-full max-w-[1100px] space-y-4">
          <div>
            <h2 className="text-lg font-semibold">자막 생성</h2>
            <p className="text-sm text-muted-foreground mt-1">
              무자막 영상은 목록에서 골라 신청하고, 기존 자막은 opus 입력 또는 목록에서 싱크를
              맞춥니다. 신청분은 야간 배치가 처리하며(또는 [지금 처리]), 산출물은 영상 옆 사이드카
              자막(.srt/.smi)입니다.
            </p>
          </div>
          <GenerateSection onSubmitted={() => void loadJobs()} />
          <ResyncSection onSubmitted={() => void loadJobs()} />
          <QueueSection jobs={jobs} onReload={() => void loadJobs()} />
        </div>
      </div>
    </main>
  );
}
