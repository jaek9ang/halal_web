CREATE INDEX idx_ocr_test_filename
        ON ocr_test_files(original_filename)
    

CREATE INDEX idx_ocr_test_status
        ON ocr_test_files(status)
    

CREATE TABLE ocr_test_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT NOT NULL UNIQUE,
            original_filename TEXT,
            saved_filename TEXT,
            saved_path TEXT,
            size_bytes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'READY',
            ocr_job_id INTEGER,
            raw_text_preview TEXT,
            error_message TEXT,
            created_at TEXT,
            updated_at TEXT
        )

CREATE TABLE sqlite_sequence(name,seq)