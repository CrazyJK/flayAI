"""actress_merge: Aoi/葵/Sora Aoi alias 시나리오."""
from packages.indexer.actress_merge import (
    build_actress_master,
    build_alias_lookup,
    lookup_canonical,
    normalize_actress,
)


def test_normalize_basic():
    assert normalize_actress("  Sora Aoi ") == "sora aoi"
    assert normalize_actress("SORA  AOI") == "sora aoi"
    assert normalize_actress("葵") == "葵"
    assert normalize_actress("") == ""
    assert normalize_actress(None) == ""


def test_aoi_merge_three_aliases_one_canonical():
    """Sora Aoi 의 3개 표기가 하나의 canonical 로 모인다."""
    records = [
        {"name": "Sora Aoi", "otherNames": ["Aoi", "葵"], "lastModified": 100, "favorite": True,
         "debut": 2002, "height": 160, "body": "B-W-H"},
        # 같은 사람을 다른 record 에서 부분 표기
        {"name": "Aoi",      "otherNames": [],            "lastModified": 50,  "favorite": False,
         "debut": 2003},
        {"name": "葵",        "otherNames": ["Sora Aoi"], "lastModified": 80,  "favorite": False,
         "debut": 2002, "comment": "JP only"},
        # 무관한 다른 사람
        {"name": "Yua Aida", "otherNames": [],            "lastModified": 90},
    ]
    actresses, aliases = build_actress_master(records)
    by_canon = {a.canonical_name: a for a in actresses}
    assert len(by_canon) == 2

    # canonical = lastModified 가 가장 큰(100) record 의 name = "sora aoi"
    sora = by_canon["sora aoi"]
    assert sora.display_name == "Sora Aoi"
    assert sora.favorite is True              # OR
    assert sora.debut == 2002                 # min
    assert sora.height == 160                 # latest 의 값

    alias_map = build_alias_lookup(aliases)
    assert lookup_canonical("Sora Aoi", alias_map) == "sora aoi"
    assert lookup_canonical("aoi",      alias_map) == "sora aoi"
    assert lookup_canonical("葵",        alias_map) == "sora aoi"
    assert lookup_canonical("Yua Aida", alias_map) == "yua aida"
    assert lookup_canonical("Unknown",  alias_map) is None


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
