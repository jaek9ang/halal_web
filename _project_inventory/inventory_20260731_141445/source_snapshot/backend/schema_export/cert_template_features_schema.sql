CREATE INDEX idx_candidates_hash ON cert_org_candidates(file_hash, run_id)

CREATE INDEX idx_feature_hash ON cert_image_features(file_hash, page_no, feature_kind)

CREATE INDEX idx_template_org ON cert_template_refs(cert_org, is_active)

CREATE TABLE cert_files (
          file_hash TEXT PRIMARY KEY, original_filename TEXT, stored_path TEXT,
          source_type TEXT, source_batch_id TEXT, file_size INTEGER, page_count INTEGER, created_at TEXT
        )

CREATE TABLE cert_image_features (
          id INTEGER PRIMARY KEY AUTOINCREMENT, file_hash TEXT NOT NULL, page_no INTEGER NOT NULL,
          feature_kind TEXT NOT NULL, feature_version TEXT NOT NULL, full_phash TEXT, header_phash TEXT,
          orb_desc_path TEXT, image_path TEXT, created_at TEXT,
          UNIQUE(file_hash, page_no, feature_kind, feature_version)
        )

CREATE TABLE cert_org_candidates (
          id INTEGER PRIMARY KEY AUTOINCREMENT, file_hash TEXT NOT NULL, candidate_org TEXT NOT NULL,
          rank_no INTEGER NOT NULL, image_score REAL, margin REAL, decision TEXT, feature_kind TEXT,
          evidence_json TEXT, run_id TEXT, created_at TEXT
        )

CREATE TABLE cert_org_decisions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, file_hash TEXT NOT NULL UNIQUE, final_org TEXT NOT NULL,
          decision_type TEXT NOT NULL, decision_score REAL, decision_reason TEXT, confirmed_by TEXT, confirmed_at TEXT
        , predicted_org TEXT DEFAULT '', original_decision TEXT DEFAULT '', original_filename TEXT DEFAULT '', file_path TEXT DEFAULT '', image_score REAL DEFAULT 0, margin REAL DEFAULT 0, is_excluded INTEGER DEFAULT 0, memo TEXT DEFAULT '', updated_at TEXT DEFAULT '')

CREATE TABLE cert_template_refs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, cert_org TEXT NOT NULL, template_id TEXT,
          source_filename TEXT, source_path TEXT, file_hash TEXT NOT NULL, page_no INTEGER NOT NULL,
          feature_version TEXT NOT NULL, is_active INTEGER DEFAULT 1, created_at TEXT,
          UNIQUE(file_hash, page_no, cert_org, feature_version)
        )

CREATE TABLE sqlite_sequence(name,seq)