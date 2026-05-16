"""flayAI 골든셋 평가 러너 (AI_PLAN.md §10 M6, §11.1).

사용:
    python eval/run_eval.py            # 전체
    python eval/run_eval.py -v         # verbose (개별 hit 출력)
    python eval/run_eval.py --id ocr-001
    python eval/run_eval.py --tag actress

각 케이스는 chat API(/api/chat) SSE 호출 후 tool_result.items 를 hits 로 모은다.
ocr_search=true 케이스는 /api/search/poster-ocr 호출.
face_search 케이스는 이미지 존재 여부 확인 후 /api/search/face 호출 (없으면 skip).

결과는 stdout 에 표 형태로 출력하고, JSON 으로 eval/results/{ts}.json 저장.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

BASE = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "eval" / "golden.yaml"
RESULTS_DIR = ROOT / "eval" / "results"

log = logging.getLogger("eval")


# --------------------------------------------------------------------------
#  호출
# --------------------------------------------------------------------------
def _chat_hits(query: str, timeout: float = 120.0) -> tuple[list[dict], float]:
    """POST /api/chat (SSE) → 모든 tool_result.items 합본, first_event_sec 반환."""
    t0 = time.time()
    first_event: float | None = None
    hits: list[dict] = []
    try:
        with httpx.stream("POST", f"{BASE}/api/chat",
                          json={"query": query}, timeout=timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except Exception:
                    continue
                if first_event is None:
                    first_event = time.time() - t0
                if ev.get("type") == "tool_result":
                    res = ev.get("result")
                    items = []
                    if isinstance(res, list):
                        items = res
                    elif isinstance(res, dict):
                        items = res.get("items") or []
                    for it in items:
                        if isinstance(it, dict) and "opus" in it:
                            hits.append(it)
    except Exception as e:
        log.warning("chat call failed: %s", e)
    return hits, first_event or (time.time() - t0)


def _ocr_hits(query: str, limit: int = 10) -> list[dict]:
    try:
        r = httpx.post(f"{BASE}/api/search/poster-ocr",
                       json={"query": query, "limit": limit}, timeout=60)
        r.raise_for_status()
        return r.json().get("items", [])
    except Exception as e:
        log.warning("ocr call failed: %s", e)
        return []


def _face_hits(image_path: str, limit: int = 5) -> list[dict] | None:
    p = ROOT / image_path
    if not p.exists():
        return None
    try:
        with p.open("rb") as f:
            r = httpx.post(f"{BASE}/api/search/face",
                           files={"image": (p.name, f, "image/jpeg")},
                           data={"limit": str(limit)}, timeout=60)
        r.raise_for_status()
        return r.json().get("items", [])
    except Exception as e:
        log.warning("face call failed: %s", e)
        return []


# --------------------------------------------------------------------------
#  검증
# --------------------------------------------------------------------------
def _check(expect: dict, hits: list[dict], all_results: dict[str, list[dict]]) -> list[str]:
    """반환: 실패 사유 리스트 (빈 리스트 = 통과)."""
    fails: list[str] = []

    if (n := expect.get("min_results")) is not None and len(hits) < n:
        fails.append(f"min_results: {len(hits)} < {n}")
    if (n := expect.get("max_results")) is not None and len(hits) > n:
        fails.append(f"max_results: {len(hits)} > {n}")

    if (a := expect.get("contains_actress")):
        norm = a.strip().lower()
        found = any(norm in (str(x).lower() for x in (h.get("actresses") or []))
                    for h in hits)
        if not found:
            fails.append(f"contains_actress: '{a}' not in any hit")

    if (opuses := expect.get("contains_opus")):
        got = {h.get("opus") for h in hits}
        miss = [o for o in opuses if o not in got]
        if miss:
            fails.append(f"contains_opus: missing {miss}")

    if (amh := expect.get("all_must_have")):
        for h in hits:
            for k, v in amh.items():
                got = h.get(k)
                if got != v:
                    fails.append(f"all_must_have: opus={h.get('opus')} {k}={got} (expected {v})")
                    break

    if (other_id := expect.get("same_result_as")):
        other = all_results.get(other_id, [])
        a = {h.get("opus") for h in hits[:3]}
        b = {h.get("opus") for h in other[:3]}
        if not (a & b):
            fails.append(f"same_result_as: top-3 disjoint with {other_id} (a={a} b={b})")

    return fails


# --------------------------------------------------------------------------
#  메인
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", type=Path, default=GOLDEN)
    ap.add_argument("--id", help="단일 케이스 id 실행")
    ap.add_argument("--tag", help="id prefix 필터 (예: actress, ocr)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
    )

    with args.golden.open("r", encoding="utf-8") as f:
        cases = yaml.safe_load(f)

    if args.id:
        cases = [c for c in cases if c["id"] == args.id]
    elif args.tag:
        cases = [c for c in cases if c["id"].startswith(args.tag)]

    if not cases:
        print("no cases matched", file=sys.stderr)
        return 2

    all_results: dict[str, list[dict]] = {}
    rows: list[dict] = []

    for c in cases:
        cid = c["id"]
        query = c["query"]
        expect = c.get("expect", {}) or {}

        t0 = time.time()
        skipped = False
        if expect.get("face_search"):
            hits = _face_hits(expect["face_search"])
            if hits is None:
                skipped = True
                hits = []
        elif expect.get("ocr_search"):
            hits = _ocr_hits(query)
        else:
            hits, _first = _chat_hits(query)
        elapsed = round(time.time() - t0, 2)

        all_results[cid] = hits

        if skipped:
            status = "SKIP"
            fails: list[str] = ["face image not found"]
        else:
            fails = _check(expect, hits, all_results)
            status = "PASS" if not fails else "FAIL"

        rows.append({
            "id": cid, "query": query, "status": status,
            "elapsed_sec": elapsed, "n_hits": len(hits), "fails": fails,
        })

        marker = {"PASS": "OK ", "FAIL": "X  ", "SKIP": "-  "}[status]
        print(f"{marker} {cid:28s} {elapsed:5.2f}s  hits={len(hits):3d}  {query}")
        if fails and args.verbose:
            for f in fails:
                print(f"     ! {f}")

    # ----- 통계 -----
    total = len(rows)
    n_pass = sum(1 for r in rows if r["status"] == "PASS")
    n_fail = sum(1 for r in rows if r["status"] == "FAIL")
    n_skip = sum(1 for r in rows if r["status"] == "SKIP")
    eligible = total - n_skip
    rate = (n_pass / eligible * 100) if eligible else 0.0

    print()
    print(f"---- {n_pass}/{eligible} PASS  ({rate:.1f}%)   skip={n_skip}  fail={n_fail} ----")
    print(f"M6 수락기준: 정답률 ≥ 85%  →  {'OK' if rate >= 85 else 'MISS'}")

    # ----- 결과 저장 -----
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "total": total, "pass": n_pass, "fail": n_fail, "skip": n_skip,
        "pass_rate": round(rate, 2),
        "rows": rows,
    }
    fp = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    fp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {fp.relative_to(ROOT)}")

    return 0 if rate >= 85 else 1


if __name__ == "__main__":
    sys.exit(main())
