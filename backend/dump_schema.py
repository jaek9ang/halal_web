from pathlib import Path
import sqlite3

backend = Path.cwd()
db_candidates = [
    backend / "db" / "pmf_app.db",
    backend / "db" / "ocr_test.db",
    backend / "db" / "halal_lhln.db",
    backend / "db" / "cert_template_features.db",
    backend / "app" / "db" / "pmf_app.db",
    backend / "app" / "db" / "ocr_test.db",
    backend / "app" / "db" / "halal_lhln.db",
    backend / "app" / "db" / "cert_template_features.db",
]

out_dir = backend / "schema_export"
out_dir.mkdir(parents=True, exist_ok=True)

found = 0

for db_path in db_candidates:
    if not db_path.exists():
        print(f"[SKIP] not found: {db_path}")
        continue

    out_path = out_dir / f"{db_path.stem}_schema.sql"

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("""
            SELECT sql
            FROM sqlite_master
            WHERE sql IS NOT NULL
            ORDER BY type, name
        """).fetchall()

        schema_text = "\n\n".join(row[0] for row in rows)
        out_path.write_text(schema_text, encoding="utf-8")

        print(f"[OK] {db_path} -> {out_path}")
        found += 1
    finally:
        conn.close()

print(f"[DONE] exported schema files: {found}")
