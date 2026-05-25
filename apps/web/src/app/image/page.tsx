"use client";

import { useState } from "react";
import AppHeader from "../_components/AppHeader";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ai.kamoru.jk:8000";

type Hit = {
  opus: string;
  title?: string;
  studio?: string;
  year?: number;
  canonical_actresses?: string[];
  score?: number;
  kind?: string;
  playable?: boolean;
};

function PosterCard({ h }: { h: Hit }) {
  const poster = `${API_BASE}/static/posters/${encodeURIComponent(h.opus)}`;
  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={poster}
        alt={h.opus}
        loading="lazy"
        className="w-full aspect-[400/269] object-cover bg-muted"
        onError={(e) => {
          (e.currentTarget as HTMLImageElement).style.display = "none";
        }}
      />
      <div className="p-2 text-xs">
        <div className="flex items-center justify-between">
          <span className="font-mono text-foreground">{h.opus}</span>
          {typeof h.score === "number" && (
            <span className="text-emerald-400 tabular-nums">{h.score.toFixed(3)}</span>
          )}
        </div>
        {h.title && <div className="mt-1 line-clamp-2 text-foreground">{h.title}</div>}
        <div className="mt-1 text-muted-foreground flex gap-2 flex-wrap">
          {h.studio && <span>{h.studio}</span>}
          {h.year && <span>{h.year}</span>}
          {h.kind && (
            <span className={h.kind === "instance" ? "text-emerald-400" : "text-muted-foreground"}>
              {h.kind}
            </span>
          )}
        </div>
        {h.canonical_actresses && h.canonical_actresses.length > 0 && (
          <div className="mt-1 text-muted-foreground">{h.canonical_actresses.join(", ")}</div>
        )}
      </div>
    </div>
  );
}

export default function ImageSearchPage() {
  const [tab, setTab] = useState<"text" | "image">("text");
  const [query, setQuery] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [items, setItems] = useState<Hit[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [kind, setKind] = useState<"" | "instance" | "archive">("");

  async function searchText() {
    if (!query.trim()) return;
    setBusy(true);
    setErr(null);
    setItems([]);
    setElapsed(null);
    const t0 = performance.now();
    try {
      const r = await fetch(`${API_BASE}/api/image/search/text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, limit: 24, kind: kind || null }),
      });
      if (!r.ok) throw new Error(await r.text());
      const j = await r.json();
      setItems(j.items ?? []);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setElapsed(Math.round(performance.now() - t0));
      setBusy(false);
    }
  }

  async function searchImage() {
    if (!file) return;
    setBusy(true);
    setErr(null);
    setItems([]);
    setElapsed(null);
    const t0 = performance.now();
    try {
      const fd = new FormData();
      fd.append("file", file);
      const url = `${API_BASE}/api/image/search?limit=24${kind ? `&kind=${kind}` : ""}`;
      const r = await fetch(url, { method: "POST", body: fd });
      if (!r.ok) throw new Error(await r.text());
      const j = await r.json();
      setItems(j.items ?? []);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setElapsed(Math.round(performance.now() - t0));
      setBusy(false);
    }
  }

  function onPick(f: File | null) {
    setFile(f);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(f ? URL.createObjectURL(f) : null);
  }

  return (
    <div className="flex-1 flex flex-col">
      <AppHeader active="image" />

      <div className="px-4 py-3 border-b border-border space-y-3">
        <div className="flex gap-2 text-sm">
          <button
            className={`px-3 py-1 rounded ${tab === "text" ? "bg-emerald-600" : "bg-muted"}`}
            onClick={() => setTab("text")}
          >
            텍스트 → 포스터
          </button>
          <button
            className={`px-3 py-1 rounded ${tab === "image" ? "bg-emerald-600" : "bg-muted"}`}
            onClick={() => setTab("image")}
          >
            이미지 → 포스터
          </button>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as "" | "instance" | "archive")}
            className="ml-auto px-2 py-1 bg-muted rounded text-xs"
          >
            <option value="">전체</option>
            <option value="instance">instance</option>
            <option value="archive">archive</option>
          </select>
        </div>

        {tab === "text" ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              searchText();
            }}
            className="flex gap-2"
          >
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder='e.g. "school uniform on beach", "검은 드레스의 여자"'
              className="flex-1 px-3 py-2 bg-card border border-border rounded text-sm"
            />
            <button
              type="submit"
              disabled={busy || !query.trim()}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-muted rounded text-sm"
            >
              검색
            </button>
          </form>
        ) : (
          <div className="flex gap-3 items-start">
            <input
              type="file"
              accept="image/*"
              onChange={(e) => onPick(e.target.files?.[0] ?? null)}
              className="text-sm"
            />
            {preview && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={preview} alt="preview" className="h-24 rounded border border-border" />
            )}
            <button
              onClick={searchImage}
              disabled={busy || !file}
              className="ml-auto px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-muted rounded text-sm"
            >
              유사 포스터 검색
            </button>
          </div>
        )}

        <div className="text-xs text-muted-foreground">
          {busy && <span>검색 중…</span>}
          {!busy && elapsed !== null && (
            <span>
              {items.length}건 · {elapsed} ms
            </span>
          )}
          {err && <span className="text-red-400 ml-3">{err}</span>}
        </div>
      </div>

      <main className="flex-1 overflow-y-auto p-4">
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {items.map((h) => (
            <PosterCard key={h.opus} h={h} />
          ))}
        </div>
      </main>
    </div>
  );
}
