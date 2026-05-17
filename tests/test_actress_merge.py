"""actress_merge: 배우 별칭 병합 시나리오 (Alice/앨리스/Alice S.)."""

from packages.indexer.actress_merge import (
    build_actress_master,
    build_alias_lookup,
    lookup_canonical,
    normalize_actress,
)


def test_normalize_basic():
    assert normalize_actress("  Alice Smith ") == "alice smith"
    assert normalize_actress("ALICE  SMITH") == "alice smith"
    assert normalize_actress("앨리스") == "앨리스"
    assert normalize_actress("") == ""
    assert normalize_actress(None) == ""


def test_alice_merge_three_aliases_one_canonical():
    """Alice S. 의 3개 표기가 하나의 canonical 로 모인다."""
    records = [
        {
            "name": "Alice Smith",
            "otherNames": ["Alice", "앨리스"],
            "lastModified": 100,
            "favorite": True,
            "debut": 2002,
            "height": 160,
        },
        # 같은 사람을 다른 record 에서 부분 표기
        {"name": "Alice", "otherNames": [], "lastModified": 50, "favorite": False, "debut": 2003},
        {
            "name": "앨리스",
            "otherNames": ["Alice Smith"],
            "lastModified": 80,
            "favorite": False,
            "debut": 2002,
            "comment": "한국어 표기",
        },
        # 무관한 다른 사람
        {"name": "Bob Carter", "otherNames": [], "lastModified": 90},
    ]
    actresses, aliases = build_actress_master(records)
    by_canon = {a.canonical_name: a for a in actresses}
    assert len(by_canon) == 2

    # canonical = lastModified 가 가장 큰(100) record 의 name = "alice smith"
    alice = by_canon["alice smith"]
    assert alice.display_name == "Alice Smith"
    assert alice.favorite is True  # OR
    assert alice.debut == 2002  # min
    assert alice.height == 160  # latest 의 값

    alias_map = build_alias_lookup(aliases)
    assert lookup_canonical("Alice Smith", alias_map) == "alice smith"
    assert lookup_canonical("alice", alias_map) == "alice smith"
    assert lookup_canonical("앨리스", alias_map) == "alice smith"
    assert lookup_canonical("Bob Carter", alias_map) == "bob carter"
    assert lookup_canonical("Unknown", alias_map) is None


def test_transitive_chain_merge():
    """A↔B 와 B↔C 가 따로 있어도 하나로 병합."""
    recs = [
        {"name": "A", "otherNames": ["B"], "lastModified": 1},
        {"name": "C", "otherNames": ["B"], "lastModified": 2},
    ]
    actresses, aliases = build_actress_master(recs)
    assert len(actresses) == 1
    canon = actresses[0].canonical_name
    assert canon == "c"
    alias_map = build_alias_lookup(aliases)
    assert lookup_canonical("A", alias_map) == "c"
    assert lookup_canonical("B", alias_map) == "c"
    assert lookup_canonical("C", alias_map) == "c"


def test_empty_record_skipped():
    actresses, _ = build_actress_master([{"name": "", "otherNames": []}])
    assert actresses == []
