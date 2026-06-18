"use client";

import { useCallback, useEffect, useState } from "react";
import AppHeader from "../_components/AppHeader";
import SectionCard from "../_components/SectionCard";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ai.kamoru.jk:8000";

// 자막 생성 요청(큐) — /api/subtitle/requests
type SubtitleJob = {
  id: number;
  opus: string;
  task: string; // generate | resync | both
  status: string; // queued | running | done | failed | skipped | canceled
  stage?: string | null;
  progress?: number | null;
  result_path?: string | null;
  error?: string | null;
  note?: string | null;
};

const SUB_TASK_LABEL: Record<string, string> = {
  generate: "생성",
  resync: "싱크수정",
  both: "자동",
};

const SUB_STATUS_STYLE: Record<string, string> = {
  queued: "bg-muted text-muted-foreground border border-border",
  running: "bg-blue-500/15 text-blue-400 border border-blue-500/30",
  done: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
  failed: "bg-red-500/15 text-red-400 border border-red-500/30",
  skipped: "bg-amber-500/15 text-amber-400 border border-amber-500/30",
  canceled: "bg-muted text-muted-foreground border border-border",
};

function SubStatusChip({ j }: { j: SubtitleJob }) {
  const cls =
    "text-xs px-1.5 py-0.5 rounded font-mono whitespace-nowrap " +
    (SUB_STATUS_STYLE[j.status] ?? "bg-muted text-muted-foreground");
  const label = j.status === "running" ? `${j.stage ?? "처리"} ${j.progress ?? 0}%` : j.status;
  return <span className={cls}>{label}</span>;
}

// 자막 신청 폼 + 큐/이력 — opus 신청 → 큐 → 야간 드레인(또는 지금 처리)
function SubtitleSection() {
  const [jobs, setJobs] = useState<SubtitleJob[]>([]);
  const [opus, setOpus] = useState("");
  const [task, setTask] = useState("generate");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/subtitle/requests?limit=50`);
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

  async function submit() {
    const op = opus.trim();
    if (!op) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch(`${API_BASE}/api/subtitle/requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ opus: op, task }),
      });
      const body = (await r.json().catch(() => ({}))) as {
        detail?: string;
        created?: boolean;
      };
      if (!r.ok) throw new Error(body.detail ?? `HTTP ${r.status}`);
      setMsg(body.created === false ? `이미 대기 중: ${op}` : `신청됨: ${op}`);
      setOpus("");
      void loadJobs();
    } catch (e) {
      setMsg(`실패: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function drainNow() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await fetch(`${API_BASE}/api/subtitle/drain`, { method: "POST" });
      const body = (await r.json().catch(() => ({}))) as { detail?: string; pending?: number };
      if (!r.ok) throw new Error(body.detail ?? `HTTP ${r.status}`);
      setMsg(`드레인 시작 — 대기 ${body.pending ?? "?"}건 처리 중`);
      void loadJobs();
    } catch (e) {
      setMsg(`실패: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    try {
      await fetch(`${API_BASE}/api/subtitle/requests/${id}`, { method: "DELETE" });
      void loadJobs();
    } catch {
      /* 무시 */
    }
  }

  const pending = jobs.filter((j) => j.status === "queued" || j.status === "running").length;

  return (
    <SectionCard title="신청 큐" badge={pending ? `대기 ${pending}` : undefined}>
      {/* 신청 폼 */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <input
          value={opus}
          onChange={(e) => setOpus(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void submit();
          }}
          placeholder="opus 입력 (예: FSDSS-951)"
          className="px-2.5 py-1.5 text-sm rounded border border-border bg-background font-mono w-56"
        />
        <select
          value={task}
          onChange={(e) => setTask(e.target.value)}
          className="px-2 py-1.5 text-sm rounded border border-border bg-background"
        >
          <option value="generate">생성 (자막 없는 영상)</option>
          <option value="resync">싱크 수정 (기존 자막)</option>
          <option value="both">자동 (있으면 싱크, 없으면 생성)</option>
        </select>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy || !opus.trim()}
          className="px-3 py-1.5 text-sm rounded border border-border bg-accent hover:bg-accent/80 disabled:opacity-50"
        >
          신청
        </button>
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

      {/* 큐/이력 */}
      {jobs.length === 0 ? (
        <p className="text-sm text-muted-foreground">신청 내역이 없습니다.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr className="text-left border-b border-border">
                <th className="py-1 pr-3">opus</th>
                <th className="pr-3">작업</th>
                <th className="pr-3">상태</th>
                <th className="pr-3">비고</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="border-b border-border/40">
                  <td className="py-1 pr-3 font-mono">{j.opus}</td>
                  <td className="pr-3">{SUB_TASK_LABEL[j.task] ?? j.task}</td>
                  <td className="pr-3">
                    <SubStatusChip j={j} />
                  </td>
                  <td
                    className="pr-3 text-xs text-muted-foreground max-w-[26rem] truncate"
                    title={j.note ?? j.error ?? ""}
                  >
                    {j.note ?? j.error ?? ""}
                  </td>
                  <td className="text-right">
                    {j.status !== "running" && (
                      <button
                        type="button"
                        onClick={() => void remove(j.id)}
                        className="text-xs text-muted-foreground hover:text-red-400"
                      >
                        삭제
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

export default function SubtitlePage() {
  return (
    <main className="flex-1 flex flex-col w-full min-h-0">
      <AppHeader active="subtitle" />
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
        <div className="mx-auto w-full max-w-[1100px] space-y-4">
          <div>
            <h2 className="text-lg font-semibold">자막 생성</h2>
            <p className="text-sm text-muted-foreground mt-1">
              영상 음성을 한국어 자막(.srt/.smi)으로 생성하거나, 기존 자막의 싱크를 맞춥니다. opus
              로 신청하면 야간 배치가 처리합니다(또는 [지금 처리]). 산출물은 영상 옆 사이드카
              파일입니다.
            </p>
          </div>
          <SubtitleSection />
        </div>
      </div>
    </main>
  );
}
