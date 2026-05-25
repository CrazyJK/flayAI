"use client";

import { useState } from "react";
import AppHeader from "../_components/AppHeader";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ai.kamoru.jk:8000";

type Actress = { name: string; votes: number; best_score: number };
type Neighbor = {
  opus: string;
  face_idx: number;
  cluster_id: number | null;
  score: number;
  actresses: string[];
};

type SearchResult = {
  actresses: Actress[];
  neighbors: Neighbor[];
  faces_detected?: number;
  elapsed_ms?: number;
  message?: string;
};

export default function FaceSearchPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [res, setRes] = useState<SearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function onPick(f: File | null) {
    setFile(f);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(f ? URL.createObjectURL(f) : null);
    setRes(null);
  }

  async function go() {
    if (!file) return;
    setBusy(true);
    setErr(null);
    setRes(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch(`${API_BASE}/api/face/search?top_k=10&face_neighbors=80`, {
        method: "POST",
        body: fd,
      });
      if (!r.ok) throw new Error(await r.text());
      setRes(await r.json());
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex-1 flex flex-col">
      <AppHeader active="face" />

      <div className="px-4 py-3 border-b border-border flex gap-3 items-start">
        <input
          type="file"
          accept="image/*"
          onChange={(e) => onPick(e.target.files?.[0] ?? null)}
          className="text-sm"
        />
        {preview && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={preview} alt="preview" className="h-32 rounded border border-border" />
        )}
        <button
          onClick={go}
          disabled={busy || !file}
          className="ml-auto px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground disabled:bg-muted disabled:text-muted-foreground rounded text-sm"
        >
          배우 추정
        </button>
      </div>

      <main className="flex-1 overflow-y-auto p-4 space-y-4">
        {busy && <div className="text-sm text-muted-foreground">분석 중…</div>}
        {err && <div className="text-sm text-destructive">{err}</div>}

        {res && (
          <>
            <div className="text-xs text-muted-foreground">
              얼굴 {res.faces_detected ?? 0}개 검출 · {res.elapsed_ms} ms
              {res.message && <span className="text-amber-400 ml-2">{res.message}</span>}
            </div>

            <section>
              <h2 className="text-sm font-semibold mb-2">Top {res.actresses.length} 배우</h2>
              {res.actresses.length === 0 ? (
                <div className="text-sm text-muted-foreground">매칭되는 배우 없음</div>
              ) : (
                <ol className="space-y-1 text-sm">
                  {res.actresses.map((a, i) => (
                    <li key={a.name} className="flex items-center gap-3">
                      <span className="w-6 tabular-nums text-muted-foreground">{i + 1}.</span>
                      <span className="flex-1">{a.name}</span>
                      <span className="text-muted-foreground tabular-nums">{a.votes}표</span>
                      <span className="text-success tabular-nums w-16 text-right">
                        {a.best_score.toFixed(3)}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </section>

            <section>
              <h2 className="text-sm font-semibold mb-2">가까운 얼굴 (상위 10)</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                {res.neighbors.map((n, i) => (
                  <a
                    key={i}
                    href={`${API_BASE}/static/posters/${encodeURIComponent(n.opus)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded border border-border overflow-hidden bg-card block"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={`${API_BASE}/static/posters/${encodeURIComponent(n.opus)}`}
                      alt={n.opus}
                      loading="lazy"
                      className="w-full aspect-[400/269] object-cover bg-muted"
                    />
                    <div className="p-1.5 text-xs">
                      <div className="font-mono">{n.opus}</div>
                      <div className="flex justify-between text-muted-foreground">
                        <span>c{n.cluster_id ?? "-"}</span>
                        <span className="text-success">{n.score.toFixed(3)}</span>
                      </div>
                      <div className="text-muted-foreground line-clamp-2 leading-snug">
                        {n.actresses?.join(", ")}
                      </div>
                    </div>
                  </a>
                ))}
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
