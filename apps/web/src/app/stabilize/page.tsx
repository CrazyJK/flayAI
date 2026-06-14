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

  // 전/후 동시 재생용
  const origRef = useRef<HTMLVideoElement>(null);
  const stabRef = useRef<HTMLVideoElement>(null);
  const [syncPlaying, setSyncPlaying] = useState(false);

  // 인물 모드 주인공 지정(클릭)
  const pickVideoRef = useRef<HTMLVideoElement>(null);
  const [subject, setSubject] = useState<{ t: number; x: number; y: number } | null>(null);
  const [pickMode, setPickMode] = useState(false);

  function onPick(f: File | null) {
    setFile(f);
    setSubject(null);
    setPickMode(false);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(f ? URL.createObjectURL(f) : null);
  }

  function onPickClick(e: React.MouseEvent<HTMLDivElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const x = Math.min(Math.max((e.clientX - box.left) / box.width, 0), 1);
    const y = Math.min(Math.max((e.clientY - box.top) / box.height, 0), 1);
    setSubject({ t: pickVideoRef.current?.currentTime ?? 0, x, y });
    setPickMode(false);
  }

  const loadJobs = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/stabilize/jobs`);
      if (r.ok) setJobs((await r.json()).jobs ?? []);
    } catch {
      /* 무시 */
    }
  }, []);

  // 마운트 시 잡 목록
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

  // 현재 잡 폴링 (종료 상태까지)
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
    setSyncPlaying(false);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("mode", mode);
      fd.append("strength", strength);
      if (mode === "person" && subject) fd.append("subject", JSON.stringify(subject));
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

  // --- 전/후 동시 재생 ---
  function syncToggle() {
    const o = origRef.current;
    const s = stabRef.current;
    if (!o || !s) return;
    if (syncPlaying) {
      o.pause();
      s.pause();
      setSyncPlaying(false);
    } else {
      s.currentTime = o.currentTime; // 안정화본을 원본 위치에 맞춤
      s.muted = true; // 오디오 중복 방지(원본만 소리)
      o.play().catch(() => {});
      s.play().catch(() => {});
      setSyncPlaying(true);
    }
  }

  function syncRestart() {
    const o = origRef.current;
    const s = stabRef.current;
    if (!o || !s) return;
    o.currentTime = 0;
    s.currentTime = 0;
    s.muted = true;
    o.play().catch(() => {});
    s.play().catch(() => {});
    setSyncPlaying(true);
  }

  // 원본을 마스터로 — 재생 중 드리프트 보정 + 원본 일시정지/종료 시 동기화
  function onOrigTime() {
    if (!syncPlaying) return;
    const o = origRef.current;
    const s = stabRef.current;
    if (o && s && Math.abs(s.currentTime - o.currentTime) > 0.3) s.currentTime = o.currentTime;
  }
  function onOrigPause() {
    if (syncPlaying) stabRef.current?.pause();
  }
  function onOrigPlay() {
    if (syncPlaying) stabRef.current?.play().catch(() => {});
  }

  const running = status && !TERMINAL.has(status.status);
  const done = status?.status === "done";
  const resultUrl = jobId ? `${API_BASE}/api/stabilize/jobs/${jobId}/result` : null;
  const metrics = status?.outputs?.[0]?.metrics;
  const canCompare = done && !!resultUrl && !!previewUrl;

  return (
    <div className="relative flex-1 flex flex-col">
      <AppHeader active="stabilize" />

      <div className="mx-auto w-full max-w-[1600px] px-4 py-4">
        {/* 가로 모니터: 좌측 옵션 사이드바 + 우측 넓은 비교 영역. 좁은 화면에선 세로 스택. */}
        <div className="grid gap-4 lg:grid-cols-[minmax(340px,380px)_1fr] items-start">
          {/* ===== 사이드바: 업로드 + 옵션 + 최근 잡 ===== */}
          <div className="space-y-4 lg:sticky lg:top-4">
            <section className="rounded-lg border border-border bg-card p-4 space-y-4">
              <div className="space-y-2">
                <label className="block text-sm font-medium">영상 업로드</label>
                <input
                  type="file"
                  accept="video/mp4,video/*"
                  onChange={(e) => onPick(e.target.files?.[0] ?? null)}
                  className="block w-full text-sm file:mr-3 file:px-3 file:py-1.5 file:rounded file:border-0 file:bg-primary file:text-primary-foreground file:text-sm hover:file:bg-primary/90"
                />
                {file && (
                  <div className="flex items-center gap-3">
                    {previewUrl && (
                      <video
                        src={previewUrl}
                        className="w-16 rounded border border-border bg-black aspect-[9/16] object-cover shrink-0"
                        muted
                      />
                    )}
                    <p className="text-xs text-muted-foreground break-all">
                      {file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB
                    </p>
                  </div>
                )}
              </div>

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
                    onClick={() => setMode("person")}
                    className={`px-3 py-1.5 rounded text-sm ${
                      mode === "person" ? "bg-primary text-primary-foreground" : "bg-muted"
                    }`}
                  >
                    인물 고정
                  </button>
                </div>
                <p className="text-xs text-muted-foreground">
                  {mode === "background"
                    ? "배경(문·벽 등)을 기준으로 카메라 흔들림을 제거합니다."
                    : "지정한 인물(주인공)을 화면에 고정합니다. 우측에서 주인공을 클릭해 지정하세요."}
                </p>
              </div>

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

              <div className="space-y-2">
                <button
                  onClick={submit}
                  disabled={!file || submitting || !!running}
                  className="w-full px-4 py-2 rounded text-sm bg-primary hover:bg-primary/90 text-primary-foreground disabled:bg-muted disabled:text-muted-foreground"
                >
                  {submitting ? "업로드 중…" : running ? "처리 중…" : "안정화 시작"}
                </button>
                <p className="text-xs text-muted-foreground">
                  결과는 자르지 않고 캔버스를 확장합니다(검은 여백 허용).
                </p>
              </div>
              {err && <p className="text-sm text-destructive whitespace-pre-wrap">{err}</p>}
            </section>

            {jobs.length > 0 && (
              <section className="rounded-lg border border-border bg-card p-4">
                <h2 className="text-sm font-medium mb-2">최근 잡</h2>
                <ul className="divide-y divide-border">
                  {jobs.map((j) => (
                    <li
                      key={j.job_id}
                      className={`flex items-center gap-2 py-1.5 text-xs ${
                        j.job_id === jobId ? "text-foreground" : ""
                      }`}
                    >
                      <button
                        onClick={() => {
                          setSyncPlaying(false);
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

          {/* ===== 메인: 진행 / 결과 비교 / 주인공 지정 ===== */}
          <div className="min-w-0">
            {!status && mode === "person" && previewUrl ? (
              <section className="rounded-lg border border-border bg-card p-4 space-y-3">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <h2 className="text-sm font-medium">주인공 지정</h2>
                  <button
                    onClick={() => setPickMode((v) => !v)}
                    className={`px-3 py-1.5 rounded text-sm ${
                      pickMode ? "bg-primary text-primary-foreground" : "bg-muted"
                    }`}
                  >
                    {pickMode ? "인물을 클릭…" : subject ? "다시 지정" : "주인공 클릭 지정"}
                  </button>
                </div>
                <p className="text-xs text-muted-foreground">
                  영상을 원하는 장면에서 멈춘 뒤 “주인공 클릭 지정”을 누르고 인물을 클릭하세요.
                  미지정 시 화면 중앙의 인물을 자동 추적합니다.
                </p>
                <div className="relative mx-auto h-[62vh] aspect-[9/16] bg-black rounded overflow-hidden">
                  <video
                    ref={pickVideoRef}
                    src={previewUrl}
                    controls
                    className="w-full h-full object-cover"
                  />
                  {pickMode && (
                    <div
                      className="absolute inset-0 cursor-crosshair"
                      onClick={onPickClick}
                      aria-label="주인공 클릭"
                    />
                  )}
                  {subject && (
                    <div
                      className="absolute h-5 w-5 -ml-2.5 -mt-2.5 rounded-full border-2 border-success bg-success/30 pointer-events-none"
                      style={{ left: `${subject.x * 100}%`, top: `${subject.y * 100}%` }}
                    />
                  )}
                </div>
                {subject && (
                  <p className="text-xs text-muted-foreground">
                    지정됨 · t={subject.t.toFixed(1)}s ({(subject.x * 100).toFixed(0)}%,{" "}
                    {(subject.y * 100).toFixed(0)}%)
                    <button
                      onClick={() => setSubject(null)}
                      className="ml-2 hover:text-destructive"
                    >
                      지우기
                    </button>
                  </p>
                )}
              </section>
            ) : !status ? (
              <div className="rounded-lg border border-dashed border-border bg-card/50 p-10 text-center text-sm text-muted-foreground">
                영상을 올리고 <span className="text-foreground">안정화 시작</span>을 누르면
                여기에 진행과 결과(전/후 비교)가 표시됩니다.
              </div>
            ) : (
              <section className="rounded-lg border border-border bg-card p-4 space-y-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
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
                  {status.input && (
                    <span className="text-xs text-muted-foreground">
                      입력 {status.input.width}×{status.input.height} · {status.input.fps}fps ·{" "}
                      {status.input.duration}s · {status.input.codec}
                    </span>
                  )}
                  {running && (
                    <button onClick={cancelJob} className="px-2 py-1 rounded text-xs bg-muted">
                      취소
                    </button>
                  )}
                </div>

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

                {done && resultUrl && (
                  <div className="space-y-3">
                    {/* 비교 컨트롤 */}
                    <div className="flex items-center gap-2 flex-wrap">
                      {canCompare && (
                        <>
                          <button
                            onClick={syncToggle}
                            className="px-3 py-1.5 rounded text-sm bg-primary text-primary-foreground hover:bg-primary/90"
                          >
                            {syncPlaying ? "⏸ 동시 정지" : "▶ 동시 재생"}
                          </button>
                          <button
                            onClick={syncRestart}
                            className="px-3 py-1.5 rounded text-sm bg-muted hover:bg-muted/80"
                          >
                            ↺ 처음부터
                          </button>
                          <span className="text-xs text-muted-foreground">
                            (원본 기준으로 동기화 · 안정화본 음소거)
                          </span>
                        </>
                      )}
                      <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
                        {metrics?.canvas_expand_w && (
                          <span>
                            캔버스 ×{metrics.canvas_expand_w}/{metrics.canvas_expand_h}
                          </span>
                        )}
                        {metrics?.smoothing && <span>smoothing {metrics.smoothing}</span>}
                        <a
                          href={resultUrl}
                          download
                          className="px-3 py-1.5 rounded bg-primary text-primary-foreground hover:bg-primary/90"
                        >
                          다운로드
                        </a>
                      </div>
                    </div>

                    {/* 전/후 — 9:16 세로 영상 2개 나란히, 뷰포트 높이에 맞춤 */}
                    <div className="grid grid-cols-2 gap-3">
                      {previewUrl && (
                        <figure className="space-y-1 min-w-0">
                          <figcaption className="text-xs text-muted-foreground">원본</figcaption>
                          <video
                            ref={origRef}
                            src={previewUrl}
                            controls
                            onTimeUpdate={onOrigTime}
                            onPause={onOrigPause}
                            onPlay={onOrigPlay}
                            onEnded={() => setSyncPlaying(false)}
                            className="w-full h-[68vh] object-contain rounded border border-border bg-black"
                          />
                        </figure>
                      )}
                      <figure className={`space-y-1 min-w-0 ${previewUrl ? "" : "col-span-2"}`}>
                        <figcaption className="text-xs text-success">안정화</figcaption>
                        <video
                          ref={stabRef}
                          src={resultUrl}
                          controls
                          className="w-full h-[68vh] object-contain rounded border border-border bg-black"
                        />
                      </figure>
                    </div>
                  </div>
                )}
              </section>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
