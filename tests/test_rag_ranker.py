"""rag/ranker + retriever (RRF) 단위 테스트."""

from packages.rag.ranker import rank
from packages.rag.retriever import Candidate, rrf_merge


def test_rrf_merge_combines_ranks():
    sem = [
        Candidate(opus="A", semantic_score=0.9),
        Candidate(opus="B", semantic_score=0.8),
        Candidate(opus="C", semantic_score=0.7),
    ]
    fts = [Candidate(opus="C", fts_score=0.9), Candidate(opus="A", fts_score=0.5)]
    merged = rrf_merge(sem, fts)
    assert merged[0].opus in {"A", "C"}  # both top in their lists
    opus_set = {c.opus for c in merged}
    assert opus_set == {"A", "B", "C"}
    # rrf_score 누적 검증: C는 sem rank3 + fts rank1, A 는 sem rank1 + fts rank2
    by = {c.opus: c.rrf_score for c in merged}
    assert by["A"] > 0 and by["C"] > 0
    # 둘 다 있는 항목이 단독 등장(B)보다 높아야 함
    assert by["A"] > by["B"]
    assert by["C"] > by["B"]


def test_rank_weights_apply():
    cands = [
        Candidate(
            opus="X",
            semantic_score=1.0,
            fts_score=0.0,
            payload={"play": 0, "rank": 0, "like_count": 0},
        ),
        Candidate(
            opus="Y",
            semantic_score=0.0,
            fts_score=1.0,
            payload={"play": 0, "rank": 0, "like_count": 0},
        ),
    ]
    out = rank(cands)
    assert out[0].opus == "X"  # semantic_weight(0.70) > fts_weight(0.15)


def test_rank_empty():
    assert rank([]) == []


def test_rank_usage_boost_breaks_tie():
    cands = [
        Candidate(opus="A", semantic_score=0.5, payload={"play": 0, "rank": 0, "like_count": 0}),
        Candidate(opus="B", semantic_score=0.5, payload={"play": 100, "rank": 5, "like_count": 50}),
    ]
    out = rank(cands)
    assert out[0].opus == "B"
