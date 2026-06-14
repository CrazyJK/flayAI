"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AppHeader from "../_components/AppHeader";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ai.kamoru.jk:8000";

const STRENGTHS = [
  { key: "dejitter", label: "흔들림만", desc: "이동·추종은 보존하고 떨림만 제거 (트래블 샷)" },
  { key: "smooth", label: "부분 고정", desc: "떨림 + 느린 움직임 일부 정리" },
  { key: "lock", label: "완전 고정", desc: "느린 드리프트까지 평탄화 (정지형 구간)" },
  { key: "auto", label: "자동", desc: "영상의 카메라/인물 이동량을 보고 강도를 자동 선택 (기본)" },
] as const;

const MODE_LABEL: Record<string, string> = { background: "배경 고정", person: "인물 고정" };
const STRENGTH_LABEL: Record<string, string> = {
  dejitter: "흔들림만",
  smooth: "부분 고정",
  lock: "완전 고정",
  auto: "자동",
};
const STATUS_LABEL: Record<string, string> = {
  queued: "대기 중",
  running: "처리 중",
  done: "완료",
  failed: "실패",
  canceled: "취소됨",
};

// 모드별 처리 단계(원형 불빛). detect/track 은 한 '추적' 단계로 묶는다.
const STAGE_FLOW: Record<string, { key: string; label: string; match: string[] }[]> = {
  background: [
    { key: "decode", label: "디코딩", match: ["decode"] },
    { key: "detect", label: "분석", match: ["detect"] },
    { key: "transform", label: "보정", match: ["transform"] },
    { key: "encode", label: "인코딩", match: ["encode"] },
  ],
  person: [
    { key: "decode", label: "디코딩", match: ["decode"] },
    { key: "track", label: "추적", match: ["track", "detect"] },
    { key: "transform", label: "보정", match: ["transform"] },
    { key: "warp", label: "합성", match: ["warp"] },
    { key: "encode", label: "인코딩", match: ["encode"] },
  ],
};

type Metrics = {
  smoothing?: number;
  canvas_expand_w?: number;
  canvas_expand_h?: number;
  tracker?: string;
  edge?: string;
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

function relTime(ts?: number): string {
  if (!ts) return "";
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "방금";
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  return `${Math.floor(s / 86400)}일 전`;
}

// 단계별 원형 불빛 — 대기(회색)·진행중(주황 점멸)·완료(초록)·실패(빨강)
function StageLights({ status }: { status: JobStatus }) {
  const flow = STAGE_FLOW[status.mode] ?? STAGE_FLOW.background;
  const cur = status.stage ?? "";
  const curIdx = flow.findIndex((d) => d.match.includes(cur));
  const isDone = status.status === "done";
  const isFailed = status.status === "failed";
  return (
    <ul className="space-y-2">
      {flow.map((d, i) => {
        let dot = "bg-muted";
        let txt = "text-muted-foreground";
        let pulse = false;
        if (isDone || (curIdx >= 0 && i < curIdx)) {
          dot = "bg-success";
          txt = "";
        } else if (curIdx === i) {
          if (isFailed) {
            dot = "bg-destructive";
            txt = "text-destructive";
          } else {
            dot = "bg-amber-500";
            txt = "text-foreground";
            pulse = true;
          }
        }
        return (
          <li key={d.key} className="flex items-center gap-2 text-xs">
            <span
              className={`h-3 w-3 shrink-0 rounded-full ${dot} ${pulse ? "animate-pulse" : ""}`}
            />
            <span className={txt}>{d.label}</span>
            {curIdx === i && !isFailed && (
              <span className="ml-auto tabular-nums text-muted-foreground">
                {status.progress ?? 0}%
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export default function StabilizePage() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [mode, setMode] = useState<"background" | "person">("background");
  const [strength, setStrength] = useState<string>("auto");

  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const origRef = useRef<HTMLVideoElement>(null);
  const stabRef = useRef<HTMLVideoElement>(null);
  const [syncPlaying, setSyncPlaying] = useState(false);
  const [muted, setMuted] = useState(true);

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

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f && f.type.startsWith("video")) onPick(f);
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

  function backToSetup() {
    setStatus(null);
    setJobId(null);
    setSyncPlaying(false);
  }

  function syncToggle() {
    const o = origRef.current;
    const s = stabRef.current;
    if (!o || !s) return;
    if (syncPlaying) {
      o.pause();
      s.pause();
      setSyncPlaying(false);
    } else {
      s.currentTime = o.currentTime;
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
    o.play().catch(() => {});
    s.play().catch(() => {});
    setSyncPlaying(true);
  }
  function onOrigTime() {
    if (!syncPlaying) return;
    const o = origRef.current;
    const s = stabRef.current;
    if (o && s && Math.abs(s.currentTime - o.currentTime) > 0.3) s.currentTime = o.currentTime;
  }

  const running = status && !TERMINAL.has(status.status);
  const done = status?.status === "done";
  const doneJob = status && status.status === "done" ? status : null;
  const resultUrl = jobId ? `${API_BASE}/api/stabilize/jobs/${jobId}/result` : null;
  const metrics = status?.outputs?.[0]?.metrics;
  const canCompare = done && !!resultUrl && !!previewUrl;

  return (
    <div className="relative flex-1 flex flex-col">
      <AppHeader active="stabilize" />
      <input
        ref={fileInputRef}
        type="file"
        accept="video/mp4,video/*"
        className="hidden"
        onChange={(e) => onPick(e.target.files?.[0] ?? null)}
      />

      {/* 가로 모니터에선 폭을 넓게(32"/24" 멀티모니터), 세로는 자연히 좁아짐 */}
      <div className="mx-auto w-full max-w-[2400px] px-4 py-4">
        <div className="grid gap-4 landscape:grid-cols-[minmax(300px,340px)_1fr_minmax(220px,300px)] items-start">
          {/* ===== 좌: 옵션 + 처리중 ===== */}
          <div className="space-y-4 landscape:sticky landscape:top-4">
            <section className="rounded-lg border border-border bg-card p-4 space-y-4">
              {file ? (
                <div className="flex items-center gap-2 text-xs">
                  <span className="truncate">📹 {file.name} · {(file.size / 1024 / 1024).toFixed(1)}MB</span>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="ml-auto shrink-0 px-2 py-1 rounded bg-muted hover:bg-muted/80"
                  >
                    변경
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full px-4 py-2 rounded text-sm bg-primary text-primary-foreground hover:bg-primary/90"
                >
                  영상 파일 선택
                </button>
              )}

              <div className="space-y-1.5">
                <span className="text-sm font-medium">안정화 기준</span>
                <div className="flex gap-2">
                  {(["background", "person"] as const).map((mk) => (
                    <button
                      key={mk}
                      onClick={() => setMode(mk)}
                      className={`px-3 py-1.5 rounded text-sm ${
                        mode === mk ? "bg-primary text-primary-foreground" : "bg-muted"
                      }`}
                    >
                      {MODE_LABEL[mk]}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  {mode === "background"
                    ? "배경(문·벽 등)을 기준으로 카메라 흔들림을 제거합니다."
                    : "지정한 인물(주인공)을 화면에 고정합니다. 가운데 영상에서 주인공을 클릭해 지정하세요."}
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

              <button
                onClick={submit}
                disabled={!file || submitting || !!running}
                className="w-full px-4 py-2 rounded text-sm bg-primary hover:bg-primary/90 text-primary-foreground disabled:bg-muted disabled:text-muted-foreground"
              >
                {submitting ? "업로드 중…" : running ? "처리 중…" : "안정화 시작"}
              </button>
              <p className="text-xs text-muted-foreground">
                결과는 자르지 않고 캔버스를 확장합니다(여백은 블러로 채움).
              </p>
              {err && <p className="text-sm text-destructive whitespace-pre-wrap">{err}</p>}
            </section>

            {/* 처리중/실패 — 단계별 원형 불빛 */}
            {status && !done && (
              <section className="rounded-lg border border-border bg-card p-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="text-sm font-medium">
                    <span
                      className={status.status === "failed" ? "text-destructive" : "text-foreground"}
                    >
                      {STATUS_LABEL[status.status] ?? status.status}
                    </span>
                  </h2>
                  {running ? (
                    <button onClick={cancelJob} className="px-2 py-1 rounded text-xs bg-muted">
                      취소
                    </button>
                  ) : (
                    <button
                      onClick={backToSetup}
                      className="px-2 py-1 rounded text-xs bg-muted hover:bg-muted/80"
                    >
                      ↩ 다시 설정
                    </button>
                  )}
                </div>
                <StageLights status={status} />
                {status.note && <p className="text-xs text-muted-foreground">참고: {status.note}</p>}
                {status.status === "failed" && (
                  <p className="text-sm text-destructive whitespace-pre-wrap">{status.error}</p>
                )}
              </section>
            )}
          </div>

          {/* ===== 가운데: 미리보기/결과 ===== */}
          <div className="min-w-0">
            {doneJob && resultUrl ? (
              // 결과: 전/후 비교
              <section className="rounded-lg border border-border bg-card p-4 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  {previewUrl && (
                    <figure className="space-y-1 min-w-0">
                      <figcaption className="text-xs text-muted-foreground">원본</figcaption>
                      <video
                        ref={origRef}
                        src={previewUrl}
                        controls
                        muted={muted}
                        onTimeUpdate={onOrigTime}
                        onPause={() => syncPlaying && stabRef.current?.pause()}
                        onPlay={() => syncPlaying && stabRef.current?.play().catch(() => {})}
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
                      muted
                      className="w-full h-[68vh] object-contain rounded border border-border bg-black"
                    />
                  </figure>
                </div>
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
                      <button
                        onClick={() => setMuted((m) => !m)}
                        className="px-3 py-1.5 rounded text-sm bg-muted hover:bg-muted/80"
                        title="동시 재생 시 소리 끄기/켜기"
                      >
                        {muted ? "🔇 음소거" : "🔊 소리"}
                      </button>
                    </>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {MODE_LABEL[doneJob.mode] ?? doneJob.mode} ·{" "}
                    {STRENGTH_LABEL[doneJob.strength] ?? doneJob.strength}
                    {metrics?.tracker === "sam2" ? " · SAM2" : ""}
                  </span>
                  <div className="ml-auto flex items-center gap-3">
                    <button
                      onClick={backToSetup}
                      className="px-3 py-1.5 rounded text-sm bg-muted hover:bg-muted/80"
                    >
                      ↩ 다시 설정
                    </button>
                    <a
                      href={resultUrl}
                      download
                      className="px-3 py-1.5 rounded text-sm bg-primary text-primary-foreground hover:bg-primary/90"
                    >
                      다운로드
                    </a>
                  </div>
                </div>
              </section>
            ) : previewUrl ? (
              // 설정: 비디오 맨 위, 부가 정보(주인공 지정 등) 하단
              <section className="rounded-lg border border-border bg-card p-4 space-y-3">
                <div className="relative mx-auto h-[64vh] aspect-[9/16] bg-black rounded overflow-hidden">
                  <video
                    ref={pickVideoRef}
                    src={previewUrl}
                    controls
                    className="w-full h-full object-cover"
                  />
                  {mode === "person" && pickMode && (
                    <div
                      className="absolute inset-0 cursor-crosshair"
                      onClick={onPickClick}
                      aria-label="주인공 클릭"
                    />
                  )}
                  {mode === "person" && subject && (
                    <div
                      className="absolute h-5 w-5 -ml-2.5 -mt-2.5 rounded-full border-2 border-success bg-success/30 pointer-events-none"
                      style={{ left: `${subject.x * 100}%`, top: `${subject.y * 100}%` }}
                    />
                  )}
                </div>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <h2 className="text-sm font-medium">
                      {mode === "person" ? "주인공 지정 & 미리보기" : "미리보기"}
                    </h2>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {mode === "person"
                        ? "원하는 장면에서 멈춘 뒤 “주인공 클릭 지정”을 누르고 고정할 지점(얼굴/몸통)을 클릭. 미지정 시 중앙 인물 자동."
                        : "배경 기준으로 흔들림을 제거합니다. 왼쪽에서 강도를 고르고 “안정화 시작”을 누르세요."}
                      {mode === "person" && subject
                        ? ` · 지정됨(${(subject.x * 100).toFixed(0)}%, ${(subject.y * 100).toFixed(0)}%, t=${subject.t.toFixed(1)}s)`
                        : ""}
                    </p>
                  </div>
                  {mode === "person" && (
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => setPickMode((v) => !v)}
                        className={`px-3 py-1.5 rounded text-sm ${
                          pickMode ? "bg-primary text-primary-foreground" : "bg-muted"
                        }`}
                      >
                        {pickMode ? "인물을 클릭…" : subject ? "다시 지정" : "주인공 클릭 지정"}
                      </button>
                      {subject && (
                        <button
                          onClick={() => setSubject(null)}
                          className="px-2 py-1.5 rounded text-sm bg-muted hover:bg-muted/80 text-muted-foreground"
                        >
                          지우기
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </section>
            ) : (
              // 업로드: 크게, 드래그&드롭
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                className={`flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed min-h-[64vh] text-center p-10 transition-colors ${
                  dragOver ? "border-primary bg-primary/5" : "border-border bg-card/40"
                }`}
              >
                <svg
                  width="44"
                  height="44"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="text-muted-foreground"
                  aria-hidden
                >
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                <p className="text-lg font-medium">영상을 여기에 끌어다 놓으세요</p>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="px-4 py-2 rounded text-sm bg-primary text-primary-foreground hover:bg-primary/90"
                >
                  또는 파일 선택
                </button>
                <p className="text-xs text-muted-foreground">흔들린 짧은 영상 (mp4 등)</p>
              </div>
            )}
          </div>

          {/* ===== 우: 최근 작업 ===== */}
          <div className="landscape:sticky landscape:top-4">
            <section className="rounded-lg border border-border bg-card p-4">
              <h2 className="text-sm font-medium mb-2">최근 작업</h2>
              {jobs.length === 0 ? (
                <p className="text-xs text-muted-foreground">아직 작업이 없습니다.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {jobs.map((j) => (
                    <li key={j.job_id} className="flex items-center gap-2 py-2">
                      <button
                        onClick={() => {
                          setSyncPlaying(false);
                          setJobId(j.job_id);
                          setStatus(j);
                        }}
                        className="text-left min-w-0 flex-1"
                      >
                        <div className={`text-xs ${j.job_id === jobId ? "text-foreground" : ""}`}>
                          {MODE_LABEL[j.mode] ?? j.mode} · {STRENGTH_LABEL[j.strength] ?? j.strength}
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          <span
                            className={
                              j.status === "done"
                                ? "text-success"
                                : j.status === "failed"
                                  ? "text-destructive"
                                  : ""
                            }
                          >
                            {STATUS_LABEL[j.status] ?? j.status}
                          </span>
                          {j.created_at ? ` · ${relTime(j.created_at)}` : ""}
                        </div>
                      </button>
                      <button
                        onClick={() => removeJob(j.job_id)}
                        className="shrink-0 text-xs text-muted-foreground hover:text-destructive"
                      >
                        삭제
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
