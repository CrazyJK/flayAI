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

const MODE_LABEL: Record<string, string> = {
  background: "배경 고정",
  person: "인물 고정",
  both: "둘 다",
};
const VARIANT_LABEL: Record<string, string> = { background: "배경", person: "인물" };
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
// '둘 다'는 인물 플로우로 표시(배경 단계도 분석/보정/인코딩으로 매핑됨)
STAGE_FLOW.both = STAGE_FLOW.person;

type Metrics = {
  smoothing?: number;
  canvas_expand_w?: number;
  canvas_expand_h?: number;
  tracker?: string;
  edge?: string;
  scale_lock?: boolean;
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
  const [mode, setMode] = useState<"background" | "person" | "both">("background");
  const [strength, setStrength] = useState<string>("auto");
  const [edge, setEdge] = useState<"blur" | "crop">("blur");
  const [interpolate, setInterpolate] = useState(false);
  const [scaleLock, setScaleLock] = useState(false);

  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const origRef = useRef<HTMLVideoElement>(null);
  const stabRefs = useRef<Record<string, HTMLVideoElement | null>>({}); // variant별 결과 영상
  const [syncPlaying, setSyncPlaying] = useState(false);
  const [muted, setMuted] = useState(true);

  const pickVideoRef = useRef<HTMLVideoElement>(null);
  const [subject, setSubject] = useState<{ t: number; x: number; y: number } | null>(null);
  const [pickMode, setPickMode] = useState(false);

  function onPick(f: File | null) {
    setFile(f);
    setSubject(null);
    setPickMode(false);
    // 새 파일 선택 시 이전 잡/결과를 비워 새 영상 설정 화면으로
    setJobId(null);
    setStatus(null);
    setSyncPlaying(false);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(f ? URL.createObjectURL(f) : null);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f && (f.type.startsWith("video") || f.type === "image/gif")) onPick(f);
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
      fd.append("edge", edge);
      if (interpolate) fd.append("interpolate", "1");
      if (personish && scaleLock) fd.append("scale_lock", "1");
      if (personish && subject) fd.append("subject", JSON.stringify(subject));
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

  async function removeAllJobs() {
    if (!jobs.length || !window.confirm("최근 작업을 모두 삭제할까요?")) return;
    await Promise.all(
      jobs.map((j) =>
        fetch(`${API_BASE}/api/stabilize/jobs/${j.job_id}`, { method: "DELETE" }).catch(() => {}),
      ),
    );
    setJobId(null);
    setStatus(null);
    loadJobs();
  }

  function backToSetup() {
    setStatus(null);
    setJobId(null);
    setSyncPlaying(false);
  }

  // 원본 + 모든 결과 영상을 함께 제어(동시 재생). 원본을 마스터로(없으면 첫 결과).
  function _vids(): HTMLVideoElement[] {
    return [origRef.current, ...Object.values(stabRefs.current)].filter(Boolean) as HTMLVideoElement[];
  }
  function syncToggle() {
    const vids = _vids();
    if (vids.length < 2) return;
    if (syncPlaying) {
      vids.forEach((v) => v.pause());
      setSyncPlaying(false);
    } else {
      const m = origRef.current ?? vids[0];
      vids.forEach((v) => {
        if (v !== m) v.currentTime = m.currentTime;
      });
      vids.forEach((v) => v.play().catch(() => {}));
      setSyncPlaying(true);
    }
  }
  function syncRestart() {
    const vids = _vids();
    if (!vids.length) return;
    vids.forEach((v) => {
      v.currentTime = 0;
    });
    vids.forEach((v) => v.play().catch(() => {}));
    setSyncPlaying(true);
  }
  function onMasterTime() {
    if (!syncPlaying) return;
    const m = origRef.current ?? Object.values(stabRefs.current).find(Boolean) ?? null;
    if (!m) return;
    _vids().forEach((v) => {
      if (v !== m && Math.abs(v.currentTime - m.currentTime) > 0.3) v.currentTime = m.currentTime;
    });
  }

  const running = status && !TERMINAL.has(status.status);
  const done = status?.status === "done";
  const doneJob = status && status.status === "done" ? status : null;
  const resultUrl = jobId ? `${API_BASE}/api/stabilize/jobs/${jobId}/result` : null;
  const isImage = !!file && file.type.startsWith("image"); // gif 등 — 원본을 img 로
  const personish = mode === "person" || mode === "both"; // 주인공 지정이 필요한 모드
  const outs = doneJob?.outputs ?? [];
  // 원본: 방금 올린 파일(previewUrl) 우선, 최근작업에서 열면 서버 작업본(?variant=original)
  const origIsImage = isImage && !!previewUrl;
  const origSrc = previewUrl ?? (done && resultUrl ? `${resultUrl}?variant=original` : null);
  // 원본 + 각 결과를 한 줄에 같이 띄우고 동시 재생(둘 다 모드는 원본·배경·인물 3개).
  const vidCount = (origSrc && !origIsImage ? 1 : 0) + outs.length;
  // 각 영상(figure) 폭을 줄(메인) 너비의 1/N 로 제한 → 줄바꿈 없이 N개가 한 줄에(넘치면 축소)
  const figMax = `calc((100% - ${(Math.max(vidCount, 1) - 1) * 8}px) / ${Math.max(vidCount, 1)})`;
  const canSync = !!done && vidCount >= 2;

  return (
    <div className="relative flex-1 flex flex-col">
      <AppHeader active="stabilize" />
      <input
        ref={fileInputRef}
        type="file"
        accept="video/mp4,video/quicktime,video/x-msvideo,video/*,image/gif"
        className="hidden"
        onChange={(e) => onPick(e.target.files?.[0] ?? null)}
      />

      {/* 가로 모니터에선 폭을 넓게(32"/24" 멀티모니터), 세로는 자연히 좁아짐 */}
      <div className="mx-auto w-full max-w-[2400px] px-4 py-4">
        <div
          className={`grid gap-4 items-start ${
            doneJob
              ? // 결과: 메인을 풀 너비(1fr)로 — 원본·결과 N개를 한 줄에 최대한 크게
                "landscape:grid-cols-[minmax(330px,360px)_1fr_minmax(330px,360px)]"
              : // 설정·업로드: 적당한 고정 폭으로 가운데 정렬
                "landscape:grid-cols-[minmax(330px,360px)_minmax(0,1261px)_minmax(330px,360px)] landscape:justify-center"
          }`}
        >
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
                  {(["background", "person", "both"] as const).map((mk) => (
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
                    : mode === "person"
                      ? "지정한 인물(주인공)을 화면에 고정합니다. 가운데 영상에서 주인공을 클릭해 지정하세요."
                      : "배경·인물 두 결과를 모두 만들어 비교합니다. 주인공도 클릭해 지정하세요."}
                </p>
              </div>

              <div className="space-y-1.5">
                <span className="text-sm font-medium">고정 강도</span>
                <div className="flex flex-nowrap gap-1.5">
                  {STRENGTHS.map((s) => (
                    <button
                      key={s.key}
                      onClick={() => setStrength(s.key)}
                      className={`px-2 py-1.5 rounded text-sm whitespace-nowrap ${
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

              <div className="space-y-1.5">
                <span className="text-sm font-medium">여백 처리</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setEdge("blur")}
                    className={`px-3 py-1.5 rounded text-sm ${
                      edge === "blur" ? "bg-primary text-primary-foreground" : "bg-muted"
                    }`}
                  >
                    채움(확장)
                  </button>
                  <button
                    onClick={() => setEdge("crop")}
                    className={`px-3 py-1.5 rounded text-sm ${
                      edge === "crop" ? "bg-primary text-primary-foreground" : "bg-muted"
                    }`}
                  >
                    잘라내기
                  </button>
                </div>
                <p className="text-xs text-muted-foreground">
                  {edge === "blur"
                    ? "자르지 않고 화각 유지 — 여백은 블러로 채움(배경 모드는 검은 여백)."
                    : "안정화 여백을 잘라내 깔끔하게(영상 크기는 줄어듭니다)."}
                </p>
              </div>

              {personish && (
                <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={scaleLock}
                    onChange={(e) => setScaleLock(e.target.checked)}
                    className="accent-primary"
                  />
                  주인공 크기까지 고정 — 거리 변화 작을 때만(클수록 배경 줌 손실↑)
                </label>
              )}
              <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={interpolate}
                  onChange={(e) => setInterpolate(e.target.checked)}
                  className="accent-primary"
                />
                부드럽게(저fps 보간) — gif 등 끊김 완화. 흔들림 자체는 개선 안 됨
              </label>

              <button
                onClick={submit}
                disabled={!file || submitting || !!running}
                className="w-full px-4 py-2 rounded text-sm bg-primary hover:bg-primary/90 text-primary-foreground disabled:bg-muted disabled:text-muted-foreground"
              >
                {submitting ? "업로드 중…" : running ? "처리 중…" : "안정화 시작"}
              </button>
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
                {/* 원본 + 각 결과를 한 줄에(둘 다 모드는 원본·배경·인물) — 폭 1/N 제한으로 줄바꿈 없이 동시 재생 */}
                <div className="flex justify-center items-start gap-2">
                  {origSrc && (
                    <figure className="space-y-1 min-w-0" style={{ maxWidth: figMax }}>
                      <figcaption className="text-xs text-muted-foreground">원본</figcaption>
                      {origIsImage ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={origSrc}
                          alt="원본"
                          className="block mx-auto max-w-full max-h-[82vh] rounded border border-border bg-black"
                        />
                      ) : (
                        <video
                          ref={origRef}
                          src={origSrc}
                          controls
                          muted={muted}
                          onTimeUpdate={onMasterTime}
                          onPause={() => {
                            if (syncPlaying)
                              _vids().forEach((v) => v !== origRef.current && v.pause());
                          }}
                          onPlay={() => {
                            if (syncPlaying)
                              _vids().forEach(
                                (v) => v !== origRef.current && v.play().catch(() => {}),
                              );
                          }}
                          onEnded={() => setSyncPlaying(false)}
                          className="block mx-auto max-w-full max-h-[82vh] rounded border border-border bg-black"
                        />
                      )}
                    </figure>
                  )}
                  {outs.map((o) => (
                    <figure key={o.variant} className="space-y-1 min-w-0" style={{ maxWidth: figMax }}>
                      <figcaption className="flex items-center gap-2 text-xs">
                        <span className="text-success">
                          {outs.length > 1 ? `${VARIANT_LABEL[o.variant] ?? o.variant} 안정화` : "안정화"}
                        </span>
                        <a
                          href={`${resultUrl}?variant=${o.variant}`}
                          download
                          className="text-muted-foreground hover:text-foreground"
                          title="다운로드"
                        >
                          ⬇
                        </a>
                      </figcaption>
                      <video
                        ref={(el) => {
                          stabRefs.current[o.variant] = el;
                        }}
                        src={`${resultUrl}?variant=${o.variant}`}
                        controls
                        muted
                        className="block mx-auto max-w-full max-h-[82vh] rounded border border-border bg-black"
                      />
                    </figure>
                  ))}
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {canSync && (
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
                  </span>
                  <div className="ml-auto flex items-center gap-3">
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="px-3 py-1.5 rounded text-sm bg-muted hover:bg-muted/80"
                    >
                      ＋ 새 영상
                    </button>
                    <button
                      onClick={backToSetup}
                      className="px-3 py-1.5 rounded text-sm bg-muted hover:bg-muted/80"
                    >
                      ↩ 다시 설정
                    </button>
                  </div>
                </div>
              </section>
            ) : previewUrl ? (
              // 설정: 비디오 맨 위, 부가 정보(주인공 지정 등) 하단
              <section className="rounded-lg border border-border bg-card p-4 space-y-3">
                {/* 비디오 본래 비율 유지(검은 여백 없음), 세로=높이·가로=폭 기준으로 화면 안에 맞춤 */}
                <div className="relative mx-auto w-fit max-w-full">
                  {isImage ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={previewUrl}
                      alt="원본"
                      className="block max-h-[64vh] max-w-full rounded bg-black"
                    />
                  ) : (
                    <video
                      ref={pickVideoRef}
                      src={previewUrl}
                      controls
                      className="block max-h-[64vh] max-w-full rounded bg-black"
                    />
                  )}
                  {personish && pickMode && (
                    <div
                      className="absolute inset-0 cursor-crosshair"
                      onClick={onPickClick}
                      aria-label="주인공 클릭"
                    />
                  )}
                  {personish && subject && (
                    <div
                      className="absolute h-5 w-5 -ml-2.5 -mt-2.5 rounded-full border-2 border-success bg-success/30 pointer-events-none"
                      style={{ left: `${subject.x * 100}%`, top: `${subject.y * 100}%` }}
                    />
                  )}
                </div>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <h2 className="text-sm font-medium">
                      {personish ? "주인공 지정 & 미리보기" : "미리보기"}
                    </h2>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {personish
                        ? "원하는 장면에서 멈춘 뒤 “주인공 클릭 지정”을 누르고 고정할 지점(얼굴/몸통)을 클릭. 미지정 시 중앙 인물 자동."
                        : "배경 기준으로 흔들림을 제거합니다. 왼쪽에서 강도를 고르고 “안정화 시작”을 누르세요."}
                      {personish && subject
                        ? ` · 지정됨(${(subject.x * 100).toFixed(0)}%, ${(subject.y * 100).toFixed(0)}%, t=${subject.t.toFixed(1)}s)`
                        : ""}
                    </p>
                  </div>
                  {personish && (
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
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-medium">최근 작업</h2>
                {jobs.length > 0 && (
                  <button
                    onClick={removeAllJobs}
                    className="text-[11px] text-muted-foreground hover:text-destructive"
                  >
                    전체 삭제
                  </button>
                )}
              </div>
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
