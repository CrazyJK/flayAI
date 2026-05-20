"""관리자 대시보드 인덱서 수치 점검 스크립트."""

from packages.indexer.db import connect


def main():
    conn = connect()
    try:
        total_videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        total_posters = conn.execute("SELECT COUNT(*) FROM posters").fetchone()[0]

        # 번역 완료 (admin이 읽는 것)
        translated = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE title_ko IS NOT NULL AND title_ko != ''"
        ).fetchone()[0]

        # translations 테이블에 캐싱된 수
        try:
            cached_translations = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
        except Exception:
            cached_translations = "테이블 없음"

        # OCR 완료 (admin이 읽는 것)
        ocr_done = conn.execute(
            "SELECT COUNT(*) FROM posters WHERE ocr_text IS NOT NULL AND ocr_text != ''"
        ).fetchone()[0]

        # posters 테이블 컬럼 확인
        cols = [r[1] for r in conn.execute("PRAGMA table_info(posters)").fetchall()]

        print(f"=== DB 실제 상태 ===")
        print(f"total_videos:        {total_videos}")
        print(f"total_posters:       {total_posters}")
        print(f"translated (title_ko != ''): {translated}  ({translated*100//total_videos}%)")
        print(f"cached_translations: {cached_translations}")
        print(
            f"ocr_done (ocr_text != ''):   {ocr_done}  ({ocr_done*100//total_posters if total_posters else 0}%)"
        )
        print(f"posters 컬럼:        {cols}")
        print()

        # Qdrant 확인
        from qdrant_client import QdrantClient
        from packages.settings import load_config

        cfg = load_config()
        qc = QdrantClient(url=cfg["server"]["qdrant"])
        for name in ["videos", "posters_clip", "poster_ocr", "faces"]:
            try:
                info = qc.get_collection(name)
                print(f"Qdrant '{name}': {info.points_count} points")
            except Exception as e:
                print(f"Qdrant '{name}': ERROR - {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
