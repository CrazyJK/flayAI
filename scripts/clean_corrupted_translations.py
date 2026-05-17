"""오염된 번역 데이터만 골라 비우는 일회용 클린업 스크립트.

판정 기준 ( packages.indexer.translate._looks_corrupted ):
- 같은 토큰 5회 이상 연속 반복 (NLLB repetition collapse)
- 길이 20자 이상이고 한자 비율 >= 한글 비율 (LLM 폴백의 중국어 오염)

대상:
1. translations 테이블의 ko 캐시 행
2. videos.title_ko / desc_ko

실행 후 reindex 의 translate 단계를 다시 돌리면, 정리된 행은 신규 알고리즘
(no_repeat_ngram_size, _looks_corrupted 검증, 한국어 LLM 프롬프트) 으로 재생성됨.
"""
from __future__ import annotations

from packages.indexer.db import connect
from packages.indexer.translate import _looks_corrupted


def main() -> None:
    conn = connect()
    try:
        # 1) translations 캐시
        rows = conn.execute(
            "SELECT hash, tgt_text FROM translations WHERE tgt_lang = 'ko'"
        ).fetchall()
        bad_hashes = [r["hash"] for r in rows if _looks_corrupted(r["tgt_text"] or "")]
        print(f"translations: total={len(rows)} corrupted={len(bad_hashes)}")
        if bad_hashes:
            conn.executemany(
                "DELETE FROM translations WHERE hash = ?",
                [(h,) for h in bad_hashes],
            )

        # 2) videos.title_ko
        t_rows = conn.execute(
            "SELECT opus, title_ko FROM videos "
            "WHERE title_ko IS NOT NULL AND title_ko <> ''"
        ).fetchall()
        bad_titles = [r["opus"] for r in t_rows if _looks_corrupted(r["title_ko"])]
        print(f"videos.title_ko: total={len(t_rows)} corrupted={len(bad_titles)}")
        if bad_titles:
            conn.executemany(
                "UPDATE videos SET title_ko = NULL WHERE opus = ?",
                [(o,) for o in bad_titles],
            )

        # 3) videos.desc_ko
        d_rows = conn.execute(
            "SELECT opus, desc_ko FROM videos "
            "WHERE desc_ko IS NOT NULL AND desc_ko <> ''"
        ).fetchall()
        bad_descs = [r["opus"] for r in d_rows if _looks_corrupted(r["desc_ko"])]
        print(f"videos.desc_ko: total={len(d_rows)} corrupted={len(bad_descs)}")
        if bad_descs:
            conn.executemany(
                "UPDATE videos SET desc_ko = NULL WHERE opus = ?",
                [(o,) for o in bad_descs],
            )

        conn.commit()
        print("done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
