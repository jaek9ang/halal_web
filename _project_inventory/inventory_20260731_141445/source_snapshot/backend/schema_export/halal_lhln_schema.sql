CREATE TABLE lhln_reference (
        lph_id TEXT PRIMARY KEY,
        nama_lhln_raw TEXT,
        nama_lhln TEXT,
        abbreviation TEXT,
        negara TEXT,
        kota TEXT,
        alamat TEXT,
        lokasi TEXT,
        jenis TEXT,
        no_reg TEXT,
        tgl_berlaku TEXT,
        status TEXT,
        updated_at TEXT
    )

CREATE TABLE lhln_sync_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        crawled_at TEXT,
        total_count INTEGER,
        saved_count INTEGER,
        source_url TEXT
    )

CREATE TABLE sqlite_sequence(name,seq)