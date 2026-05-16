from packages.indexer.db import connect
from packages.indexer.embed_text import _qdrant

conn = connect()
total     = conn.execute("SELECT COUNT(*) FROM posters").fetchone()[0]
with_text = conn.execute("SELECT COUNT(*) FROM posters WHERE ocr_text IS NOT NULL AND ocr_text != ''").fetchone()[0]
empty     = conn.execute("SELECT COUNT(*) FROM posters WHERE ocr_text IS NULL OR ocr_text = ''").fetchone()[0]

print(f"포스터 전체   : {total:,}")
print(f"OCR 텍스트 있음: {with_text:,}  ({with_text/total*100:.1f}%)")
print(f"OCR 텍스트 없음: {empty:,}")

print("\n--- 샘플 3개 ---")
rows = conn.execute(
    "SELECT opus, ocr_text FROM posters WHERE ocr_text IS NOT NULL AND ocr_text != '' LIMIT 3"
).fetchall()
for r in rows:
    print(r["opus"], "|", r["ocr_text"][:120])

conn.close()

qc = _qdrant()
info = qc.get_collection("poster_ocr")
print(f"\nQdrant poster_ocr 벡터: {info.points_count:,}")
