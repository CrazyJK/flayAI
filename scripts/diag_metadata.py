"""DB metadata 진단."""
from packages.indexer.db import connect

c = connect()

print("--- nulls ---")
r = c.execute("""SELECT COUNT(*) tot,
       SUM(CASE WHEN release_year  IS NULL THEN 1 ELSE 0 END) null_year,
       SUM(CASE WHEN release_month IS NULL THEN 1 ELSE 0 END) null_month,
       SUM(CASE WHEN release_date  IS NULL THEN 1 ELSE 0 END) null_date,
       SUM(CASE WHEN studio        IS NULL THEN 1 ELSE 0 END) null_studio
       FROM videos""").fetchone()
print(dict(r))

print("\n--- top years ---")
for row in c.execute("SELECT release_year, COUNT(*) FROM videos GROUP BY release_year ORDER BY 2 DESC LIMIT 12").fetchall():
    print(tuple(row))

print("\n--- 2023 months ---")
for row in c.execute("SELECT release_year, release_month, COUNT(*) FROM videos WHERE release_year=2023 GROUP BY release_month ORDER BY release_month").fetchall():
    print(tuple(row))

print("\n--- top studios ---")
for row in c.execute("SELECT studio, COUNT(*) FROM videos GROUP BY studio ORDER BY 2 DESC LIMIT 20").fetchall():
    print(tuple(row))

print("\n--- studio LIKE %s1% ---")
for row in c.execute("SELECT studio, COUNT(*) FROM videos WHERE LOWER(studio) LIKE '%s1%' OR LOWER(studio) LIKE '%sone%' GROUP BY studio ORDER BY 2 DESC LIMIT 20").fetchall():
    print(tuple(row))
