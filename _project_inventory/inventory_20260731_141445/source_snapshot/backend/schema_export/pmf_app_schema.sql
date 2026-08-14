CREATE INDEX idx_inbound_attachment_request
        ON inbound_attachment(request_id)
    

CREATE INDEX idx_inbound_mail_request
        ON inbound_mail(matched_request_id)
    

CREATE INDEX idx_inbound_ocr_candidate_attachment
        ON inbound_ocr_candidate(attachment_id)
    

CREATE INDEX idx_inbound_ocr_candidate_request
        ON inbound_ocr_candidate(request_id)
    

CREATE TABLE inbound_attachment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mail_id INTEGER,
            request_id TEXT,
            original_filename TEXT,
            saved_filename TEXT,
            saved_path TEXT,
            ext TEXT,
            file_size INTEGER,
            ocr_status TEXT DEFAULT 'pending',
            created_at TEXT, ocr_selected INTEGER DEFAULT 0, filename_date_candidates_json TEXT,
            FOREIGN KEY(mail_id) REFERENCES inbound_mail(id)
        )

CREATE TABLE inbound_mail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT,
            mailbox TEXT,
            message_uid TEXT UNIQUE,
            subject TEXT,
            sender TEXT,
            received_at TEXT,
            body_text TEXT,
            matched_request_id TEXT,
            match_status TEXT,
            match_reason TEXT,
            attachment_count INTEGER DEFAULT 0,
            download_dir TEXT,
            downloaded_at TEXT
        , is_excluded INTEGER DEFAULT 0, exclude_reason TEXT, body_preview TEXT, date_candidates_json TEXT)

CREATE TABLE inbound_ocr_candidate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attachment_id INTEGER,
            mail_id INTEGER,
            request_id TEXT,
            ocr_job_id INTEGER,
            filename TEXT,
            status TEXT,
            best_expiry TEXT,
            expiry_candidates_json TEXT,
            filename_candidates_json TEXT,
            mail_candidates_json TEXT,
            ocr_candidates_json TEXT,
            message TEXT,
            created_at TEXT
        )

CREATE TABLE mail_send_logs (
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
        sent_at TEXT
    , deleted_at TEXT)

CREATE TABLE ocr_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_path TEXT,
        filename TEXT,
        file_ext TEXT,
        status TEXT,
        raw_text TEXT,
        result_json TEXT,
        error_message TEXT,
        created_at TEXT,
        updated_at TEXT
    )

CREATE TABLE received_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT,
        message_id TEXT,
        subject TEXT,
        sender TEXT,
        receiver TEXT,
        sent_at TEXT,
        request_id TEXT,
        body_preview TEXT,
        filename TEXT,
        filepath TEXT,
        size_bytes INTEGER,
        downloaded_at TEXT
    )

CREATE TABLE sqlite_sequence(name,seq)

CREATE TABLE supplier_email_overrides (
        supplier_key TEXT PRIMARY KEY,
        supplier_name TEXT,
        final_to TEXT,
        final_cc TEXT,
        memo TEXT,
        updated_at TEXT
    )