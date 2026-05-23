"use client";

import { useCallback, useEffect, useId, useState } from "react";
import AppHeader from "../_components/AppHeader";

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
  capabilities?: string[] | null;
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

type StepInfo = {
  step: string;
  status: "pending" | "running" | "done" | "failed" | "error";
  started_at?: number;
  finished_at?: number;
  returncode?: number;
  stdout?: string;
  stderr?: string;
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
  current?: number;
  steps?: StepInfo[];
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

// 처리 대상 건수 × 건당 소요시간(초) 으로 추정한 예상 소요시간을 사람이 읽기 좋게 포맷
function fmtDuration(sec: number): string {
  if (sec <= 0) return "—";
  if (sec < 60) return `${Math.round(sec)}초`;
  if (sec < 3600) return `${Math.round(sec / 60)}분`;
  const h = Math.floor(sec / 3600);
  const m = Math.round((sec % 3600) / 60);
  return m > 0 ? `${h}시간 ${m}분` : `${h}시간`;
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
    <div className="border border-neutral-800 rounded-lg overflow-hidden flex flex-col">
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
      <div className="p-4 flex-1">{children}</div>
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
  poster_caption: "포스터 VLM 캡션 임베딩 (bge-m3)",
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
      {/* 모든 박스 동일 너비(grid 1fr). 폭은 가장 긴 설명이 한 줄로 들어가도록 결정.
          3줄 구성: 이름 / 건수 / 설명(말줄임 없이 한 줄) */}
      <div className="grid gap-2 grid-cols-[repeat(auto-fill,minmax(300px,1fr))]">
        {data.tables.map((t) => (
          <div
            key={t.name}
            className="bg-neutral-900 rounded-lg border border-neutral-800 px-3 py-2.5"
          >
            <div className="font-mono text-sm text-neutral-200">
              {t.name}
              {t.note && <span className="ml-1 text-[10px] text-neutral-500">[{t.note}]</span>}
            </div>
            <div className="font-mono text-lg font-semibold text-neutral-100 mt-0.5 tabular-nums">
              {t.count >= 0 ? fmtNum(t.count) : "—"}
            </div>
            <div className="text-[11px] text-neutral-500 mt-1 whitespace-nowrap">
              {SQLITE_DESC[t.name] ?? ""}
            </div>
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
      {/* 2 x n 그리드. 각 카드 4줄: 이름 / 메타 / capabilities / 로드상태 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {data.models.map((m) => (
          <div
            key={m.name}
            className={
              "rounded border px-3 py-2 flex flex-col gap-1 " +
              (m.loaded
                ? "border-emerald-500/40 bg-emerald-500/5"
                : "border-neutral-700/60 bg-neutral-900/50")
            }
          >
            {/* 1줄: 이름 */}
            <div className="flex items-center gap-2">
              <span
                className={
                  "w-2 h-2 rounded-full shrink-0 " +
                  (m.loaded ? "bg-emerald-400 animate-pulse" : "bg-neutral-700")
                }
                title={m.loaded ? "VRAM 로드 중" : "미로드"}
              />
              <span className="font-mono text-sm text-neutral-100 truncate">{m.name}</span>
            </div>
            {/* 2줄: 메타 */}
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-neutral-400">
              {m.parameter_size && <span>파라미터 {m.parameter_size}</span>}
              {m.quantization && <span>양자화 {m.quantization}</span>}
              {m.family && <span>패밀리 {m.family}</span>}
              <span>크기 {fmtBytes(m.size)}</span>
            </div>
            {/* 3줄: capabilities (지원 기능) */}
            <div className="flex flex-wrap gap-1 min-h-[18px]">
              {(m.capabilities ?? []).map((c) => (
                <span
                  key={c}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-700/40 text-neutral-300 font-mono"
                >
                  {c}
                </span>
              ))}
            </div>
            {/* 4줄: 로드 상태 (미로드여도 높이 유지) */}
            <div className="min-h-[16px] text-[11px] font-mono">
              {m.loaded ? (
                <span className="text-emerald-400">
                  로드 중 · VRAM {fmtBytes(m.size_vram)}
                  {m.expires_at && (
                    <span className="text-neutral-400">
                      {" · "}만료 {new Date(m.expires_at).toLocaleTimeString("ko-KR")}
                    </span>
                  )}
                </span>
              ) : (
                <span className="text-neutral-600">미로드</span>
              )}
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

// 인덱싱 전체 흐름(세로 다이어그램용). 메타 단계 + AI 단계를 논리적 순서로 나열.
// - 메타(load·scan·history·fts·sync-payload): 증분 갱신/전체 재구축에서 자동 실행.
// - AI(translate~ocr): 개별 버튼으로 실행. completedKey/secPerItem 으로 진행률·ETA 표시.
type PipeStage = {
  job: string; // CLI 작업명 = 실행 버튼 + 파이프라인 단계명(메타)
  label: string;
  desc: string;
  group: "메타" | "AI";
  // AI 단계: 진행률/ETA용
  completedKey?: string;
  totalKey?: "videos" | "posters";
  secPerItem?: number; // 건당 최악 소요시간(초)
  // 메타 단계: 대상 건수/예상시간 표시용
  metaCount?: "videos" | "posters" | "all";
  estText?: string;
};

const PIPELINE: PipeStage[] = [
  {
    job: "load",
    label: "JSON 로드",
    group: "메타",
    desc: "영상 메타데이터를 JSON에서 읽어 DB에 적재",
    metaCount: "videos",
    estText: "~수초",
  },
  {
    job: "scan",
    label: "포스터 스캔",
    group: "메타",
    desc: "포스터 파일을 탐색해 분류하고 제목을 보완",
    metaCount: "posters",
    estText: "~수초",
  },
  {
    job: "history",
    label: "히스토리",
    group: "메타",
    desc: "재생·접근 히스토리를 DB에 적재",
    metaCount: "all",
    estText: "~1초",
  },
  {
    job: "fts",
    label: "FTS 색인",
    group: "메타",
    desc: "제목·설명 전문 검색 인덱스를 생성",
    metaCount: "videos",
    estText: "~1초",
  },
  {
    job: "translate",
    label: "번역",
    group: "AI",
    desc: "일본어 제목·설명을 한국어로 번역",
    completedKey: "translate",
    totalKey: "videos",
    secPerItem: 1.2,
  },
  {
    job: "caption-posters",
    label: "포스터 캡션",
    group: "AI",
    desc: "포스터 이미지를 보고 한국어 장면 설명·태그를 생성",
    completedKey: "caption_posters",
    totalKey: "posters",
    secPerItem: 3.5,
  },
  {
    job: "embed",
    label: "텍스트 임베딩",
    group: "AI",
    desc: "영상 텍스트를 의미 검색용 벡터로 변환",
    completedKey: "embed_text",
    totalKey: "videos",
    secPerItem: 0.008,
  },
  {
    job: "embed-clip",
    label: "이미지 임베딩",
    group: "AI",
    desc: "포스터 이미지를 유사 검색용 벡터로 변환",
    completedKey: "embed_clip",
    totalKey: "posters",
    secPerItem: 0.033,
  },
  {
    job: "extract-faces",
    label: "얼굴 추출",
    group: "AI",
    desc: "포스터에서 얼굴을 찾아 벡터로 변환",
    completedKey: "extract_faces",
    totalKey: "posters",
    secPerItem: 0.23,
  },
  {
    job: "cluster-faces",
    label: "얼굴 클러스터링",
    group: "AI",
    desc: "비슷한 얼굴을 묶어 배우 단위로 그룹화",
    estText: "~77초",
  },
  {
    job: "ocr-posters",
    label: "포스터 OCR",
    group: "AI",
    desc: "포스터에 인쇄된 글자를 추출(OCR)",
    completedKey: "ocr_posters",
    totalKey: "posters",
    secPerItem: 1.4,
  },
  {
    job: "sync-payload",
    label: "페이로드 동기화",
    group: "메타",
    desc: "분류·재생 가능 정보를 벡터 DB에 동기화",
    metaCount: "all",
    estText: "~수초",
  },
];

// 한 단계의 현재 상태를 jobs(파이프라인 steps + 개별 작업)에서 해석.
type StageStatus = "idle" | "running" | "done" | "failed";
function stageState(
  job: string,
  jobs: Record<string, JobInfo>,
): { status: StageStatus; info?: JobInfo | StepInfo } {
  const cands: { status: StageStatus; ts: number; info: JobInfo | StepInfo }[] = [];
  for (const pj of ["refresh", "rebuild"]) {
    const p = jobs[pj];
    const s = p?.steps?.find((x) => x.step === job);
    if (s) {
      const st = (s.status === "error" ? "failed" : s.status) as StageStatus;
      cands.push({ status: st, ts: s.started_at ?? p?.started_at ?? 0, info: s });
    }
  }
  const ij = jobs[job];
  if (ij) {
    const st = (ij.status === "error" ? "failed" : ij.status) as StageStatus;
    cands.push({ status: st, ts: ij.started_at ?? 0, info: ij });
  }
  if (cands.length === 0) return { status: "idle" };
  const running = cands.find((c) => c.status === "running");
  if (running) return { status: "running", info: running.info };
  cands.sort((a, b) => b.ts - a.ts);
  return { status: cands[0].status, info: cands[0].info };
}

function JobButton({
  job,
  label,
  sub,
  info,
  busy,
  onStart,
  onToggleLog,
  expanded,
}: {
  job: string;
  label: string;
  sub?: string;
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
          "px-3 py-1.5 text-sm rounded border transition-colors text-left " +
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
        <span className="block whitespace-nowrap font-medium">
          {busy === job || isRunning ? (
            <span className="animate-pulse">↻ {label}</span>
          ) : (
            <>
              {isDone && "✓ "}
              {isFailed && "✗ "}
              {label}
            </>
          )}
        </span>
        {sub && (
          <span className="block text-[10px] font-normal opacity-70 whitespace-nowrap">{sub}</span>
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

// 단계 간 연결 화살표. 좁은 화면은 아래(▼), 넓은 화면(xl)은 오른쪽(→) 방향 SVG.
function StageArrow() {
  return (
    <div
      className="flex items-center justify-center text-neutral-600 py-1 xl:py-0 xl:px-1"
      aria-hidden
    >
      <svg className="xl:hidden" width="16" height="20" viewBox="0 0 16 20" fill="none">
        <path
          d="M8 1V15M3 10l5 5 5-5"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <svg className="hidden xl:block" width="22" height="16" viewBox="0 0 22 16" fill="none">
        <path
          d="M1 8h14M11 3l5 5-5 5"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
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
    // 파괴적 작업은 실행 전 한 번 더 확인
    if (job === "rebuild") {
      const ok = window.confirm(
        "전체 재인덱싱: 메타데이터를 처음부터 재적재하고, 모든 AI 단계(번역·캡션·임베딩·OCR·얼굴)를 강제로 다시 처리합니다.\n" +
          "시간이 매우 오래 걸립니다(최대 수십 시간). 백그라운드로 진행됩니다.\n\n" +
          "계속하시겠습니까?",
      );
      if (!ok) return;
    }
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
  // 증분(신규 건만) vs 전체(전부 재처리) 작업량·예상시간 추정 — 각 버튼에 표시.
  const incrCount = Object.values(data.pending).reduce((a, b) => a + b, 0);
  const incrEtaSec = PIPELINE.reduce(
    (sum, s) =>
      sum + (s.completedKey ? (data.pending[s.completedKey] ?? 0) * (s.secPerItem ?? 0) : 0),
    0,
  );
  const fullCount = PIPELINE.reduce(
    (sum, s) => sum + (s.completedKey && s.totalKey ? totals[s.totalKey] : 0),
    0,
  );
  const fullEtaSec = PIPELINE.reduce(
    (sum, s) => sum + (s.completedKey && s.totalKey ? totals[s.totalKey] * (s.secPerItem ?? 0) : 0),
    0,
  );
  // 메타 단계 대상 건수 (없으면 null)
  const metaCountOf = (s: PipeStage): number | null =>
    s.metaCount === "videos" ? totals.videos : s.metaCount === "posters" ? totals.posters : null;

  // KPI 타일: 기본 수치 + 파생 보조 지표(커버리지%·라벨링·비율)
  const pctOf = (done: number, total: number) => (total > 0 ? Math.round((done / total) * 100) : 0);
  const statTiles: { label: string; value: number; sub?: string }[] = [
    {
      label: "영상",
      value: totals.videos,
      sub: `번역 ${pctOf(completed.translate ?? 0, totals.videos)}% · 임베딩 ${pctOf(completed.embed_text ?? 0, totals.videos)}%`,
    },
    {
      label: "포스터",
      value: totals.posters,
      sub: `CLIP ${pctOf(completed.embed_clip ?? 0, totals.posters)}% · OCR ${pctOf(completed.ocr_posters ?? 0, totals.posters)}% · 얼굴 ${pctOf(completed.extract_faces ?? 0, totals.posters)}%`,
    },
    {
      label: "배우",
      value: totals.actresses,
      sub: totals.actresses > 0 ? `영상 ${(totals.videos / totals.actresses).toFixed(1)}편/명` : undefined,
    },
    {
      label: "얼굴 클러스터",
      value: totals.face_clusters,
      sub: `라벨 ${fmtNum(totals.labeled_clusters)} · ${pctOf(totals.labeled_clusters, totals.face_clusters)}%`,
    },
    {
      label: "클러스터 라벨",
      value: totals.labeled_clusters,
      sub: `미라벨 ${fmtNum(Math.max(0, totals.face_clusters - totals.labeled_clusters))}`,
    },
  ];

  return (
    <SectionCard title="인덱서" available>
      {/* 집계 KPI 타일 (기본 수치 + 보조 지표) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-5">
        {statTiles.map((item) => (
          <div
            key={item.label}
            className="bg-neutral-900 rounded-lg border border-neutral-800 px-3 py-2.5"
          >
            <div className="text-neutral-400 text-xs">{item.label}</div>
            <div className="text-neutral-100 font-mono text-xl font-semibold mt-0.5 tabular-nums">
              {fmtNum(item.value)}
            </div>
            {item.sub && <div className="text-[11px] text-neutral-500 mt-1">{item.sub}</div>}
          </div>
        ))}
      </div>

      {/* 일괄 작업 (메타 + AI 전체 파이프라인을 순서대로 실행) */}
      <div className="mb-4 flex flex-wrap items-stretch gap-2">
        <JobButton
          job="refresh"
          label="증분 인덱싱"
          sub={`신규 ${fmtNum(incrCount)}건 · 최대 ~${fmtDuration(incrEtaSec)}`}
          info={jobs["refresh"]}
          busy={busy}
          onStart={(j) => void handleStart(j)}
          onToggleLog={toggleLog}
          expanded={false}
        />
        <JobButton
          job="rebuild"
          label="⚠ 전체 재인덱싱"
          sub={`전체 ${fmtNum(fullCount)}건 · 최대 ~${fmtDuration(fullEtaSec)}`}
          info={jobs["rebuild"]}
          busy={busy}
          onStart={(j) => void handleStart(j)}
          onToggleLog={toggleLog}
          expanded={false}
        />
      </div>

      {/* 흐름도 — 좁은 화면은 세로(▼), 넓은 화면은 가로(→) */}
      <div className="flex flex-col xl:flex-row xl:flex-wrap xl:items-stretch gap-2">
        {PIPELINE.map((s, i) => {
          const { status, info } = stageState(s.job, jobs);
          const isAI = s.group === "AI";
          const done = s.completedKey ? (completed[s.completedKey] ?? 0) : 0;
          const total = s.totalKey ? totals[s.totalKey] : 0;
          const pending = s.completedKey ? (data.pending[s.completedKey] ?? 0) : 0;
          const eta = s.secPerItem ? pending * s.secPerItem : 0;
          const stepInfo = info as JobInfo | undefined;
          const hasLog = !!(stepInfo?.stdout || stepInfo?.stderr);
          const expanded = expandedJob === s.job;
          const mc = metaCountOf(s);
          const border =
            status === "running"
              ? "border-amber-500/60 bg-amber-500/5"
              : status === "done"
                ? "border-emerald-500/40 bg-neutral-900/40"
                : status === "failed"
                  ? "border-red-500/50 bg-red-500/5"
                  : "border-neutral-700/50 bg-neutral-900/40";
          return (
            <div key={s.job} className="flex flex-col xl:flex-row xl:items-stretch">
              <div
                className={
                  "rounded-lg border px-3 py-2.5 transition-colors xl:w-[360px] xl:flex xl:flex-col " +
                  border
                }
              >
                <div className="flex items-center gap-2">
                  <span className="w-4 text-center shrink-0">
                    {status === "running" ? (
                      <span className="text-amber-400 animate-pulse">●</span>
                    ) : status === "done" ? (
                      <span className="text-emerald-400">✓</span>
                    ) : status === "failed" ? (
                      <span className="text-red-400">✗</span>
                    ) : (
                      <span className="text-neutral-600">○</span>
                    )}
                  </span>
                  <span className="text-sm font-semibold text-neutral-100">{s.label}</span>
                  <span
                    className={
                      "text-[10px] px-1.5 py-0.5 rounded font-mono " +
                      (isAI ? "bg-blue-500/15 text-blue-300" : "bg-neutral-600/30 text-neutral-300")
                    }
                  >
                    {s.group}
                  </span>
                  <div className="ml-auto flex items-center gap-1">
                    {hasLog && (
                      <button
                        type="button"
                        onClick={() => toggleLog(s.job)}
                        className="px-1 text-xs text-neutral-400 hover:text-neutral-200"
                        title="로그"
                      >
                        {expanded ? "▲" : "▼"}
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={!!busy || status === "running"}
                      onClick={() => void handleStart(s.job)}
                      className={
                        "px-2 py-0.5 text-xs rounded border whitespace-nowrap " +
                        (status === "running"
                          ? "border-amber-500/40 bg-amber-500/10 text-amber-300 cursor-wait"
                          : "border-neutral-700 bg-neutral-800 text-neutral-300 hover:bg-neutral-700")
                      }
                    >
                      {status === "running" ? "↻ 실행 중" : "실행"}
                    </button>
                  </div>
                </div>
                <p className="text-xs text-neutral-400 mt-1 ml-6">{s.desc}</p>
                <div className="mt-1.5 ml-6">
                  {isAI && s.completedKey ? (
                    // 진행률은 두 줄로: 1행 프로그레스바, 2행 건수·ETA (박스 밖으로 넘치지 않게)
                    <div className="space-y-1">
                      <ProgressBar done={done} total={total} />
                      <div className="text-xs font-mono text-neutral-400">
                        {fmtNum(done)}/{fmtNum(total)}
                        {pending > 0 && (
                          <span className="ml-1 text-amber-400">
                            +{fmtNum(pending)} · 최대 ~{fmtDuration(eta)}
                          </span>
                        )}
                      </div>
                    </div>
                  ) : (
                    <span className="text-xs font-mono text-neutral-400">
                      {mc != null ? `대상 ~${fmtNum(mc)}건 · ` : ""}예상 {s.estText ?? "~수초"}
                    </span>
                  )}
                </div>
                {expanded && stepInfo && hasLog && <LogBox info={stepInfo} />}
              </div>
              {i < PIPELINE.length - 1 && <StageArrow />}
            </div>
          );
        })}
      </div>

      {/* 설명 (흐름도 아래로 이동) */}
      <div className="mt-4 pt-3 border-t border-neutral-800 space-y-1 text-xs text-neutral-500">
        <p>
          증분 인덱싱 = 전체 파이프라인(메타+AI)을 신규 건만 처리. 전체 재인덱싱 = 처음부터 다시
          (확인창). 각 단계 카드의 [실행] 으로 개별 실행도 가능.
        </p>
        <p>
          ⓘ 시간은 <span className="text-amber-400">최대(상한)</span> 추정 — 실제는 캐시·파일명
          제목·GPU 배치로 보통 더 빠릅니다. 각 단계 버튼으로 개별 실행도 가능합니다.
        </p>
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// 시스템 모니터 (CPU/RAM/GPU/VRAM/온도)
// ---------------------------------------------------------------------------

type SystemData = {
  available: boolean;
  cpu_percent?: number;
  cpu_count?: number;
  ram_percent?: number;
  ram_used?: number;
  ram_total?: number;
  gpu_available?: boolean;
  gpu_percent?: number;
  vram_used_mib?: number;
  vram_total_mib?: number;
  gpu_temp?: number;
  gpu_name?: string;
};

type MonitorData = { system: SystemData; qdrant: QdrantData; ollama: OllamaData };

// 실시간 차트용 롤링 버퍼 (각 지표 최근 N초 %값)
type MetricHistory = { cpu: number[]; ram: number[]; gpu: number[]; vram: number[] };

// 현재 %값 헤더 + 최근 추이 SVG 영역 차트.
// viewBox 0~100 좌표 + preserveAspectRatio=none 으로 카드 높이를 그대로 채운다.
function MetricChart({
  label,
  percent,
  sub,
  data,
}: {
  label: string;
  percent?: number;
  sub?: string;
  data: number[];
}) {
  const uid = useId();
  const gid = "mc" + uid.replace(/:/g, "");
  const p = percent == null ? null : Math.max(0, Math.min(100, percent));
  // 현재값 임계로 색 결정 (emerald < 60 ≤ amber < 85 ≤ red)
  const stroke = p == null ? "#525252" : p >= 85 ? "#ef4444" : p >= 60 ? "#f59e0b" : "#10b981";

  const pts = data.map((v, i) => {
    const x = data.length <= 1 ? 0 : (i / (data.length - 1)) * 100;
    const y = 100 - Math.max(0, Math.min(100, v));
    return `${x.toFixed(2)} ${y.toFixed(2)}`;
  });
  const line = pts.map((pt, i) => `${i === 0 ? "M" : "L"}${pt}`).join(" ");
  const area = pts.length >= 2 ? `${line} L100 100 L0 100 Z` : "";

  return (
    <div className="bg-neutral-900 rounded-lg border border-neutral-800 px-3 py-2 flex flex-col min-h-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs text-neutral-400 truncate">{label}</span>
        <span className="font-mono text-sm text-neutral-100 shrink-0">
          {p == null ? "—" : `${p.toFixed(0)}%`}
        </span>
      </div>
      <div className="relative flex-1 mt-1 min-h-[36px]">
        <svg
          className="absolute inset-0 h-full w-full"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden
        >
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity="0.35" />
              <stop offset="100%" stopColor={stroke} stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {area && <path d={area} fill={`url(#${gid})`} />}
          {pts.length >= 2 && (
            <path
              d={line}
              fill="none"
              stroke={stroke}
              strokeWidth="1.5"
              strokeLinejoin="round"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
      </div>
      {sub && <div className="mt-1 text-[11px] text-neutral-500 font-mono shrink-0">{sub}</div>}
    </div>
  );
}

function SystemMonitor({ sys, history }: { sys?: SystemData; history: MetricHistory }) {
  if (!sys) return <div className="text-sm text-neutral-500 animate-pulse">시스템 정보 로딩…</div>;
  // 2진 GiB 로 표시 (작업관리자·VRAM 표기와 단위 일치; 라벨은 관례상 GB)
  const gb = (b?: number) => (b == null ? "—" : `${(b / 1024 ** 3).toFixed(1)}GB`);
  const mib = (m?: number) => (m == null ? "—" : `${(m / 1024).toFixed(1)}GB`);
  const vramPct =
    sys.vram_total_mib && sys.vram_used_mib != null
      ? (sys.vram_used_mib / sys.vram_total_mib) * 100
      : undefined;
  // h-full + grid-rows-2 로 카드(SectionCard)가 늘어난 높이를 2x2 차트가 그대로 채운다.
  return (
    <div className="grid h-full min-h-[200px] grid-cols-2 grid-rows-2 gap-2">
      <MetricChart
        label={`CPU${sys.cpu_count ? ` · ${sys.cpu_count}코어` : ""}`}
        percent={sys.cpu_percent}
        data={history.cpu}
      />
      <MetricChart
        label="RAM"
        percent={sys.ram_percent}
        sub={`${gb(sys.ram_used)} / ${gb(sys.ram_total)}`}
        data={history.ram}
      />
      {sys.gpu_available ? (
        <>
          <MetricChart
            label="GPU"
            percent={sys.gpu_percent}
            sub={sys.gpu_temp != null ? `${sys.gpu_temp}°C` : undefined}
            data={history.gpu}
          />
          <MetricChart
            label="VRAM"
            percent={vramPct}
            sub={`${mib(sys.vram_used_mib)} / ${mib(sys.vram_total_mib)}`}
            data={history.vram}
          />
        </>
      ) : (
        <div className="col-span-2 text-xs text-neutral-500 px-1">GPU 정보 없음</div>
      )}
    </div>
  );
}

// CPU/RAM/GPU/VRAM 차트를 Qdrant·Ollama 와 동일한 카드(SectionCard)로 묶는다.
function SystemSection({ sys, history }: { sys?: SystemData; history: MetricHistory }) {
  return (
    <SectionCard
      title="시스템 리소스"
      badge={sys?.gpu_name ? sys.gpu_name.replace("NVIDIA GeForce ", "") : undefined}
      available={!!sys?.available}
    >
      <SystemMonitor sys={sys} history={history} />
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// 메인 페이지
// ---------------------------------------------------------------------------

const MONITOR_POLL_MS = 1000; // 모니터 폴링 간격 (psutil 비차단 + nvidia-smi ~50ms 라 1초도 부하 적음)
const MAX_HISTORY = 60; // 차트 롤링 버퍼 길이 (1초 × 60 = 최근 약 1분)

export default function AdminPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [monitor, setMonitor] = useState<MonitorData | null>(null);
  const [history, setHistory] = useState<MetricHistory>({ cpu: [], ram: [], gpu: [], vram: [] });
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

  const loadMonitor = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/admin/monitor`);
      if (!r.ok) return;
      const m = (await r.json()) as MonitorData;
      setMonitor(m);
      // 차트 롤링 버퍼에 현재 %값 누적 (최근 MAX_HISTORY개 유지)
      const s = m.system ?? ({} as SystemData);
      const vramPct =
        s.vram_total_mib && s.vram_used_mib != null
          ? (s.vram_used_mib / s.vram_total_mib) * 100
          : 0;
      const cap = (arr: number[], v: number) => [...arr, v].slice(-MAX_HISTORY);
      setHistory((h) => ({
        cpu: cap(h.cpu, s.cpu_percent ?? 0),
        ram: cap(h.ram, s.ram_percent ?? 0),
        gpu: cap(h.gpu, s.gpu_percent ?? 0),
        vram: cap(h.vram, vramPct),
      }));
    } catch {
      /* 모니터 폴링 실패는 조용히 무시 */
    }
  }, []);

  // 진입 시 자동으로 한 번 로드 (새로고침 버튼을 누르지 않아도 데이터 표시)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  // 실시간 모니터링: /monitor(경량) 를 3초 간격으로 폴링 (CPU/GPU/Qdrant/Ollama)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadMonitor();
    const t = setInterval(() => void loadMonitor(), MONITOR_POLL_MS);
    return () => clearInterval(t);
  }, [loadMonitor]);

  // 작업 실행 중에는 1.5초마다 자동 폴링해 단계 진행상황을 갱신 (평소엔 수동 새로고침)
  useEffect(() => {
    const running = data && Object.values(data.jobs).some((j) => j.status === "running");
    if (!running) return;
    const t = setInterval(() => void load(), 1500);
    return () => clearInterval(t);
  }, [data, load]);

  async function startJob(job: string) {
    const r = await fetch(`${API_BASE}/api/admin/jobs/${encodeURIComponent(job)}`, {
      method: "POST",
    });
    if (!r.ok) {
      const body = (await r.json().catch(() => ({}))) as { detail?: string };
      throw new Error(body.detail ?? `HTTP ${r.status}`);
    }
    // 곧바로 한 번 로드해 실행 상태를 띄우면 위 폴링이 이어받음
    setTimeout(() => void load(), 600);
  }

  return (
    <main className="flex-1 flex flex-col w-full min-h-0">
      {/* 상단 고정 헤더 (채팅과 동일한 공용 헤더) */}
      <AppHeader
        active="admin"
        actions={
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="ml-1 px-2.5 py-1 text-xs rounded border border-neutral-700 hover:bg-neutral-800 disabled:opacity-50"
          >
            {loading ? "로딩…" : "↻ 새로고침"}
          </button>
        }
      />

      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-8">
        {error && (
          <div className="rounded border border-red-500/40 bg-red-500/10 px-4 py-3 text-base text-red-400">
            API 연결 실패: {error}
          </div>
        )}

        {/* 모니터링 — 실시간(3초) */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">
            모니터링 <span className="text-xs font-normal text-neutral-500">· 실시간 (1초)</span>
          </h2>
          {/* 시스템·Qdrant·Ollama: 넓으면 3열로 가로 꽉 채움, 좁으면 세로 스택. 등높이 카드 */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 items-stretch">
            <SystemSection sys={monitor?.system} history={history} />
            <QdrantSection
              data={monitor?.qdrant ?? data?.qdrant ?? { available: false, collections: [] }}
            />
            <OllamaSection
              data={
                monitor?.ollama ?? data?.ollama ?? { available: false, models: [], running_count: 0 }
              }
            />
          </div>
        </section>

        {/* 인덱싱 작업 */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">
            인덱싱 작업{" "}
            <span className="text-xs font-normal text-neutral-500">
              {lastRefresh ? `· 갱신 ${lastRefresh.toLocaleTimeString("ko-KR")}` : ""}
            </span>
          </h2>
          {data ? (
            <>
              <SqliteSection data={data.sqlite} />
              <IndexerSection data={data.indexer} jobs={data.jobs} onStartJob={startJob} />
            </>
          ) : (
            <div className="text-base text-neutral-400 animate-pulse">데이터 로딩 중…</div>
          )}
        </section>
      </div>
    </main>
  );
}
