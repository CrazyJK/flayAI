from packages.indexer.db import connect

conn = connect()
rows = conn.execute(
    "SELECT opus, path FROM posters WHERE ocr_text IS NULL OR ocr_text = '' LIMIT 10"
).fetchall()
print(f"OCR 누락 샘플 ({len(rows)}개):")
for r in rows:
    print(" ", r["opus"], "|", r["path"])
conn.close()
