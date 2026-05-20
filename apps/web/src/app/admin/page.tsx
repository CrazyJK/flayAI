"use client";
"use client";

import Link from "next/link";
import { useCallback, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ai.kamoru.jk:8000";

// ---------------------------------------------------------------------------
// 타입 정의
// ---------------------------------------------------------------------------

type QdrantCollection = {
  name: string;
  points_count: number;
  vectors_count: number;
  dim?: number | null;
  status: string;
  error?: string;
};

type QdrantData = {
  available: boolean;
  collections: QdrantCollection[];
  error?: string;
};

type SqliteTable = {
  name: string;
  count: number;
  note?: string;
};

type SqliteData = {
  available: boolean;
  tables: SqliteTable[];
  recent_queries_24h: number;
  error?: string;
};

type OllamaModel = {
  name: string;
  size: number;
  modified_at: string;
  parameter_size?: string | null;
  quantization?: string | null;
  family?: string | null;
  loaded: boolean;
  size_vram?: number | null;
  expires_at?: string | null;
};

type OllamaData = {
  available: boolean;
  models: OllamaModel[];
  running_count: number;
  error?: string;
};

type IndexerTotals = {
  videos: number;
  posters: number;
  actresses: number;
  face_clusters: number;
  labeled_clusters: number;
};

type IndexerData = {
  available: boolean;
  totals: IndexerTotals;
  completed: Record<string, number>;
  pending: Record<string, number>;
  error?: string;
};

type JobInfo = {
  status: "running" | "done" | "failed" | "error";
  pid?: number;
  started_at?: number;
  finished_at?: number;
  returncode?: number;
  stdout?: string;
  stderr?: string;
  error?: string;
};

type Dashboard = {
  qdrant: QdrantData;
  sqlite: SqliteData;
  ollama: OllamaData;
  indexer: IndexerData;
  jobs: Record<string, JobInfo>;
};

// ---------------------------------------------------------------------------
// 유틸리티
// ---------------------------------------------------------------------------

function fmtBytes(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(1)} ${units[i]}`;
}

function fmtNum(n: number): string {
  return n.toLocaleString("ko-KR");
}

function elapsed(startTs: number): string {
  const sec = Math.round(Date.now() / 1000 - startTs);
  if (sec < 60) return `${sec}초 전`;
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전`;
  return `${Math.floor(sec / 3600)}시간 전`;
}

function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const color = pct >= 100 ? "bg-emerald-500" : pct >= 50 ? "bg-blue-500" : "bg-amber-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-neutral-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-neutral-400 shrink-0 w-8 text-right text-xs">{pct}%</span>
    </div>
  );
}

function SectionCard({
  title,
  badge,
  available,
  children,
}: {
  title: string;
  badge?: string;
  available: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-neutral-800 rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 bg-neutral-900 flex items-center gap-2 border-b border-neutral-800">
        <span className="font-semibold text-base">{title}</span>
        {badge && <span className="text-sm font-mono text-neutral-400 ml-1">{badge}</span>}
        <span
          className={
            "ml-auto text-xs px-1.5 py-0.5 rounded font-mono " +
            (available
              ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
              : "bg-red-500/15 text-red-400 border border-red-500/30")
          }
        >
          {available ? "UP" : "DOWN"}
        </span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Qdrant 섹션
// ---------------------------------------------------------------------------

const QDRANT_DESC: Record<string, string> = {
  videos: "영상 텍스트 임베딩 (bge-m3)",
  posters_clip: "포스터 이미지 임베딩 (CLIP ViT-L/14)",
  faces: "얼굴 벡터 (InsightFace buffalo_l)",
  poster_ocr: "포스터 OCR 텍스트 임베딩 (bge-m3)",
};

function QdrantSection({ data }: { data: QdrantData }) {
  if (!data.available) {
    return (
      <SectionCard title="Qdrant 벡터 DB" available={false}>
        <p className="text-sm text-red-400">{data.error}</p>
      </SectionCard>
    );
  }
  return (
    <SectionCard title="Qdrant 벡터 DB" badge={`${data.collections.length}개 컬렉션`} available>
      <div className="space-y-2">
        {data.collections.map((col) => (
          <div
            key={col.name}
            className="rounded border border-neutral-700/60 bg-neutral-900/50 px-3 py-2"
          >
            {col.error ? (
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-mono text-base text-neutral-200">{col.name}</p>
                  <p className="text-sm text-neutral-400 mt-0.5">
                    {QDRANT_DESC[col.name] ?? "벡터 컬렉션"}
                  </p>
                </div>
                <p className="text-xs text-red-400 shrink-0 max-w-[60%] text-right">{col.error}</p>
              </div>
            ) : (
              <div className="flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-base text-neutral-200">{col.name}</p>
                  <p className="text-xs text-neutral-400 mt-0.5">
                    {QDRANT_DESC[col.name] ?? "벡터 컬렉션"}
                  </p>
                </div>
                <div className="flex gap-4 text-sm text-right shrink-0">
                  <div>
                    <div className="font-mono text-neutral-100">{fmtNum(col.points_count)}</div>
                    <div className="text-neutral-400 text-xs">포인트</div>
                  </div>
                  {col.dim && (
                    <div>
                      <div className="font-mono text-neutral-300">{col.dim}d</div>
                      <div className="text-neutral-400 text-xs">차원</div>
                    </div>
                  )}
                  <div>
                    <span
                      className={
                        "px-1.5 py-0.5 rounded font-mono text-[11px] " +
                        (col.status === "green"
                          ? "bg-emerald-500/15 text-emerald-400"
                          : "bg-amber-500/15 text-amber-400")
                      }
                    >
                      {col.status}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
        {data.collections.length === 0 && <p className="text-sm text-neutral-400">컬렉션 없음</p>}
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// SQLite 섹션
// ---------------------------------------------------------------------------

const SQLITE_DESC: Record<string, string> = {
  videos: "영상 메타데이터 (opus, 제목, 스튜디오, 출시일 등)",
  actresses: "배우 canonical 정보 (이름, 데뷔, 신체 등)",
  actress_aliases: "배우 이름 별칭 → canonical 매핑",
  video_actresses: "영상-배우 다대다 관계",
  studios: "제작사 정보",
  tags: "태그 목록",
  tag_groups: "태그 그룹 분류",
  video_tags: "영상-태그 다대다 관계",
  likes: "좋아요 이벤트 시계열",
  history: "재생·접근 히스토리 로그",
  posters: "포스터 파일 경로 및 OCR 텍스트",
  face_clusters: "얼굴 클러스터 → 배우 매핑",
  poster_faces: "포스터별 검출된 얼굴 bbox·클러스터",
  translations: "번역 캐시 (JP→KO)",
  query_log: "API 쿼리 이력",
  videos_fts: "FTS5 전문 검색 인덱스",
};

function SqliteSection({ data }: { data: SqliteData }) {
  if (!data.available) {
    return (
      <SectionCard title="SQLite DB" available={false}>
        <p className="text-sm text-red-400">{data.error}</p>
      </SectionCard>
    );
  }
  return (
    <SectionCard
      title="SQLite DB"
      badge={`${data.tables.length}개 테이블 · 최근 24h 쿼리 ${fmtNum(data.recent_queries_24h)}건`}
      available
    >
      <div className="space-y-1">
        {data.tables.map((t) => (
          <div
            key={t.name}
            className="flex items-center gap-3 rounded px-2 py-1.5 hover:bg-neutral-800/40 transition-colors"
          >
            <span className="font-mono text-sm text-neutral-200 w-36 shrink-0">
              {t.name}
              {t.note && <span className="ml-1 text-xs text-neutral-500">[{t.note}]</span>}
            </span>
            <span className="text-xs text-neutral-400 flex-1 min-w-0 truncate">
              {SQLITE_DESC[t.name] ?? ""}
            </span>
            <span className="font-mono text-sm text-neutral-300 shrink-0 w-16 text-right">
              {t.count >= 0 ? fmtNum(t.count) : "—"}
            </span>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// Ollama 섹션
// ---------------------------------------------------------------------------

function OllamaSection({ data }: { data: OllamaData }) {
  if (!data.available) {
    return (
      <SectionCard title="Ollama LLM" available={false}>
        <p className="text-sm text-red-400">{data.error}</p>
      </SectionCard>
    );
  }
  const loadedCount = data.models.filter((m) => m.loaded).length;
  return (
    <SectionCard
      title="Ollama LLM"
      badge={`${data.models.length}개 설치 · ${loadedCount}개 VRAM 로드`}
      available
    >
      <div className="space-y-2">
        {data.models.map((m) => (
          <div
            key={m.name}
            className={
              "rounded border px-3 py-2.5 " +
              (m.loaded
                ? "border-emerald-500/30 bg-emerald-500/5"
                : "border-neutral-700/60 bg-neutral-900/50")
            }
          >
            <div className="flex items-start gap-2">
              <span
                className={
                  "mt-1 w-2 h-2 rounded-full shrink-0 " +
                  (m.loaded ? "bg-emerald-400 animate-pulse" : "bg-neutral-600")
                }
                title={m.loaded ? "VRAM 로드 중" : "대기"}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="font-mono text-base text-neutral-100">{m.name}</span>
                  {m.loaded && (
                    <span className="text-[10px] font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-1.5 py-0.5 rounded">
                      VRAM 로드 중
                    </span>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-neutral-400">
                  {m.parameter_size && <span>파라미터 {m.parameter_size}</span>}
                  {m.quantization && <span>양자화 {m.quantization}</span>}
                  {m.family && <span>패밀리 {m.family}</span>}
                  <span>크기 {fmtBytes(m.size)}</span>
                </div>
                {m.loaded && (
                  <div className="mt-1.5 flex flex-wrap gap-x-4 text-[11px]">
                    {m.size_vram != null && m.size_vram > 0 && (
                      <span className="text-emerald-400">VRAM {fmtBytes(m.size_vram)}</span>
                    )}
                    {m.expires_at && (
                      <span className="text-neutral-400">
                        만료 {new Date(m.expires_at).toLocaleTimeString("ko-KR")}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        {data.models.length === 0 && <p className="text-sm text-neutral-400">설치된 모델 없음</p>}
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// 인덱서 섹션
// ---------------------------------------------------------------------------

type PipelineStep = {
  job: string;
  completedKey: string;
  totalKey: "videos" | "posters";
  label: string;
  desc: string;
};

const PIPELINE_STEPS: PipelineStep[] = [
  {
    job: "translate",
    completedKey: "translate",
    totalKey: "videos",
    label: "번역",
    desc: "일본어 제목·설명을 한국어로 번역 (NLLB-200) · 증분 · GPU · 전체 ~7시간",
  },
  {
    job: "embed",
    completedKey: "embed_text",
    totalKey: "videos",
    label: "텍스트 임베딩",
    desc: "영상 텍스트를 벡터화해 Qdrant videos 컬렉션에 저장 (bge-m3) · 전체 재처리 · GPU · ~30분",
  },
  {
    job: "embed-clip",
    completedKey: "embed_clip",
    totalKey: "posters",
    label: "이미지 임베딩",
    desc: "포스터 이미지를 벡터화해 Qdrant posters_clip 컬렉션에 저장 (CLIP ViT-L/14) · 전체 재처리 · GPU · ~11분",
  },
  {
    job: "ocr-posters",
    completedKey: "ocr_posters",
    totalKey: "posters",
    label: "포스터 OCR",
    desc: "포스터 이미지에서 텍스트를 추출해 Qdrant poster_ocr 컬렉션에 저장 (RapidOCR) · 증분 · CPU · ~8시간",
  },
  {
    job: "extract-faces",
    completedKey: "extract_faces",
    totalKey: "posters",
    label: "얼굴 추출",
    desc: "포스터에서 얼굴을 감지·벡터화해 Qdrant faces 컬렉션에 저장 (InsightFace buffalo_l) · 증분 · GPU · ~79분",
  },
];

type StandaloneJob = { job: string; label: string; desc: string };

const STANDALONE_JOBS: StandaloneJob[] = [
  {
    job: "load",
    label: "JSON 로드",
    desc: "K:/Crazy/Info/*.json → SQLite videos 테이블 · 증분 · CPU · ~수초",
  },
  {
    job: "scan",
    label: "포스터 스캔",
    desc: "포스터 디렉토리를 탐색해 instance/archive 분류 후 DB 갱신 · 증분 · CPU · ~수초",
  },
  {
    job: "history",
    label: "히스토리 CSV",
    desc: "재생 히스토리 CSV를 SQLite history 테이블에 반영 · 증분 · CPU · ~수초",
  },
  {
    job: "fts",
    label: "FTS 재구축",
    desc: "videos_fts5 전문 검색 인덱스를 처음부터 재생성 · 전체 재구축 · CPU · ~수초",
  },
  {
    job: "cluster-faces",
    label: "얼굴 클러스터링",
    desc: "mutual-kNN + Union-Find로 얼굴 벡터를 배우 단위로 자동 그룹화 · 전체 재처리 · GPU · ~77초",
  },
  {
    job: "sync-payload",
    label: "페이로드 동기화",
    desc: "Qdrant 각 컬렉션 payload를 SQLite 최신 데이터로 갱신 · 전체 · CPU · ~수분",
  },
];

function JobButton({
  job,
  label,
  info,
  busy,
  onStart,
  onToggleLog,
  expanded,
}: {
  job: string;
  label: string;
  info?: JobInfo;
  busy: string | null;
  onStart: (job: string) => void;
  onToggleLog: (job: string) => void;
  expanded: boolean;
}) {
  const isRunning = info?.status === "running";
  const isDone = info?.status === "done";
  const isFailed = info?.status === "failed" || info?.status === "error";
  const hasLog = !!(info?.stdout || info?.stderr);
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        disabled={!!busy || isRunning}
        onClick={() => onStart(job)}
        className={
          "px-2 py-1 text-sm rounded border transition-colors whitespace-nowrap " +
          (isRunning
            ? "border-amber-500/40 bg-amber-500/10 text-amber-300 cursor-wait"
            : isDone
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
              : isFailed
                ? "border-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20"
                : "border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700")
        }
        title={
          info?.started_at
            ? `${isRunning ? "실행 중" : isDone ? "완료" : "실패"} · ${elapsed(info.started_at)}`
            : "클릭하여 시작"
        }
      >
        {busy === job || isRunning ? (
          <span className="animate-pulse">↻ {label}</span>
        ) : (
          <>
            {isDone && "✓ "}
            {isFailed && "✗ "}
            {label}
          </>
        )}
      </button>
      {hasLog && (
        <button
          type="button"
          onClick={() => onToggleLog(job)}
          className="px-1 py-1 text-xs text-neutral-400 hover:text-neutral-300"
          title="로그 보기"
        >
          {expanded ? "▲" : "▼"}
        </button>
      )}
    </div>
  );
}

function LogBox({ info }: { info: JobInfo }) {
  return (
    <div className="mt-2 rounded border border-neutral-700 bg-neutral-950 p-2 text-sm font-mono max-h-40 overflow-y-auto">
      <div className="text-neutral-400 mb-1">
        rc={info.returncode ?? "—"} · {info.finished_at ? elapsed(info.finished_at) : "실행 중"}
      </div>
      {info.stderr && <pre className="text-amber-300/80 whitespace-pre-wrap">{info.stderr}</pre>}
      {info.stdout && <pre className="text-neutral-300 whitespace-pre-wrap">{info.stdout}</pre>}
    </div>
  );
}

function IndexerSection({
  data,
  jobs,
  onStartJob,
}: {
  data: IndexerData;
  jobs: Record<string, JobInfo>;
  onStartJob: (job: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [expandedJob, setExpandedJob] = useState<string | null>(null);

  async function handleStart(job: string) {
    setBusy(job);
    try {
      await onStartJob(job);
    } catch (e) {
      alert(`작업 시작 실패: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  function toggleLog(job: string) {
    setExpandedJob((prev) => (prev === job ? null : job));
  }

  if (!data.available) {
    return (
      <SectionCard title="인덱서" available={false}>
        <p className="text-sm text-red-400">{data.error}</p>
      </SectionCard>
    );
  }

  const { totals, completed } = data;
  const totalPending = Object.values(data.pending).reduce((a, b) => a + b, 0);

  return (
    <SectionCard
      title="인덱서"
      badge={totalPending > 0 ? `대기 ${fmtNum(totalPending)}` : "모두 완료"}
      available
    >
      {/* 집계 수치 */}
      <div className="flex flex-wrap gap-3 mb-5">
        {[
          { label: "영상", value: totals.videos },
          { label: "포스터", value: totals.posters },
          { label: "배우", value: totals.actresses },
          { label: "얼굴 클러스터", value: totals.face_clusters },
          { label: "클러스터 라벨", value: totals.labeled_clusters },
        ].map((item) => (
          <div
            key={item.label}
            className="bg-neutral-900 rounded px-3 py-1.5 text-center min-w-[72px]"
          >
            <div className="text-neutral-100 font-mono text-base font-semibold">
              {fmtNum(item.value)}
            </div>
            <div className="text-neutral-400 text-xs mt-0.5">{item.label}</div>
          </div>
        ))}
      </div>

      {/* 파이프라인 단계별 진행률 + 배치 버튼 통합 */}
      <div className="mb-4">
        <p className="text-sm font-medium text-neutral-400 mb-2">파이프라인 (진행률 · 시작)</p>
        <div className="space-y-3">
          {PIPELINE_STEPS.map((step) => {
            const done = completed[step.completedKey] ?? 0;
            const total = totals[step.totalKey];
            const pendingKey = step.completedKey;
            const pending = data.pending[pendingKey] ?? 0;
            const jobInfo = jobs[step.job];
            return (
              <div
                key={step.job}
                className="rounded border border-neutral-700/50 bg-neutral-900/40 px-3 py-2"
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-sm text-neutral-200 font-medium w-24 shrink-0">
                    {step.label}
                  </span>
                  <span className="text-xs text-neutral-400 flex-1">{step.desc}</span>
                  <JobButton
                    job={step.job}
                    label={step.label}
                    info={jobInfo}
                    busy={busy}
                    onStart={(j) => void handleStart(j)}
                    onToggleLog={toggleLog}
                    expanded={expandedJob === step.job}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <ProgressBar done={done} total={total} />
                  <span className="text-xs font-mono text-neutral-400 shrink-0 w-28 text-right">
                    {fmtNum(done)}/{fmtNum(total)}
                    {pending > 0 && <span className="ml-1 text-amber-400">+{fmtNum(pending)}</span>}
                  </span>
                </div>
                {expandedJob === step.job && jobInfo && <LogBox info={jobInfo} />}
              </div>
            );
          })}
        </div>
      </div>

      {/* 단독 작업 */}
      <div>
        <p className="text-sm font-medium text-neutral-400 mb-2">기타 작업</p>
        <div className="space-y-1.5">
          {STANDALONE_JOBS.map((sj) => {
            const jobInfo = jobs[sj.job];
            return (
              <div key={sj.job}>
                <div className="flex items-center gap-2 px-1 py-0.5">
                  <JobButton
                    job={sj.job}
                    label={sj.label}
                    info={jobInfo}
                    busy={busy}
                    onStart={(j) => void handleStart(j)}
                    onToggleLog={toggleLog}
                    expanded={expandedJob === sj.job}
                  />
                  <span className="text-xs text-neutral-400 flex-1">{sj.desc}</span>
                </div>
                {expandedJob === sj.job && jobInfo && <LogBox info={jobInfo} />}
              </div>
            );
          })}
        </div>
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// 메인 페이지
// ---------------------------------------------------------------------------

export default function AdminPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/admin/dashboard`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const json = (await r.json()) as Dashboard;
      setData(json);
      setLastRefresh(new Date());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  // 자동 갱신 없음 — 수동 새로고침만 지원 (부하 절약)

  async function startJob(job: string) {
    const r = await fetch(`${API_BASE}/api/admin/jobs/${encodeURIComponent(job)}`, {
      method: "POST",
    });
    if (!r.ok) {
      const body = (await r.json().catch(() => ({}))) as { detail?: string };
      throw new Error(body.detail ?? `HTTP ${r.status}`);
    }
    setTimeout(() => void load(), 3000);
  }

  return (
    <main className="flex-1 flex flex-col mx-auto w-full max-w-3xl px-4">
      <header className="py-4 border-b border-neutral-800 flex items-baseline gap-2">
        <h1 className="text-xl font-semibold">flayAI</h1>
        <span className="text-sm text-neutral-400 font-mono">{API_BASE}</span>
        <nav className="ml-auto flex items-center gap-3 text-sm">
          <Link href="/" className="text-neutral-400 hover:text-neutral-200">
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
          <Link href="/admin" className="text-neutral-200">
            관리자
          </Link>
        </nav>
      </header>

      <div className="py-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">시스템 모니터링</h2>
            <p className="text-sm text-neutral-400 mt-0.5">
              {lastRefresh
                ? `마지막 갱신: ${lastRefresh.toLocaleTimeString("ko-KR")}`
                : "새로고침 버튼으로 데이터를 로드하세요"}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="px-3 py-1.5 text-sm rounded border border-neutral-700 hover:bg-neutral-800 disabled:opacity-50"
          >
            {loading ? "로딩…" : "↻ 새로고침"}
          </button>
        </div>

        {error && (
          <div className="rounded border border-red-500/40 bg-red-500/10 px-4 py-3 text-base text-red-400">
            API 연결 실패: {error}
          </div>
        )}

        {loading && !data && (
          <div className="text-base text-neutral-400 animate-pulse">데이터 로딩 중…</div>
        )}

        {!data && !loading && !error && (
          <div className="text-base text-neutral-400">
            새로고침 버튼을 눌러 시스템 상태를 확인하세요.
          </div>
        )}

        {data && (
          <div className="space-y-6">
            <QdrantSection data={data.qdrant} />
            <OllamaSection data={data.ollama} />
            <SqliteSection data={data.sqlite} />
            <IndexerSection data={data.indexer} jobs={data.jobs} onStartJob={startJob} />
          </div>
        )}
      </div>
    </main>
  );
}
