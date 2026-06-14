"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AppHeader from "../_components/AppHeader";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ai.kamoru.jk:8000";

// 잡 처리 단계(진행바). vidstab 엔진 기준.
const STAGES = ["decode", "detect", "transform", "encode"] as const;

// 안정화 강도 프리셋 — 백엔드 smoothing_presets 와 대응(docs/video-stabilization-plan.md §9).
const STRENGTHS = [
  { key: "dejitter", label: "흔들림만", desc: "이동·추종은 보존하고 떨림만 제거 (트래블 샷)" },
  { key: "smooth", label: "부분 고정", desc: "떨림 + 느린 움직임 일부 정리 (기본)" },
  { key: "lock", label: "완전 고정", desc: "느린 드리프트까지 평탄화 (정지형 구간)" },
  { key: "auto", label: "자동", desc: "현재는 부분 고정과 동일 (자동 판정 예정)" },
] as const;

type Metrics = {
  smoothing?: number;
  canvas_expand_w?: number;
  canvas_expand_h?: number;
  output_wh?: number[];
  metrics_error?: string;
};
type JobOutput = { variant: string; file: string; metrics?: Metrics };
type JobStatus = {
  job_id: string;
  status: "queued" | "running" | "done" | "failed" | "canceled";
  mode: string;
  strength: string;
  stage?: string | null;
  progress?: number;
  input?: { width: number; height: number; fps: number; codec: string; duration: number } | null;
  outputs?: JobOutput[];
  error?: string | null;
  note?: string | null;
  created_at?: number;
};

const TERMINAL = new Set(["done", "failed", "canceled"]);

export default function StabilizePage() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [mode, setMode] = useState<"background" | "person">("background");
  const [strength, setStrength] = useState<string>("smooth");

  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  // --- 원본 미리보기 (방금 올린 파일에 한해 전/후 비교 가능) ---
  function onPick(f: File | null) {
    setFile(f);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(f ? URL.createObjectURL(f) : null);
  }

  const loadJobs = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/stabilize/jobs`);
      if (r.ok) setJobs((await r.json()).jobs ?? []);
    } catch {
      /* 무시 */
    }
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await fetch(`${API_BASE}/api/stabilize/jobs`);
        if (alive && r.ok) setJobs((await r.json()).jobs ?? []);
      } catch {
        /* 무시 */
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // --- 현재 잡 폴링 (종료 상태까지) ---
  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const r = await fetch(`${API_BASE}/api/stabilize/jobs/${jobId}`);
        if (r.ok) {
          const s: JobStatus = await r.json();
          if (!alive) return;
          setStatus(s);
          if (!TERMINAL.has(s.status)) {
            timer = setTimeout(tick, 1500);
          } else {
            loadJobs();
          }
          return;
        }
      } catch {
        /* 재시도 */
      }
      if (alive) timer = setTimeout(tick, 2500);
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [jobId, loadJobs]);

  async function submit() {
    if (!file || submitting) return;
    setSubmitting(true);
    setErr(null);
    setStatus(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("mode", mode);
      fd.append("strength", strength);
      const r = await fetch(`${API_BASE}/api/stabilize/jobs`, { method: "POST", body: fd });
      if (!r.ok) throw new Error(await r.text());
      const j = await r.json();
      setJobId(j.job_id);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function cancelJob() {
    if (!jobId) return;
    await fetch(`${API_BASE}/api/stabilize/jobs/${jobId}/cancel`, { method: "POST" }).catch(() => {});
  }

  async function removeJob(id: string) {
    await fetch(`${API_BASE}/api/stabilize/jobs/${id}`, { method: "DELETE" }).catch(() => {});
    if (id === jobId) {
      setJobId(null);
      setStatus(null);
    }
    loadJobs();
  }

  const running = status && !TERMINAL.has(status.status);
  const done = status?.status === "done";
  const resultUrl = jobId ? `${API_BASE}/api/stabilize/jobs/${jobId}/result` : null;
  const metrics = status?.outputs?.[0]?.metrics;

  return (
    <div className="relative flex-1 flex flex-col">
      <AppHeader active="stabilize" />

      <div className="mx-auto w-full max-w-[900px] px-4 py-4 space-y-4">
        {/* ---- 업로드 + 옵션 ---- */}
        <section className="rounded-lg border border-border bg-card p-4 space-y-4">
          <div className="flex items-start gap-4">
            <div className="flex-1 space-y-3">
              <label className="block text-sm font-medium">영상 업로드</label>
              <input
                ref={fileRef}
                type="file"
                accept="video/mp4,video/*"
                onChange={(e) => onPick(e.target.files?.[0] ?? null)}
                className="block w-full text-sm file:mr-3 file:px-3 file:py-1.5 file:rounded file:border-0 file:bg-primary file:text-primary-foreground file:text-sm hover:file:bg-primary/90"
              />
              {file && (
                <p className="text-xs text-muted-foreground">
                  {file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB
                </p>
              )}
            </div>
            {previewUrl && (
              <video
                src={previewUrl}
                className="w-28 rounded border border-border bg-black aspect-[9/16] object-cover"
                muted
              />
            )}
          </div>

          {/* 기준 */}
          <div className="space-y-1.5">
            <span className="text-sm font-medium">안정화 기준</span>
            <div className="flex gap-2">
              <button
                onClick={() => setMode("background")}
                className={`px-3 py-1.5 rounded text-sm ${
                  mode === "background" ? "bg-primary text-primary-foreground" : "bg-muted"
                }`}
              >
                배경 고정
              </button>
              <button
                disabled
                title="SAM2 클릭 지정 연동 예정"
                className="px-3 py-1.5 rounded text-sm bg-muted text-muted-foreground opacity-60 cursor-not-allowed"
              >
                인물 고정 · 준비중
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              배경(문·벽 등)을 기준으로 카메라 흔들림을 제거합니다. 인물 기준은 곧 추가됩니다.
            </p>
          </div>

          {/* 강도 */}
          <div className="space-y-1.5">
            <span className="text-sm font-medium">고정 강도</span>
            <div className="flex flex-wrap gap-2">
              {STRENGTHS.map((s) => (
                <button
                  key={s.key}
                  onClick={() => setStrength(s.key)}
                  className={`px-3 py-1.5 rounded text-sm ${
                    strength === s.key ? "bg-primary text-primary-foreground" : "bg-muted"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {STRENGTHS.find((s) => s.key === strength)?.desc}
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={submit}
              disabled={!file || submitting || !!running}
              className="px-4 py-2 rounded text-sm bg-primary hover:bg-primary/90 text-primary-foreground disabled:bg-muted disabled:text-muted-foreground"
            >
              {submitting ? "업로드 중…" : running ? "처리 중…" : "안정화 시작"}
            </button>
            <span className="text-xs text-muted-foreground">
              결과는 자르지 않고 캔버스를 확장합니다(검은 여백 허용).
            </span>
          </div>
          {err && <p className="text-sm text-destructive whitespace-pre-wrap">{err}</p>}
        </section>

        {/* ---- 진행 / 결과 ---- */}
        {status && (
          <section className="rounded-lg border border-border bg-card p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium">
                잡 <span className="font-mono text-xs text-muted-foreground">{status.job_id}</span>
                <span
                  className={`ml-2 text-xs ${
                    done
                      ? "text-success"
                      : status.status === "failed"
                        ? "text-destructive"
                        : "text-muted-foreground"
                  }`}
                >
                  {status.status}
                </span>
              </h2>
              {running && (
                <button onClick={cancelJob} className="px-2 py-1 rounded text-xs bg-muted">
                  취소
                </button>
              )}
            </div>

            {status.input && (
              <p className="text-xs text-muted-foreground">
                입력 {status.input.width}×{status.input.height} · {status.input.fps}fps ·{" "}
                {status.input.duration}s · {status.input.codec}
              </p>
            )}

            {/* 진행바 */}
            {running && (
              <div className="space-y-1.5">
                <div className="h-2 rounded bg-muted overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{ width: `${status.progress ?? 0}%` }}
                  />
                </div>
                <div className="flex gap-1.5 text-[11px] text-muted-foreground">
                  {STAGES.map((st) => (
                    <span
                      key={st}
                      className={status.stage === st ? "text-foreground font-medium" : ""}
                    >
                      {st}
                    </span>
                  ))}
                  <span className="ml-auto tabular-nums">{status.progress ?? 0}%</span>
                </div>
              </div>
            )}

            {status.note && <p className="text-xs text-muted-foreground">참고: {status.note}</p>}
            {status.status === "failed" && (
              <p className="text-sm text-destructive whitespace-pre-wrap">{status.error}</p>
            )}

            {/* 결과: 전/후 비교 */}
            {done && resultUrl && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  {previewUrl && (
                    <figure className="space-y-1">
                      <figcaption className="text-xs text-muted-foreground">원본</figcaption>
                      <video
                        src={previewUrl}
                        controls
                        className="w-full rounded border border-border bg-black"
                      />
                    </figure>
                  )}
                  <figure className="space-y-1">
                    <figcaption className="text-xs text-success">안정화</figcaption>
                    <video
                      src={resultUrl}
                      controls
                      className="w-full rounded border border-border bg-black"
                    />
                  </figure>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                  {metrics?.canvas_expand_w && (
                    <span>
                      캔버스 확장 가로 ×{metrics.canvas_expand_w} · 세로 ×{metrics.canvas_expand_h}
                    </span>
                  )}
                  {metrics?.smoothing && <span>smoothing {metrics.smoothing}</span>}
                  <a
                    href={resultUrl}
                    download
                    className="ml-auto px-3 py-1.5 rounded bg-primary text-primary-foreground hover:bg-primary/90"
                  >
                    다운로드
                  </a>
                </div>
              </div>
            )}
          </section>
        )}

        {/* ---- 최근 잡 ---- */}
        {jobs.length > 0 && (
          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="text-sm font-medium mb-2">최근 잡</h2>
            <ul className="divide-y divide-border">
              {jobs.map((j) => (
                <li key={j.job_id} className="flex items-center gap-2 py-1.5 text-xs">
                  <button
                    onClick={() => {
                      setJobId(j.job_id);
                      setStatus(j);
                    }}
                    className="font-mono text-muted-foreground hover:text-foreground"
                  >
                    {j.job_id.slice(0, 8)}
                  </button>
                  <span className="text-muted-foreground">
                    {j.mode}/{j.strength}
                  </span>
                  <span
                    className={
                      j.status === "done"
                        ? "text-success"
                        : j.status === "failed"
                          ? "text-destructive"
                          : "text-muted-foreground"
                    }
                  >
                    {j.status}
                  </span>
                  <button
                    onClick={() => removeJob(j.job_id)}
                    className="ml-auto text-muted-foreground hover:text-destructive"
                  >
                    삭제
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
