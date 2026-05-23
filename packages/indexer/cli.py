"""flay-index CLI (typer).

서브커맨드:
  load          -- K:/Crazy/Info/*.json → SQLite (기본 증분 UPSERT; --rebuild 면 전체 재적재)
  scan          -- 포스터 디렉토리 스캔 + classify (instance/archive)
  history       -- history.csv → SQLite
  fts           -- videos_fts 재구축
  all           -- load → scan → history → fts 순차 실행
  refresh       -- 증분 갱신: load → scan → history → fts → sync-payload (파생 데이터 보존)
  rebuild       -- 전체 재구축: load --rebuild → scan → history → fts → sync-payload (파생 데이터 초기화)
  translate     -- JP→KO 번역 (NLLB-200)
  embed         -- bge-m3 → Qdrant videos
  embed-clip    -- OpenCLIP ViT-L/14 → Qdrant posters_clip
  extract-faces -- InsightFace buffalo_l → poster_faces + Qdrant faces
  cluster-faces -- 얼굴 클러스터링(mutual-kNN + Union-Find) + 배우 자동 매핑
  ocr-posters   -- RapidOCR(onnx) → posters.ocr_text + Qdrant poster_ocr
  caption-posters -- VLM(gemma-4) → posters.caption (검색용 장면 설명; embed 로 반영)
  sync-payload  -- SQLite kind/playable 변경분을 Qdrant payload 에 반영
  cleanup       -- 고아 row/point 정리 (dry-run 기본)
  status        -- state.json 요약
"""

from __future__ import annotations

import json
import logging
import sys
import time

import typer

from packages.indexer import caption_posters as caption_mod
from packages.indexer import cleanup as cleanup_mod
from packages.indexer import cluster_faces as cluster_mod
from packages.indexer import embed_clip as embed_clip_mod
from packages.indexer import embed_text as embed_mod
from packages.indexer import faces as faces_mod
from packages.indexer import history as history_mod
from packages.indexer import load_jsons as load_mod
from packages.indexer import ocr as ocr_mod
from packages.indexer import poster_scanner as scan_mod
from packages.indexer import sync_payload as sync_mod
from packages.indexer import translate as translate_mod
from packages.indexer.db import connect, fts_rebuild, init_schema
from packages.indexer.state import load_state

app = typer.Typer(add_completion=False, help="flayAI indexer CLI")


def _setup_log(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )


def _print(title: str, payload: dict | object) -> None:
    typer.echo(f"[{title}]")
    if hasattr(payload, "__dict__"):
        payload = payload.__dict__
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command()
def load(
    rebuild: bool = typer.Option(
        False, "--rebuild", help="전체 재적재(번역 등 파생 데이터 초기화). 기본은 증분 UPSERT"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """JSON ETL. 기본은 증분(UPSERT)으로 title_ko/desc_ko 보존. --rebuild 면 전체 재적재."""
    _setup_log(verbose)
    t = time.time()
    stats = load_mod.run(rebuild=rebuild)
    stats["elapsed_sec"] = round(time.time() - t, 2)
    _print("load_jsons", stats)


@app.command()
def scan(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """포스터 스캔 + classify."""
    _setup_log(verbose)
    t = time.time()
    stats = scan_mod.run()
    out = {**stats.__dict__, "elapsed_sec": round(time.time() - t, 2)}
    if stats.scanned:
        out["match_rate"] = round(stats.matched / stats.scanned, 4)
    _print("scan_posters", out)


@app.command()
def history(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """history.csv ingest."""
    _setup_log(verbose)
    t = time.time()
    stats = history_mod.run()
    out = {**stats.__dict__, "elapsed_sec": round(time.time() - t, 2)}
    _print("history_csv", out)


@app.command()
def fts(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """videos_fts 재구축."""
    _setup_log(verbose)
    conn = connect()
    init_schema(conn)
    t = time.time()
    fts_rebuild(conn)
    n = conn.execute("SELECT COUNT(*) FROM videos_fts").fetchone()[0]
    conn.close()
    _print("fts", {"rows": n, "elapsed_sec": round(time.time() - t, 2)})


@app.command()
def all(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """load(증분) → scan → history → fts 순차 실행."""
    _setup_log(verbose)
    load(rebuild=False, verbose=verbose)
    scan(verbose)
    history(verbose)
    fts(verbose)


@app.command()
def refresh(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """증분 갱신: load(증분) → scan → history → fts → sync-payload.

    신규 영상 추가 · instance↔archive 이동 · JSON/CSV 수정을 한 번에 반영한다.
    번역(title_ko/desc_ko) 등 파생 데이터는 보존된다.
    """
    _setup_log(verbose)
    load(rebuild=False, verbose=verbose)
    scan(verbose)
    history(verbose)
    fts(verbose)
    sync_payload(verbose)


@app.command()
def rebuild(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """전체 재구축: load(--rebuild) → scan → history → fts → sync-payload.

    videos 를 처음부터 재적재하므로 title_ko/desc_ko 등 파생 데이터가 초기화된다.
    번역·임베딩 등은 이후 다시 실행해야 한다.
    """
    _setup_log(verbose)
    load(rebuild=True, verbose=verbose)
    scan(verbose)
    history(verbose)
    fts(verbose)
    sync_payload(verbose)


@app.command()
def translate(
    limit: int = typer.Option(0, "--limit", "-n", help="0이면 전체"),
    force: bool = typer.Option(False, "--force", help="이미 번역된 것도 다시"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """JP→KO 번역 (videos.title_ko / desc_ko)."""
    _setup_log(verbose)
    t = time.time()
    out = translate_mod.run(limit=limit or None, force=force)
    out["elapsed_sec"] = round(time.time() - t, 2)
    _print("translate", out)


@app.command()
def embed(
    limit: int = typer.Option(0, "--limit", "-n", help="0이면 전체"),
    batch_size: int = typer.Option(0, "--batch-size", "-b"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """bge-m3 → Qdrant videos 컬렉션 upsert."""
    _setup_log(verbose)
    t = time.time()
    out = embed_mod.run(limit=limit or None, batch_size=batch_size or None)
    out["elapsed_sec"] = round(time.time() - t, 2)
    _print("embed_text", out)


@app.command(name="embed-clip")
def embed_clip(
    limit: int = typer.Option(0, "--limit", "-n", help="0이면 전체"),
    batch_size: int = typer.Option(0, "--batch-size", "-b"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """OpenCLIP ViT-L/14 → Qdrant posters_clip 컬렉션 upsert."""
    _setup_log(verbose)
    t = time.time()
    out = embed_clip_mod.run(limit=limit or None, batch_size=batch_size or None)
    out["elapsed_sec"] = round(time.time() - t, 2)
    _print("embed_clip", out)


@app.command(name="extract-faces")
def extract_faces(
    limit: int = typer.Option(0, "--limit", "-n", help="0이면 전체"),
    rebuild: bool = typer.Option(False, "--rebuild", help="이미 처리한 포스터도 재처리"),
    det_threshold: float = typer.Option(0.5, "--det-threshold"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """InsightFace buffalo_l → poster_faces + Qdrant faces 컬렉션."""
    _setup_log(verbose)
    t = time.time()
    out = faces_mod.run(
        limit=limit or None,
        only_missing=not rebuild,
        det_score_threshold=det_threshold,
    )
    out["elapsed_sec"] = round(time.time() - t, 2)
    _print("extract_faces", out)


@app.command(name="cluster-faces")
def cluster_faces(
    min_cluster_size: int = typer.Option(0, "--min-cluster-size"),
    min_samples: int = typer.Option(0, "--min-samples"),
    confidence: float = typer.Option(0.0, "--confidence", "-c", help="0이면 config 기본값"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """얼굴 클러스터링(mutual-kNN + Union-Find) → face_clusters + cluster_id + 배우 자동 매핑."""
    _setup_log(verbose)
    t = time.time()
    out = cluster_mod.run(
        min_cluster_size=min_cluster_size or None,
        min_samples=min_samples or None,
        confidence_threshold=confidence or None,
    )
    out["elapsed_sec"] = round(time.time() - t, 2)
    _print("cluster_faces", out)


@app.command(name="ocr-posters")
def ocr_posters(
    limit: int = typer.Option(0, "--limit", "-n", help="0이면 전체"),
    force: bool = typer.Option(False, "--force", help="이미 OCR된 포스터도 재처리"),
    embed_batch: int = typer.Option(16, "--embed-batch"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """RapidOCR(ONNX) → posters.ocr_text + Qdrant poster_ocr 컬렉션."""
    _setup_log(verbose)
    t = time.time()
    out = ocr_mod.run(limit=limit or None, force=force, embed_batch=embed_batch)
    out["elapsed_sec"] = round(time.time() - t, 2)
    _print("ocr_posters", out)


@app.command(name="caption-posters")
def caption_posters(
    limit: int = typer.Option(0, "--limit", "-n", help="0이면 전체"),
    force: bool = typer.Option(False, "--force", help="이미 캡션된 포스터도 재생성"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """VLM(config.models.vision, 예: gemma-4) → posters.caption (검색용 장면 설명).

    생성된 캡션은 이후 `embed` 단계에서 videos 임베딩의 [장면] 블록으로 반영된다.
    """
    _setup_log(verbose)
    t = time.time()
    out = caption_mod.run(limit=limit or None, force=force)
    out["elapsed_sec"] = round(time.time() - t, 2)
    _print("caption_posters", out)


@app.command(name="sync-payload")
def sync_payload(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """SQLite videos.kind / playable 변경분을 Qdrant 4 컬렉션 payload 에 반영.

    벡터 재계산 없이 set_payload 만 호출 (수십~수백배 빠름).
    """
    _setup_log(verbose)
    out = sync_mod.run()
    _print("sync_payload", out)


@app.command()
def cleanup(
    apply: bool = typer.Option(False, "--apply", help="실제 삭제 적용 (기본은 dry-run)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """고아 row/point 정리 (SQLite + Qdrant 4 컬렉션).

    탐지 대상:
      1) posters.path 의 파일이 실제 없음
      2) videos 의 JSON({info_dir}/{opus}.json) 이 실제 없음
      3) Qdrant 에는 있는데 SQLite videos 에 없는 opus
    """
    _setup_log(verbose)
    out = cleanup_mod.run(apply=apply)
    _print("cleanup", out)


@app.command()
def status() -> None:
    """state.json 요약."""
    _print("state", load_state())


if __name__ == "__main__":
    app()
