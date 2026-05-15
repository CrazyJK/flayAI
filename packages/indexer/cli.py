"""flay-index CLI (typer).

서브커맨드:
  load     -- K:/Crazy/Info/*.json → SQLite
  scan     -- 포스터 디렉토리 스캔 + classify (instance/archive)
  history  -- history.csv → SQLite
  fts      -- videos_fts 재구축
  all      -- load → scan → history → fts 순차 실행
  status   -- state.json 요약
"""
from __future__ import annotations

import json
import logging
import sys
import time

import typer

from packages.indexer import history as history_mod
from packages.indexer import load_jsons as load_mod
from packages.indexer import poster_scanner as scan_mod
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
def load(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """JSON ETL."""
    _setup_log(verbose)
    t = time.time()
    stats = load_mod.run()
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
    """load → scan → history → fts 순차 실행."""
    _setup_log(verbose)
    load(verbose)
    scan(verbose)
    history(verbose)
    fts(verbose)


@app.command()
def status() -> None:
    """state.json 요약."""
    _print("state", load_state())


if __name__ == "__main__":
    app()
