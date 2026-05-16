"use client";

import { useCallback, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

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
  title: string | null;
  studio: string | null;
  year: number | null;
  actresses: string[];
};

type Detail = { cluster: Cluster; samples: Sample[] };

function ClusterDetail({ id, onLabeled }: { id: number; onLabeled: () => void }) {
  const [d, setD] = useState<Detail | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancel = false;
    setD(null);
    fetch(`${API_BASE}/api/face/clusters/${id}/samples?limit=12`)
      .then((r) => r.json())
      .then((j) => { if (!cancel) { setD(j); setName(j.cluster?.canonical_name ?? ""); } });
    return () => { cancel = true; };
  }, [id]);

  async function save(clear = false) {
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/face/clusters/${id}/label`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          canonical_name: clear ? null : (name.trim() || null),
          confidence: clear ? null : 1.0,
        }),
      });
      onLabeled();
    } finally { setBusy(false); }
  }

  if (!d) return <div className="text-sm text-neutral-500 p-4">로딩…</div>;

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <h2 className="text-base font-semibold">
          cluster #{d.cluster.cluster_id} · {d.cluster.sample_count}장
        </h2>
        {d.cluster.canonical_name && (
          <span className="px-2 py-0.5 text-xs bg-emerald-600/30 text-emerald-300 rounded">
            {d.cluster.canonical_name}
            {d.cluster.confidence != null && (
              <span className="ml-1 text-neutral-400">
                ({d.cluster.confidence.toFixed(2)})
              </span>
            )}
          </span>
        )}
      </div>

      <div className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="배우 canonical_name (예: 三上悠亜)"
          className="flex-1 px-3 py-2 bg-neutral-900 border border-neutral-800 rounded text-sm"
        />
        <button
          disabled={busy}
          onClick={() => save(false)}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-neutral-700 rounded text-sm"
        >저장</button>
        <button
          disabled={busy}
          onClick={() => save(true)}
          className="px-3 py-2 bg-neutral-800 hover:bg-neutral-700 rounded text-sm"
        >해제</button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
        {d.samples.map((s) => (
          <a
            key={`${s.poster_opus}-${s.face_idx}`}
            href={`${API_BASE}/static/posters/${encodeURIComponent(s.poster_opus)}`}
            target="_blank" rel="noreferrer"
            className="rounded border border-neutral-800 overflow-hidden bg-neutral-900 block"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${API_BASE}/static/posters/${encodeURIComponent(s.poster_opus)}`}
              alt={s.poster_opus}
              loading="lazy"
              className="w-full h-32 object-cover bg-neutral-800"
            />
            <div className="p-1.5 text-xs">
              <div className="font-mono">{s.poster_opus}</div>
              <div className="text-neutral-400 truncate">{s.actresses?.join(", ")}</div>
            </div>
          </a>
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
      url.searchParams.set("min_size", String(minSize));
      const r = await fetch(url.toString());
      const j = await r.json();
      setItems(j.items ?? []);
      setTotal(j.total ?? 0);
    } finally { setBusy(false); }
  }, [offset, onlyUnlabeled, minSize]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="flex-1 flex flex-col">
      <header className="px-4 py-3 border-b border-neutral-800 flex items-center gap-3">
        <h1 className="text-base font-semibold">얼굴 클러스터 라벨링</h1>
        <nav className="flex gap-2 text-xs">
          <a href="/" className="text-neutral-400 hover:text-neutral-200">채팅</a>
          <a href="/image" className="text-neutral-400 hover:text-neutral-200">이미지</a>
          <a href="/face" className="text-neutral-400 hover:text-neutral-200">얼굴</a>
          <a href="/labels" className="text-neutral-200">라벨링</a>
        </nav>
        <span className="ml-auto text-xs text-neutral-500">{total} clusters</span>
      </header>

      <div className="px-4 py-2 border-b border-neutral-800 flex items-center gap-3 text-xs">
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={onlyUnlabeled}
                 onChange={(e) => { setOffset(0); setOnlyUnlabeled(e.target.checked); }} />
          unlabeled만
        </label>
        <label className="flex items-center gap-1">
          min size:
          <input type="number" min={1} value={minSize}
                 onChange={(e) => { setOffset(0); setMinSize(parseInt(e.target.value) || 1); }}
                 className="w-16 px-2 py-0.5 bg-neutral-900 border border-neutral-800 rounded" />
        </label>
        <div className="ml-auto flex gap-2">
          <button disabled={busy || offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  className="px-2 py-0.5 bg-neutral-800 hover:bg-neutral-700 disabled:opacity-30 rounded">←</button>
          <span className="tabular-nums text-neutral-500">
            {offset + 1}-{Math.min(offset + limit, total)} / {total}
          </span>
          <button disabled={busy || offset + limit >= total}
                  onClick={() => setOffset(offset + limit)}
                  className="px-2 py-0.5 bg-neutral-800 hover:bg-neutral-700 disabled:opacity-30 rounded">→</button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <aside className="w-64 border-r border-neutral-800 overflow-y-auto">
          <ul className="text-sm">
            {items.map((c) => (
              <li key={c.cluster_id}>
                <button
                  onClick={() => setSelected(c.cluster_id)}
                  className={`w-full text-left px-3 py-2 hover:bg-neutral-900 border-b border-neutral-900
                    ${selected === c.cluster_id ? "bg-neutral-900" : ""}`}
                >
                  <div className="flex justify-between">
                    <span className="font-mono text-neutral-400">#{c.cluster_id}</span>
                    <span className="text-neutral-500 tabular-nums">{c.sample_count}</span>
                  </div>
                  <div className={c.canonical_name ? "text-emerald-300" : "text-neutral-500 italic"}>
                    {c.canonical_name ?? "(unlabeled)"}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <section className="flex-1 overflow-y-auto">
          {selected ? (
            <ClusterDetail id={selected} onLabeled={load} />
          ) : (
            <div className="p-6 text-sm text-neutral-500">왼쪽에서 클러스터를 선택하세요.</div>
          )}
        </section>
      </div>
    </div>
  );
}
