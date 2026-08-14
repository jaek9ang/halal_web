import sqlite3
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]

# 새 FastAPI DB
NEW_DB_PATH = BACKEND_DIR / "db" / "pmf_app.db"

# 기존 Streamlit DB 예상 위치
# 현재 위치: ...\halal_web\backend
# 기존 위치 예상: ...\SW Project\db\pmf_app.db
OLD_DB_PATH = BACKEND_DIR.parents[1] / "db" / "pmf_app.db"


def table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name=?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def ensure_new_log_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mail_send_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT,
            request_id TEXT,
            supplier TEXT,
            mail_type TEXT,
            sender TEXT,
            receiver TEXT,
            cc TEXT,
            subject TEXT,
            body_html TEXT,
            attach_pdf TEXT,
            attachment_paths TEXT,
            test_mode INTEGER,
            success INTEGER,
            send_result TEXT,
            error_message TEXT,
            sent_at TEXT,
            deleted_at TEXT
        )
        """
    )

    conn.commit()


def normalize_test_mode(value) -> int:
    text = str(value or "").strip().upper()

    if text in {"Y", "YES", "TRUE", "1", "테스트", "테스트모드"}:
        return 1

    return 0


def normalize_success(send_status, error_msg="") -> int:
    status = str(send_status or "").strip().upper()

    if status == "SUCCESS":
        return 1

    return 0


def migrate_old_logs():
    print(f"[OLD DB] {OLD_DB_PATH}")
    print(f"[NEW DB] {NEW_DB_PATH}")

    if not OLD_DB_PATH.exists():
        print("기존 Streamlit DB를 찾지 못했습니다.")
        print("OLD_DB_PATH 경로가 맞는지 확인하세요.")
        return

    NEW_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    old_conn = sqlite3.connect(OLD_DB_PATH)
    old_conn.row_factory = sqlite3.Row

    new_conn = sqlite3.connect(NEW_DB_PATH)
    new_conn.row_factory = sqlite3.Row

    try:
        if not table_exists(old_conn, "sent_mail_log"):
            print("기존 DB에 sent_mail_log 테이블이 없습니다.")
            return

        ensure_new_log_table(new_conn)

        old_rows = old_conn.execute(
            """
            SELECT
                request_id,
                batch_id,
                sent_at,
                sender,
                receiver,
                cc,
                supplier_name,
                mail_type,
                subject,
                body_html,
                attach_pdf,
                attachment_paths,
                send_status,
                error_msg,
                test_mode,
                COALESCE(deleted, 0) AS deleted,
                deleted_at
            FROM sent_mail_log
            WHERE COALESCE(deleted, 0) = 0
            ORDER BY id ASC
            """
        ).fetchall()

        print(f"기존 로그 {len(old_rows)}건 발견")

        inserted = 0
        skipped = 0

        for row in old_rows:
            request_id = row["request_id"] or ""
            subject = row["subject"] or ""
            sent_at = row["sent_at"] or ""

            # 중복 방지: request_id + subject + sent_at 기준
            exists = new_conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM mail_send_logs
                WHERE COALESCE(request_id, '') = ?
                  AND COALESCE(subject, '') = ?
                  AND COALESCE(sent_at, '') = ?
                """,
                (request_id, subject, sent_at),
            ).fetchone()["cnt"]

            if int(exists) > 0:
                skipped += 1
                continue

            send_status = row["send_status"] or ""
            error_msg = row["error_msg"] or ""

            new_conn.execute(
                """
                INSERT INTO mail_send_logs (
                    batch_id,
                    request_id,
                    supplier,
                    mail_type,
                    sender,
                    receiver,
                    cc,
                    subject,
                    body_html,
                    attach_pdf,
                    attachment_paths,
                    test_mode,
                    success,
                    send_result,
                    error_message,
                    sent_at,
                    deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["batch_id"] or "",
                    request_id,
                    row["supplier_name"] or "",
                    row["mail_type"] or "",
                    row["sender"] or "",
                    row["receiver"] or "",
                    row["cc"] or "",
                    subject,
                    row["body_html"] or "",
                    row["attach_pdf"] or "N",
                    row["attachment_paths"] or "[]",
                    normalize_test_mode(row["test_mode"]),
                    normalize_success(send_status, error_msg),
                    send_status,
                    error_msg,
                    sent_at,
                    row["deleted_at"] or None,
                ),
            )

            inserted += 1

        new_conn.commit()

        print(f"이관 완료: {inserted}건")
        print(f"중복 스킵: {skipped}건")

    finally:
        old_conn.close()
        new_conn.close()


if __name__ == "__main__":
    migrate_old_logs()