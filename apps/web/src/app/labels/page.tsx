"use client";

import { useCallback, useEffect, useState } from "react";
import AppHeader from "../_components/AppHeader";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ai.kamoru.jk:8000";

type Cluster = {
  cluster_id: number;
  canonical_name: string | null;
  sample_count: number;
  confidence: number | null;
};

type Sample = {
  poster_opus: string;
  face_idx: number;
  bbox: string | null;
  title_ko: string | null;
  title_jp: string | null;
  studio: string | null;
  release_year: number | null;
  release_month: number | null;
  actresses: string[];
};

type Detail = { cluster: Cluster; samples: Sample[] };

/** samples의 actresses에서 가장 많이 등장하는 이름 반환 */
function suggestName(samples: Sample[]): string {
  const freq: Record<string, number> = {};
  for (const s of samples) {
    for (const a of s.actresses ?? []) {
      const t = a.trim();
      if (t) freq[t] = (freq[t] ?? 0) + 1;
    }
  }
  const entries = Object.entries(freq);
  if (!entries.length) return "";
  return entries.sort((a, b) => b[1] - a[1])[0][0];
}

function ClusterDetail({ id, onLabeled }: { id: number; onLabeled: () => void }) {
  const [d, setD] = useState<Detail | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancel = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setD(null);
    setError(null);
    fetch(`${API_BASE}/api/face/clusters/${id}/samples?limit=12`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => {
        if (!cancel) {
          setD(j);
          // 이미 라벨이 있으면 그대로, 없으면 포스터 actresses 빈도로 추천
          setName(j.cluster?.canonical_name ?? suggestName(j.samples ?? []));
        }
      })
      .catch((e: unknown) => {
        if (!cancel) setError((e as Error).message ?? "로드 실패");
      });
    return () => {
      cancel = true;
    };
  }, [id]);

  async function save(clear = false) {
    setError(null);
    setBusy(true);
    try {
      const r = await fetch(`${API_BASE}/api/face/clusters/${id}/label`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          canonical_name: clear ? null : name.trim() || null,
          confidence: clear ? null : 1.0,
        }),
      });
      if (!r.ok) throw new Error(`저장 실패: HTTP ${r.status}`);
      onLabeled();
    } catch (e: unknown) {
      setError((e as Error).message ?? "저장 실패");
    } finally {
      setBusy(false);
    }
  }

  async function exclude(s: Sample) {
    setError(null);
    setBusy(true);
    try {
      const r = await fetch(
        `${API_BASE}/api/face/clusters/${id}/samples/${encodeURIComponent(s.poster_opus)}/${s.face_idx}`,
        { method: "DELETE" }
      );
      if (!r.ok) throw new Error(`제외 실패: HTTP ${r.status}`);
      // 로컬 상태에서 해당 카드 제거
      setD((prev) =>
        prev
          ? {
              ...prev,
              samples: prev.samples.filter(
                (x) => x.poster_opus !== s.poster_opus || x.face_idx !== s.face_idx
              ),
            }
          : prev
      );
    } catch (e: unknown) {
      setError((e as Error).message ?? "제외 실패");
    } finally {
      setBusy(false);
    }
  }

  if (!d && error) return <div className="text-sm text-destructive p-4">⚠ {error}</div>;
  if (!d) return <div className="text-sm text-muted-foreground p-4">로딩…</div>;

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <h2 className="text-base font-semibold">
          cluster #{d.cluster.cluster_id} · {d.cluster.sample_count}장
        </h2>
        {d.cluster.canonical_name && (
          <span className="px-2 py-0.5 text-xs bg-success/15 text-success rounded">
            {d.cluster.canonical_name}
            {d.cluster.confidence != null && (
              <span className="ml-1 text-muted-foreground">({d.cluster.confidence.toFixed(2)})</span>
            )}
          </span>
        )}
      </div>

      {error && (
        <div className="px-3 py-2 text-xs rounded bg-destructive/10 border border-destructive/30 text-destructive">
          ⚠ {error}
        </div>
      )}

      <div className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="배우 canonical_name (예: mikami yua)"
          className="flex-1 px-3 py-2 bg-card border border-border rounded-full text-sm"
        />
        <button
          disabled={busy}
          onClick={() => save(false)}
          className="px-[22px] py-[11px] bg-primary hover:bg-primary/90 text-primary-foreground disabled:bg-muted disabled:text-muted-foreground rounded-full text-sm active:scale-95 transition-transform"
        >
          저장
        </button>
        <button
          disabled={busy}
          onClick={() => save(true)}
          className="px-4 py-[11px] bg-muted hover:bg-accent border border-border rounded-lg text-sm active:scale-95 transition-transform"
        >
          해제
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
        {d.samples.map((s) => (
          <div
            key={`${s.poster_opus}-${s.face_idx}`}
            className="relative rounded-[18px] border border-border overflow-hidden bg-card"
          >
            {/* 포스터 이미지 — 클릭 시 새 탭 */}
            <a
              href={`${API_BASE}/static/posters/${encodeURIComponent(s.poster_opus)}`}
              target="_blank"
              rel="noreferrer"
              className="block"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${API_BASE}/static/posters/${encodeURIComponent(s.poster_opus)}`}
                alt={s.poster_opus}
                loading="lazy"
                className="w-full aspect-[400/269] object-cover bg-muted"
              />
            </a>
            <div className="p-1.5 text-xs">
              <div className="font-mono">{s.poster_opus}</div>
              <div className="text-muted-foreground truncate">{s.actresses?.join(", ")}</div>
            </div>
            {/* 제외 버튼 */}
            <button
              disabled={busy}
              onClick={() => exclude(s)}
              title="이 포스터를 클러스터에서 제외"
              className="absolute top-1 right-1 w-5 h-5 flex items-center justify-center
                         rounded-full bg-black/60 text-white/80 hover:bg-red-600 hover:text-white
                         text-[11px] leading-none disabled:opacity-40"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function LabelsPage() {
  const [items, setItems] = useState<Cluster[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const [onlyUnlabeled, setOnlyUnlabeled] = useState(false);
  const [hasInstance, setHasInstance] = useState(false);
  const [minSize, setMinSize] = useState(3);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const url = new URL(`${API_BASE}/api/face/clusters`);
      url.searchParams.set("limit", String(limit));
      url.searchParams.set("offset", String(offset));
      url.searchParams.set("only_unlabeled", onlyUnlabeled ? "true" : "false");
      url.searchParams.set("has_instance", hasInstance ? "true" : "false");
      url.searchParams.set("min_size", String(minSize));
      const r = await fetch(url.toString());
      const j = await r.json();
      setItems(j.items ?? []);
      setTotal(j.total ?? 0);
    } finally {
      setBusy(false);
    }
  }, [offset, onlyUnlabeled, hasInstance, minSize]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  return (
    <div className="h-screen flex flex-col">
      <AppHeader active="labels" />

      <div className="px-4 py-2 border-b border-border flex items-center gap-3 text-xs">
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            checked={onlyUnlabeled}
            onChange={(e) => {
              setOffset(0);
              setOnlyUnlabeled(e.target.checked);
            }}
          />
          unlabeled만
        </label>
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            checked={hasInstance}
            onChange={(e) => {
              setOffset(0);
              setHasInstance(e.target.checked);
            }}
          />
          instance만
        </label>
        <label className="flex items-center gap-1">
          min size:
          <input
            type="number"
            min={1}
            value={minSize}
            onChange={(e) => {
              setOffset(0);
              setMinSize(parseInt(e.target.value) || 1);
            }}
            className="w-16 px-2 py-0.5 bg-card border border-border rounded"
          />
        </label>
        <div className="ml-auto flex gap-2">
          <button
            disabled={busy || offset === 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
            className="px-2 py-0.5 bg-muted hover:bg-accent disabled:opacity-30 rounded"
          >
            ←
          </button>
          <span className="tabular-nums text-muted-foreground">
            {offset + 1}-{Math.min(offset + limit, total)} / {total}
          </span>
          <button
            disabled={busy || offset + limit >= total}
            onClick={() => setOffset(offset + limit)}
            className="px-2 py-0.5 bg-muted hover:bg-accent disabled:opacity-30 rounded"
          >
            →
          </button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <aside className="w-64 border-r border-border overflow-y-auto">
          <ul className="text-sm">
            {items.map((c) => (
              <li key={c.cluster_id}>
                <button
                  onClick={() => setSelected(c.cluster_id)}
                  className={`w-full text-left px-3 py-2 hover:bg-accent border-b border-border
                    ${selected === c.cluster_id ? "bg-card" : ""}`}
                >
                  <div className="flex justify-between">
                    <span className="font-mono text-muted-foreground">#{c.cluster_id}</span>
                    <span className="text-muted-foreground tabular-nums">{c.sample_count}</span>
                  </div>
                  <div
                    className={c.canonical_name ? "text-success" : "text-muted-foreground italic"}
                  >
                    {c.canonical_name ?? "(unlabeled)"}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <section key={selected ?? 0} className="flex-1 overflow-y-auto">
          {selected ? (
            <ClusterDetail id={selected} onLabeled={load} />
          ) : (
            <div className="p-6 text-sm text-muted-foreground">왼쪽에서 클러스터를 선택하세요.</div>
          )}
        </section>
      </div>
    </div>
  );
}
