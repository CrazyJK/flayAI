"""M2 acceptance: 7 chat scenarios via /api/chat (SSE)."""

from __future__ import annotations

import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"

SCENARIOS = [
    "Alice Smith 출연작 5개 추천해줘",
    "Alice 출연작 알려줘",
    "Alice S. 출연작 알려줘",
    "회사 배경의 일상 영상 찾아줘",
    "2023년 7월 발매작 보여줘",
    "StudioA 제작사 평점 4 이상 영상",
    "지금 볼 수 있는 회사 배경 영상",
]


def stream_chat(query: str) -> tuple[float, dict]:
    """Returns (first_token_sec, summary_dict)."""
    t0 = time.time()
    first_token_t: float | None = None
    first_event_t: float | None = None
    tokens: list[str] = []
    tool_calls: list = []
    tool_results: list = []
    final_msg: str | None = None
    err: str | None = None

    try:
        with httpx.stream("POST", f"{BASE}/api/chat", json={"query": query}, timeout=120.0) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                try:
                    ev = json.loads(payload)
                except Exception:
                    continue
                if first_event_t is None:
                    first_event_t = time.time() - t0
                t = ev.get("type")
                if t == "tool_call":
                    tool_calls.append({"name": ev.get("name"), "args": ev.get("args")})
                elif t == "tool_result":
                    res = ev.get("result")
                    if isinstance(res, list):
                        n = len(res)
                    elif isinstance(res, dict):
                        n = len(res.get("items", []))
                    else:
                        n = 0
                    tool_results.append({"name": ev.get("name"), "n_items": n})
                elif t == "token":
                    if first_token_t is None:
                        first_token_t = time.time() - t0
                    tokens.append(ev.get("text", ""))
                elif t == "done":
                    final_msg = ev.get("message")
                elif t == "error":
                    err = ev.get("error") or ev.get("message")
    except Exception as e:
        err = str(e)

    elapsed = time.time() - t0
    return first_token_t or elapsed, {
        "elapsed_sec": round(elapsed, 2),
        "first_event_sec": round(first_event_t, 2) if first_event_t else None,
        "first_token_sec": round(first_token_t, 2) if first_token_t else None,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "answer_preview": (final_msg or "".join(tokens))[:200],
        "error": err,
    }


def main() -> int:
    # warmup
    httpx.get(f"{BASE}/healthz", timeout=5).raise_for_status()
    print("=" * 80)
    rows = []
    for q in SCENARIOS:
        print(f"\n>>> {q}")
        ftt, summary = stream_chat(q)
        rows.append({"query": q, "ftt": ftt, **summary})
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    print("\n" + "=" * 80)
    print("SUMMARY")
    fts = [r["first_token_sec"] for r in rows if r.get("first_token_sec")]
    fts.sort()
    p95 = fts[int(len(fts) * 0.95)] if fts else None
    fes = [r["first_event_sec"] for r in rows if r.get("first_event_sec")]
    fes.sort()
    p95_ev = fes[int(len(fes) * 0.95)] if fes else None
    n_tool_calls = sum(1 for r in rows if r["tool_calls"])
    n_errors = sum(1 for r in rows if r.get("error"))
    n_pass = sum(1 for r in rows if (r["tool_calls"] or r["tool_results"]) and not r.get("error"))
    print(f"scenarios          : {len(rows)}")
    print(f"with tool_call     : {n_tool_calls}")
    print(f"errors             : {n_errors}")
    print(f"pass (tool+no err) : {n_pass}/{len(rows)}")
    print(f"first-event p95    : {p95_ev}s  (need <= 3s, SSE first event)")
    print(f"first-token p95    : {p95}s  (LLM first text token)")
    return 0 if n_pass >= 6 else 1


if __name__ == "__main__":
    sys.exit(main())
