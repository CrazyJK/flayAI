"""배우 병합 로직 (otherNames + localName 기반 Union-Find).

AI_PLAN.md §5.4 구현.
- name + otherNames + localName 을 모두 normalize → Union-Find로 그룹화
- 그룹별 canonical = 가장 최근 lastModified 의 name
- 충돌 필드(birth/body/height/comment)는 가장 최근 lastModified 우선
- favorite 은 OR (한 번이라도 즐겨찾기였으면 True)
- debut 은 group 내 최솟값(가장 빠른 데뷔)

입력: actress.json record 리스트
출력: (canonical Actress dataclass 리스트, alias_norm → canonical_name 매핑)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


def normalize_actress(name: str | None) -> str:
    """배우 이름 정규화 키. 빈 입력은 빈 문자열."""
    if not name:
        return ""
    n = unicodedata.normalize("NFKC", name).strip().lower()
    n = re.sub(r"\s+", " ", n)
    return n


@dataclass
class Actress:
    canonical_name: str          # normalize 된 키 (PRIMARY KEY)
    display_name: str            # 표시용 (가장 최근 lastModified 의 name 원문)
    local_name: str | None
    favorite: bool
    birth: str | None
    body: str | None
    height: int | None
    debut: int | None
    comment: str | None
    last_modified: int


@dataclass
class Alias:
    alias_norm: str
    alias_raw: str
    canonical_name: str


class _UF:
    """간단한 Union-Find (path compression + union by size)."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.size: dict[str, int] = {}

    def add(self, x: str) -> None:
        if x not in self.parent:
            self.parent[x] = x
            self.size[x] = 1

    def find(self, x: str) -> str:
        self.add(x)
        # iterative path compression
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        cur = x
        while self.parent[cur] != root:
            self.parent[cur], cur = root, self.parent[cur]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]

    def groups(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for k in self.parent:
            out.setdefault(self.find(k), []).append(k)
        return out


def _alias_keys(rec: dict[str, Any]) -> list[str]:
    """record 에서 alias 후보를 normalize 해서 dedupe + 빈문자열 제거."""
    keys: list[str] = []
    for raw in [rec.get("name"), rec.get("localName"), *(rec.get("otherNames") or [])]:
        n = normalize_actress(raw)
        if n and n not in keys:
            keys.append(n)
    return keys


def _key_to_raw(rec: dict[str, Any]) -> dict[str, str]:
    """normalize 키 → 원본 문자열 매핑 (record 내)."""
    out: dict[str, str] = {}
    for raw in [rec.get("name"), rec.get("localName"), *(rec.get("otherNames") or [])]:
        if not raw:
            continue
        n = normalize_actress(raw)
        if n and n not in out:
            out[n] = raw
    return out


def build_actress_master(
    records: list[dict[str, Any]],
) -> tuple[list[Actress], list[Alias]]:
    """actress.json 입력 → canonical Actress 리스트 + alias 리스트."""
    uf = _UF()
    # record_id → keys (record index 로 식별)
    rec_keys: list[list[str]] = []
    raw_lookup: dict[str, str] = {}     # alias_norm → 원문 (가장 마지막 본 것)
    for rec in records:
        keys = _alias_keys(rec)
        rec_keys.append(keys)
        for k, r in _key_to_raw(rec).items():
            raw_lookup[k] = r
        if not keys:
            continue
        uf.add(keys[0])
        for k in keys[1:]:
            uf.union(keys[0], k)

    groups = uf.groups()                 # root → [keys...]
    # alias_norm → group_root
    key_to_root: dict[str, str] = {}
    for root, members in groups.items():
        for m in members:
            key_to_root[m] = root

    # group_root → 소속 record 리스트
    root_to_records: dict[str, list[dict[str, Any]]] = {}
    for rec, keys in zip(records, rec_keys):
        if not keys:
            continue
        root = key_to_root[keys[0]]
        root_to_records.setdefault(root, []).append(rec)

    out_actresses: list[Actress] = []
    out_aliases: list[Alias] = []
    seen_canonical: set[str] = set()

    for root, members in root_to_records.items():
        # 가장 최근 lastModified 우선 (None/0 이면 0 으로 취급)
        latest = max(members, key=lambda r: int(r.get("lastModified") or 0))
        canonical = normalize_actress(latest.get("name") or "") or root

        # 동일 canonical 충돌 방지: 같은 canonical이 다른 그룹에 또 나오면 suffix
        base = canonical
        suffix = 1
        while canonical in seen_canonical:
            suffix += 1
            canonical = f"{base}#{suffix}"
        seen_canonical.add(canonical)

        actress = Actress(
            canonical_name=canonical,
            display_name=latest.get("name") or canonical,
            local_name=latest.get("localName") or None,
            favorite=any(bool(m.get("favorite")) for m in members),
            birth=latest.get("birth") or None,
            body=latest.get("body") or None,
            height=latest.get("height") or None,
            debut=min(
                (int(m["debut"]) for m in members if m.get("debut")),
                default=None,
            ),
            comment=latest.get("comment") or None,
            last_modified=int(latest.get("lastModified") or 0),
        )
        out_actresses.append(actress)

        # 그룹의 모든 alias_norm 을 canonical 로 매핑
        for k in groups[root]:
            out_aliases.append(
                Alias(
                    alias_norm=k,
                    alias_raw=raw_lookup.get(k, k),
                    canonical_name=canonical,
                )
            )
    return out_actresses, out_aliases


def build_alias_lookup(aliases: list[Alias]) -> dict[str, str]:
    """alias_norm (정규화된 임의 표기) → canonical_name 빠른 조회용."""
    return {a.alias_norm: a.canonical_name for a in aliases}


def lookup_canonical(name: str, alias_map: dict[str, str]) -> str | None:
    """임의 표기 → canonical (없으면 None)."""
    return alias_map.get(normalize_actress(name))
