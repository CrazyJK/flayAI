"use client";

import { useCallback, useEffect, useState } from "react";
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
      {/* 각 카드는 내용(설명) 글자폭에 맞춰 크기 결정 — 말줄임표(…) 없이 전체 표시 */}
      <div className="flex flex-wrap gap-2">
        {data.tables.map((t) => (
          <div key={t.name} className="bg-neutral-900 rounded-lg border border-neutral-800 px-3 py-2">
            <div className="flex items-baseline justify-between gap-4">
              <span className="font-mono text-sm text-neutral-200 whitespace-nowrap">
                {t.name}
                {t.note && <span className="ml-1 text-[10px] text-neutral-500">[{t.note}]</span>}
              </span>
              <span className="font-mono text-sm text-neutral-100 shrink-0">
                {t.count >= 0 ? fmtNum(t.count) : "—"}
              </span>
            </div>
            <div className="text-[11px] text-neutral-500 mt-0.5 whitespace-nowrap">
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
    desc: "K:/Crazy/Info/*.json → SQLite videos (증분; 전체 재구축 시 재적재)",
    metaCount: "videos",
    estText: "~수초",
  },
  {
    job: "scan",
    label: "포스터 스캔",
    group: "메타",
    desc: "포스터 디렉토리 탐색 → instance/archive 분류 + 파일명 한글 제목 백필",
    metaCount: "posters",
    estText: "~수초",
  },
  {
    job: "history",
    label: "히스토리",
    group: "메타",
    desc: "재생 히스토리 CSV → SQLite history",
    metaCount: "all",
    estText: "~1초",
  },
  {
    job: "fts",
    label: "FTS 색인",
    group: "메타",
    desc: "videos_fts5 전문검색 인덱스 재생성 (제목·설명 반영)",
    metaCount: "videos",
    estText: "~1초",
  },
  {
    job: "translate",
    label: "번역",
    group: "AI",
    desc: "JP 제목·설명 → KO (NLLB-200) · 제목은 파일명에서 먼저 채움 · 캐시 적중 시 즉시",
    completedKey: "translate",
    totalKey: "videos",
    secPerItem: 1.2,
  },
  {
    job: "embed",
    label: "텍스트 임베딩",
    group: "AI",
    desc: "영상 텍스트 벡터화 → Qdrant videos (bge-m3) · GPU",
    completedKey: "embed_text",
    totalKey: "videos",
    secPerItem: 0.008,
  },
  {
    job: "embed-clip",
    label: "이미지 임베딩",
    group: "AI",
    desc: "포스터 이미지 벡터화 → Qdrant posters_clip (CLIP ViT-L/14) · GPU",
    completedKey: "embed_clip",
    totalKey: "posters",
    secPerItem: 0.033,
  },
  {
    job: "extract-faces",
    label: "얼굴 추출",
    group: "AI",
    desc: "포스터 얼굴 감지·벡터화 → Qdrant faces (InsightFace buffalo_l) · GPU",
    completedKey: "extract_faces",
    totalKey: "posters",
    secPerItem: 0.23,
  },
  {
    job: "cluster-faces",
    label: "얼굴 클러스터링",
    group: "AI",
    desc: "mutual-kNN + Union-Find로 얼굴 → 배우 단위 그룹화 · GPU",
    estText: "~77초",
  },
  {
    job: "ocr-posters",
    label: "포스터 OCR",
    group: "AI",
    desc: "포스터 텍스트 추출 → Qdrant poster_ocr (RapidOCR) · CPU",
    completedKey: "ocr_posters",
    totalKey: "posters",
    secPerItem: 1.4,
  },
  {
    job: "sync-payload",
    label: "페이로드 동기화",
    group: "메타",
    desc: "SQLite kind/playable → Qdrant 4컬렉션 payload 반영",
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
    // 파괴적 작업은 실행 전 한 번 더 확인
    if (job === "rebuild") {
      const ok = window.confirm(
        "전체 재구축: videos 를 처음부터 재적재합니다.\n" +
          "번역(title_ko/desc_ko) 등 파생 데이터가 모두 초기화되어 다시 번역/임베딩해야 합니다.\n\n" +
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
  const totalPending = Object.values(data.pending).reduce((a, b) => a + b, 0);
  // 전체 최대 소요시간 (AI 단계 대기 × 건당 소요시간 합산)
  const totalEtaSec = PIPELINE.reduce(
    (sum, s) =>
      sum + (s.completedKey ? (data.pending[s.completedKey] ?? 0) * (s.secPerItem ?? 0) : 0),
    0,
  );
  // 메타 단계 대상 건수 (없으면 null)
  const metaCountOf = (s: PipeStage): number | null =>
    s.metaCount === "videos" ? totals.videos : s.metaCount === "posters" ? totals.posters : null;

  return (
    <SectionCard
      title="인덱서"
      badge={
        totalPending > 0
          ? `대기 ${fmtNum(totalPending)} · 최대 ~${fmtDuration(totalEtaSec)}`
          : "모두 완료"
      }
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

      {/* 일괄 작업 (메타 파이프라인 한 번에 실행) */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <JobButton
          job="refresh"
          label="증분 갱신"
          info={jobs["refresh"]}
          busy={busy}
          onStart={(j) => void handleStart(j)}
          onToggleLog={toggleLog}
          expanded={false}
        />
        <JobButton
          job="rebuild"
          label="⚠ 전체 재구축"
          info={jobs["rebuild"]}
          busy={busy}
          onStart={(j) => void handleStart(j)}
          onToggleLog={toggleLog}
          expanded={false}
        />
        <span className="text-xs text-neutral-500">
          증분 갱신 = load→scan→history→fts→sync-payload(메타·번역 보존). 전체 재구축은 load 부터
          재적재(확인창).
        </span>
      </div>
      <p className="text-xs text-neutral-500 mb-3">
        ⓘ 시간은 <span className="text-amber-400">최대(상한)</span> 추정 — 실제는 캐시·파일명 제목·GPU
        배치로 보통 더 빠릅니다. 각 단계 버튼으로 개별 실행도 가능합니다.
      </p>

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
                  "rounded-lg border px-3 py-2.5 transition-colors xl:w-[280px] xl:flex xl:flex-col " +
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
              {i < PIPELINE.length - 1 && (
                <div
                  className="flex items-center justify-center text-neutral-600 leading-none py-0.5 xl:px-1 xl:py-0"
                  aria-hidden
                >
                  <span className="xl:hidden">▼</span>
                  <span className="hidden xl:inline">→</span>
                </div>
              )}
            </div>
          );
        })}
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

function Gauge({ label, percent, sub }: { label: string; percent?: number; sub?: string }) {
  const p = percent == null ? null : Math.max(0, Math.min(100, percent));
  const color = p == null ? "bg-neutral-600" : p >= 85 ? "bg-red-500" : p >= 60 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="bg-neutral-900 rounded-lg border border-neutral-800 px-3 py-2 flex-1 min-w-[150px]">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs text-neutral-400 truncate">{label}</span>
        <span className="font-mono text-sm text-neutral-100 shrink-0">{p == null ? "—" : `${p.toFixed(0)}%`}</span>
      </div>
      <div className="mt-1 h-1.5 bg-neutral-700 rounded-full overflow-hidden">
        <div className={"h-full " + color} style={{ width: `${p ?? 0}%` }} />
      </div>
      {sub && <div className="mt-1 text-[11px] text-neutral-500 font-mono">{sub}</div>}
    </div>
  );
}

function SystemMonitor({ sys }: { sys?: SystemData }) {
  if (!sys) return <div className="text-sm text-neutral-500 animate-pulse">시스템 정보 로딩…</div>;
  const gb = (b?: number) => (b == null ? "—" : `${(b / 1e9).toFixed(1)}GB`);
  const mib = (m?: number) => (m == null ? "—" : `${(m / 1024).toFixed(1)}GB`);
  const vramPct =
    sys.vram_total_mib && sys.vram_used_mib != null ? (sys.vram_used_mib / sys.vram_total_mib) * 100 : undefined;
  return (
    <div className="flex flex-wrap gap-2">
      <Gauge label={`CPU${sys.cpu_count ? ` (${sys.cpu_count}코어)` : ""}`} percent={sys.cpu_percent} />
      <Gauge label="RAM" percent={sys.ram_percent} sub={`${gb(sys.ram_used)} / ${gb(sys.ram_total)}`} />
      {sys.gpu_available ? (
        <>
          <Gauge
            label={`GPU${sys.gpu_name ? ` · ${sys.gpu_name.replace("NVIDIA GeForce ", "")}` : ""}`}
            percent={sys.gpu_percent}
            sub={sys.gpu_temp != null ? `${sys.gpu_temp}°C` : undefined}
          />
          <Gauge label="VRAM" percent={vramPct} sub={`${mib(sys.vram_used_mib)} / ${mib(sys.vram_total_mib)}`} />
        </>
      ) : (
        <div className="text-xs text-neutral-500 self-center px-2">GPU 정보 없음</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 메인 페이지
// ---------------------------------------------------------------------------

export default function AdminPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [monitor, setMonitor] = useState<MonitorData | null>(null);
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
      if (r.ok) setMonitor((await r.json()) as MonitorData);
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
    const t = setInterval(() => void loadMonitor(), 3000);
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
            모니터링 <span className="text-xs font-normal text-neutral-500">· 실시간 (3초)</span>
          </h2>
          <SystemMonitor sys={monitor?.system} />
          {/* Qdrant·Ollama: 내용 글자폭 기준 고정폭 — 넓으면 가로, 좁으면 세로(flex-wrap) */}
          <div className="flex flex-wrap gap-3 items-start">
            <div className="w-full md:w-[480px]">
              <QdrantSection
                data={monitor?.qdrant ?? data?.qdrant ?? { available: false, collections: [] }}
              />
            </div>
            <div className="w-full md:w-[460px]">
              <OllamaSection
                data={
                  monitor?.ollama ??
                  data?.ollama ?? { available: false, models: [], running_count: 0 }
                }
              />
            </div>
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
