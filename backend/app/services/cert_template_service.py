# -*- coding: utf-8 -*-
"""Certificate template DB service: pHash + ORB based org candidates."""
from __future__ import annotations
from app.core.config import CERT_TEMPLATE_DB_PATH
from app.core.db import WAL_PRAGMAS, connect as db_connect

import hashlib, io, json, sqlite3, time, traceback, threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import cv2
import fitz
import numpy as np
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parents[2]
DB_DIR = BACKEND_DIR / "db"
OUTPUT_DIR = BACKEND_DIR / "output"
STORE_DIR = OUTPUT_DIR / "cert_template"
FEATURE_DIR = STORE_DIR / "features"
IMAGE_DIR = STORE_DIR / "images"
DB_PATH = CERT_TEMPLATE_DB_PATH
DB_WRITE_LOCK = threading.RLock()

SUPPORTED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
EXCLUDE_FOLDER_NAMES = {"새 폴더", "새폴더", "_output", "_image_similarity_result", "_cert_template_db", "__pycache__"}
FEATURE_VERSION = "v1_phash_orb_120dpi_page1"
DEFAULT_MAX_PAGES = 1
DEFAULT_DPI = 120
AUTO_SCORE_THRESHOLD = 0.82
AUTO_MARGIN_THRESHOLD = 0.07

# enhanced retry 기준. 낮은 score/margin이면 enhanced feature로 한 번 더 비교한다.
RETRY_SCORE_THRESHOLD = 0.80
RETRY_MARGIN_THRESHOLD = 0.07

# 최종 수동검토 기준. 이 값보다 낮으면 자동확정하지 않는다.
MANUAL_SCORE_THRESHOLD = 0.70
MANUAL_MARGIN_THRESHOLD = 0.04
ORG_ALIASES = {"LLS-ISA":"ISA", "LLS ISA":"ISA", "ISLAMIC SERVICES OF AMERICA":"ISA", "HALALCONTROL":"HALAL CONTROL", "HALAL CONTROL GERMANY":"HALAL CONTROL"}

@dataclass
class PageFeature:
    org: str
    source_path: str
    source_filename: str
    file_hash: str
    page_no: int
    feature_kind: str
    full_hash: np.ndarray
    header_hash: np.ndarray
    orb_desc: Optional[np.ndarray]

@dataclass
class MatchEvidence:
    org: str
    score: float
    target_page: int
    ref_page: int
    ref_file: str
    ref_hash: str
    full_hash_score: float
    header_hash_score: float
    orb_score: float
    feature_kind: str

def ensure_dirs():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    FEATURE_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_conn() -> sqlite3.Connection:
    ensure_dirs()
    return db_connect(
        DB_PATH,
        timeout=60,
        check_same_thread=False,
        pragmas=WAL_PRAGMAS,
    )

def ensure_table_columns(conn: sqlite3.Connection, table_name: str, columns: Dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}

    for column_name, column_type in columns.items():
        if column_name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def init_cert_template_db():
    with get_conn() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS cert_files (
          file_hash TEXT PRIMARY KEY, original_filename TEXT, stored_path TEXT,
          source_type TEXT, source_batch_id TEXT, file_size INTEGER, page_count INTEGER, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS cert_template_refs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, cert_org TEXT NOT NULL, template_id TEXT,
          source_filename TEXT, source_path TEXT, file_hash TEXT NOT NULL, page_no INTEGER NOT NULL,
          feature_version TEXT NOT NULL, is_active INTEGER DEFAULT 1, created_at TEXT,
          UNIQUE(file_hash, page_no, cert_org, feature_version)
        );
        CREATE TABLE IF NOT EXISTS cert_image_features (
          id INTEGER PRIMARY KEY AUTOINCREMENT, file_hash TEXT NOT NULL, page_no INTEGER NOT NULL,
          feature_kind TEXT NOT NULL, feature_version TEXT NOT NULL, full_phash TEXT, header_phash TEXT,
          orb_desc_path TEXT, image_path TEXT, created_at TEXT,
          UNIQUE(file_hash, page_no, feature_kind, feature_version)
        );
        CREATE TABLE IF NOT EXISTS cert_org_candidates (
          id INTEGER PRIMARY KEY AUTOINCREMENT, file_hash TEXT NOT NULL, candidate_org TEXT NOT NULL,
          rank_no INTEGER NOT NULL, image_score REAL, margin REAL, decision TEXT, feature_kind TEXT,
          evidence_json TEXT, run_id TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS cert_org_decisions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, file_hash TEXT NOT NULL UNIQUE, final_org TEXT NOT NULL,
          decision_type TEXT NOT NULL, decision_score REAL, decision_reason TEXT, confirmed_by TEXT, confirmed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_template_org ON cert_template_refs(cert_org, is_active);
        CREATE INDEX IF NOT EXISTS idx_feature_hash ON cert_image_features(file_hash, page_no, feature_kind);
        CREATE INDEX IF NOT EXISTS idx_candidates_hash ON cert_org_candidates(file_hash, run_id);
        ''')

        ensure_table_columns(conn, "cert_org_decisions", {
            "predicted_org": "TEXT DEFAULT ''",
            "original_decision": "TEXT DEFAULT ''",
            "original_filename": "TEXT DEFAULT ''",
            "file_path": "TEXT DEFAULT ''",
            "image_score": "REAL DEFAULT 0",
            "margin": "REAL DEFAULT 0",
            "is_excluded": "INTEGER DEFAULT 0",
            "memo": "TEXT DEFAULT ''",
            "updated_at": "TEXT DEFAULT ''",
        })


def reset_cert_template_db():
    ensure_dirs()
    with DB_WRITE_LOCK:
        for p in [DB_PATH, DB_PATH.with_suffix(DB_PATH.suffix + "-wal"), DB_PATH.with_suffix(DB_PATH.suffix + "-shm")]:
            if p.exists():
                p.unlink(missing_ok=True)
        for p in FEATURE_DIR.glob("*.npy"):
            p.unlink(missing_ok=True)
        for p in IMAGE_DIR.glob("*.jpg"):
            p.unlink(missing_ok=True)
        init_cert_template_db()

def normalize_org_label(value: str) -> str:
    text = " ".join(str(value or "").strip().replace("_", " ").split()).upper()
    return ORG_ALIASES.get(text, text)

def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def list_supported_files(folder: Path) -> List[Path]:
    if not folder.exists(): return []
    return sorted([p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS], key=lambda x: str(x).lower())

def get_org_folders(root_dir: Path) -> List[Path]:
    return sorted([p for p in root_dir.iterdir() if p.is_dir() and p.name not in EXCLUDE_FOLDER_NAMES], key=lambda x: x.name.lower())

def bits_to_string(bits: np.ndarray) -> str:
    return "".join("1" if bool(x) else "0" for x in bits.flatten())

def string_to_bits(text: str) -> np.ndarray:
    return np.array([c == "1" for c in str(text or "")], dtype=bool)

def save_orb_desc(file_hash: str, page_no: int, feature_kind: str, desc: Optional[np.ndarray]) -> str:
    if desc is None: return ""
    path = FEATURE_DIR / f"{file_hash}_p{page_no}_{feature_kind}_orb.npy"
    np.save(path, desc)
    return str(path)

def load_orb_desc(path_text: str) -> Optional[np.ndarray]:
    if not path_text: return None
    path = Path(path_text)
    if not path.exists(): return None
    try: return np.load(path, allow_pickle=False)
    except Exception: return None

def get_pdf_page_count(path: Path) -> int:
    if path.suffix.lower() != ".pdf": return 1
    try:
        doc = fitz.open(str(path))
        try: return len(doc)
        finally: doc.close()
    except Exception: return 0

def render_pdf_pages(pdf_path: Path, max_pages: int, dpi: int) -> List[Image.Image]:
    pages = []
    doc = fitz.open(str(pdf_path))
    try:
        mat = fitz.Matrix(dpi/72.0, dpi/72.0)
        for i in range(min(len(doc), max_pages)):
            try:
                pix = doc[i].get_pixmap(matrix=mat, alpha=False)
                pages.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
            except Exception:
                continue
    finally:
        doc.close()
    return pages

def load_image_pages(path: Path, max_pages: int, dpi: int) -> List[Image.Image]:
    if path.suffix.lower() == ".pdf":
        return render_pdf_pages(path, max_pages, dpi)
    return [Image.open(path).convert("RGB")]

def pil_to_cv_gray(img: Image.Image, max_width: int = 1100) -> np.ndarray:
    gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    h, w = gray.shape[:2]
    if w > max_width:
        scale = max_width / float(w)
        gray = cv2.resize(gray, (max_width, max(1, int(h*scale))), interpolation=cv2.INTER_AREA)
    return gray

def apply_clahe(gray: np.ndarray) -> np.ndarray:
    return cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8,8)).apply(gray)

def adaptive_binary(gray: np.ndarray) -> np.ndarray:
    denoised = cv2.fastNlMeansDenoising(gray, None, 8, 7, 21)
    return cv2.adaptiveThreshold(denoised,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,35,11)

def crop_document_margins(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape[:2]
    if h < 100 or w < 100: return gray
    _, mask = cv2.threshold(cv2.GaussianBlur(gray,(5,5),0),245,255,cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours: return gray
    x1,y1,x2,y2 = w,h,0,0
    for c in contours:
        x,y,cw,ch = cv2.boundingRect(c)
        if cw*ch < w*h*0.0005: continue
        x1,y1,x2,y2 = min(x1,x),min(y1,y),max(x2,x+cw),max(y2,y+ch)
    if x2 <= x1 or y2 <= y1: return gray
    px, py = int(w*.025), int(h*.025)
    cropped = gray[max(0,y1-py):min(h,y2+py), max(0,x1-px):min(w,x2+px)]
    if cropped.shape[0] < h*.65 or cropped.shape[1] < w*.65: return gray
    return cropped

def deskew_document(gray: np.ndarray) -> np.ndarray:
    h,w = gray.shape[:2]
    if h < 100 or w < 100: return gray
    inv = 255 - adaptive_binary(gray)
    coords = np.column_stack(np.where(inv > 0))
    if len(coords) < 200: return gray
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < .3 or abs(angle) > 8: return gray
    mat = cv2.getRotationMatrix2D((w//2,h//2), angle, 1.0)
    return cv2.warpAffine(gray, mat, (w,h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

def preprocess_gray(gray: np.ndarray, feature_kind: str) -> np.ndarray:
    if feature_kind == "enhanced":
        return apply_clahe(deskew_document(crop_document_margins(gray)))
    return gray

def save_page_preview(file_hash: str, page_no: int, gray: np.ndarray) -> str:
    path = IMAGE_DIR / f"{file_hash}_p{page_no}.jpg"
    if not path.exists(): cv2.imwrite(str(path), gray, [int(cv2.IMWRITE_JPEG_QUALITY),82])
    return str(path)

def phash_cv(gray: np.ndarray, hash_size: int = 8, highfreq_factor: int = 4) -> np.ndarray:
    size = hash_size * highfreq_factor
    dct = cv2.dct(np.float32(cv2.resize(gray,(size,size),interpolation=cv2.INTER_AREA)))
    low = dct[:hash_size,:hash_size]
    return (low > np.median(low[1:,1:])).flatten()

def hash_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None or a.shape != b.shape: return 0.0
    return max(0.0, 1.0 - np.count_nonzero(a != b)/float(a.size))

def compute_orb_desc(gray: np.ndarray) -> Optional[np.ndarray]:
    orb = cv2.ORB_create(nfeatures=1800, scaleFactor=1.2, nlevels=8, edgeThreshold=15, patchSize=31, fastThreshold=12)
    _, desc = orb.detectAndCompute(cv2.equalizeHist(gray), None)
    return desc

def orb_similarity(desc1: Optional[np.ndarray], desc2: Optional[np.ndarray]) -> float:
    if desc1 is None or desc2 is None or len(desc1) < 10 or len(desc2) < 10: return 0.0
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(desc1, desc2)
    if not matches: return 0.0
    dist = np.array([m.distance for m in matches], dtype=np.float32)
    good = np.sort(dist[dist <= 70])[:80]
    if len(good) == 0: return 0.0
    return float(0.65*min(len(good)/80.0,1.0) + 0.35*max(0.0,1.0-float(np.mean(good))/70.0))

def register_cert_file(path: Path, source_type: str = "template", source_batch_id: str = "") -> Dict:
    fhash = file_sha256(path)
    stat = path.stat()
    page_count = get_pdf_page_count(path)

    with DB_WRITE_LOCK:
        with get_conn() as conn:
            conn.execute('''INSERT OR IGNORE INTO cert_files
            (file_hash, original_filename, stored_path, source_type, source_batch_id, file_size, page_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (
                fhash, path.name, str(path), source_type, source_batch_id,
                stat.st_size, page_count, now_text()
            ))

    return {"file_hash":fhash,"filename":path.name,"path":str(path),"page_count":page_count,"file_size":stat.st_size}

def build_feature_for_image(img: Image.Image, file_hash: str, page_no: int, feature_kind: str) -> Dict:
    gray = preprocess_gray(pil_to_cv_gray(img), feature_kind)
    h,_ = gray.shape[:2]
    header = gray[:max(1,int(h*.38)),:]
    orb = compute_orb_desc(gray)
    return {"full_phash":bits_to_string(phash_cv(gray)), "header_phash":bits_to_string(phash_cv(header)), "orb_desc_path":save_orb_desc(file_hash,page_no,feature_kind,orb), "image_path":save_page_preview(file_hash,page_no,gray)}

def ensure_features_for_file(path: Path, feature_kind: str = "basic", max_pages: int = DEFAULT_MAX_PAGES, dpi: int = DEFAULT_DPI, source_type: str = "runtime") -> str:
    fhash = register_cert_file(path, source_type=source_type)["file_hash"]
    pages = load_image_pages(path, max_pages=max_pages, dpi=dpi)

    for idx, img in enumerate(pages, start=1):
        with get_conn() as conn:
            exists = conn.execute('''SELECT id FROM cert_image_features
                WHERE file_hash=? AND page_no=? AND feature_kind=? AND feature_version=?''',
                (fhash, idx, feature_kind, FEATURE_VERSION)
            ).fetchone()

        if exists:
            continue

        # heavy OpenCV work must be outside a sqlite write transaction.
        ft = build_feature_for_image(img, fhash, idx, feature_kind)

        with DB_WRITE_LOCK:
            with get_conn() as conn:
                conn.execute('''INSERT OR REPLACE INTO cert_image_features
                (file_hash,page_no,feature_kind,feature_version,full_phash,header_phash,orb_desc_path,image_path,created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                    fhash, idx, feature_kind, FEATURE_VERSION,
                    ft["full_phash"], ft["header_phash"], ft["orb_desc_path"], ft["image_path"], now_text()
                ))

    return fhash

def import_template_folder(root_dir: str, rebuild: bool = False, max_pages: int = DEFAULT_MAX_PAGES) -> Dict:
    root = Path(root_dir)
    if not root.exists():
        raise FileNotFoundError(f"학습 폴더가 없습니다: {root}")

    # Do not hold one sqlite connection while ensure_features_for_file() opens/writes using another connection.
    # That nested write pattern caused sqlite3.OperationalError: database is locked.
    reset_cert_template_db() if rebuild else init_cert_template_db()

    started = time.time()
    total_files = 0
    total_pages = 0
    errors = []

    for folder in get_org_folders(root):
        org = normalize_org_label(folder.name)

        for path in list_supported_files(folder):
            total_files += 1

            try:
                fhash = ensure_features_for_file(path, "basic", max_pages, source_type="template")
                ensure_features_for_file(path, "enhanced", max_pages, source_type="template")

                with get_conn() as conn:
                    rows = conn.execute('''SELECT page_no FROM cert_image_features
                        WHERE file_hash=? AND feature_kind='basic' AND feature_version=?''',
                        (fhash, FEATURE_VERSION)
                    ).fetchall()

                with DB_WRITE_LOCK:
                    with get_conn() as conn:
                        for r in rows:
                            total_pages += 1
                            conn.execute('''INSERT OR IGNORE INTO cert_template_refs
                            (cert_org,template_id,source_filename,source_path,file_hash,page_no,feature_version,is_active,created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)''', (
                                org, f"{org}_P{int(r['page_no'])}", path.name, str(path),
                                fhash, int(r["page_no"]), FEATURE_VERSION, now_text()
                            ))

            except Exception as e:
                errors.append({
                    "org": org,
                    "file": str(path),
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                })

    return {
        "ok": True,
        "root_dir": str(root),
        "rebuild": rebuild,
        "file_count": total_files,
        "page_feature_count": total_pages,
        "error_count": len(errors),
        "errors": errors[:30],
        "elapsed_sec": round(time.time() - started, 2),
    }

def get_template_status() -> Dict:
    init_cert_template_db()
    with get_conn() as conn:
        org_rows = conn.execute('''SELECT cert_org, COUNT(DISTINCT file_hash) file_count, COUNT(*) page_count FROM cert_template_refs WHERE is_active=1 AND feature_version=? GROUP BY cert_org ORDER BY cert_org''', (FEATURE_VERSION,)).fetchall()
        feature_count = conn.execute('''SELECT COUNT(*) cnt FROM cert_image_features WHERE feature_version=?''',(FEATURE_VERSION,)).fetchone()["cnt"]
        cand_count = conn.execute('SELECT COUNT(*) cnt FROM cert_org_candidates').fetchone()["cnt"]
        dec_count = conn.execute('SELECT COUNT(*) cnt FROM cert_org_decisions').fetchone()["cnt"]
    orgs = [{"cert_org":r["cert_org"],"file_count":int(r["file_count"]),"page_count":int(r["page_count"])} for r in org_rows]
    return {"ok":True,"db_path":str(DB_PATH),"store_dir":str(STORE_DIR),"feature_version":FEATURE_VERSION,"org_count":len(orgs),"template_file_count":sum(x["file_count"] for x in orgs),"template_page_count":sum(x["page_count"] for x in orgs),"feature_count":int(feature_count),"candidate_count":int(cand_count),"manual_decision_count":int(dec_count),"orgs":orgs}

def row_to_feature(row: sqlite3.Row, org: str) -> PageFeature:
    return PageFeature(org=org, source_path=row["source_path"] if "source_path" in row.keys() else "", source_filename=row["source_filename"] if "source_filename" in row.keys() else "", file_hash=row["file_hash"], page_no=int(row["page_no"]), feature_kind=row["feature_kind"], full_hash=string_to_bits(row["full_phash"]), header_hash=string_to_bits(row["header_phash"]), orb_desc=load_orb_desc(row["orb_desc_path"]))

def load_template_features(feature_kind: str) -> List[PageFeature]:
    with get_conn() as conn:
        rows = conn.execute('''SELECT r.cert_org,r.source_path,r.source_filename,f.file_hash,f.page_no,f.feature_kind,f.full_phash,f.header_phash,f.orb_desc_path FROM cert_template_refs r JOIN cert_image_features f ON r.file_hash=f.file_hash AND r.page_no=f.page_no WHERE r.is_active=1 AND f.feature_kind=? AND f.feature_version=? AND r.feature_version=?''', (feature_kind,FEATURE_VERSION,FEATURE_VERSION)).fetchall()
    return [row_to_feature(r, r["cert_org"]) for r in rows]

def load_file_features(file_hash: str, feature_kind: str) -> List[PageFeature]:
    with get_conn() as conn:
        rows = conn.execute('''SELECT cf.stored_path source_path, cf.original_filename source_filename, f.file_hash,f.page_no,f.feature_kind,f.full_phash,f.header_phash,f.orb_desc_path FROM cert_image_features f LEFT JOIN cert_files cf ON cf.file_hash=f.file_hash WHERE f.file_hash=? AND f.feature_kind=? AND f.feature_version=?''', (file_hash,feature_kind,FEATURE_VERSION)).fetchall()
    return [row_to_feature(r, "__TARGET__") for r in rows]

def compare_page_to_ref(target: PageFeature, ref: PageFeature) -> MatchEvidence:
    full = hash_similarity(target.full_hash, ref.full_hash)
    header = hash_similarity(target.header_hash, ref.header_hash)
    orb = orb_similarity(target.orb_desc, ref.orb_desc)
    score = 0.20*full + 0.40*header + 0.40*orb
    return MatchEvidence(ref.org, float(score), target.page_no, ref.page_no, ref.source_filename, ref.file_hash, float(full), float(header), float(orb), target.feature_kind)

def decide_image_result(score: float, margin: float) -> str:
    if score >= AUTO_SCORE_THRESHOLD and margin >= AUTO_MARGIN_THRESHOLD:
        return "AUTO_IMAGE"

    if score < MANUAL_SCORE_THRESHOLD or margin < MANUAL_MARGIN_THRESHOLD:
        return "MANUAL_REVIEW"

    return "REVIEW"

def classify_by_feature_kind(file_hash: str, feature_kind: str) -> Dict:
    tfs = load_file_features(file_hash, feature_kind); refs = load_template_features(feature_kind)
    if not tfs or not refs: return {"file_hash":file_hash,"predicted_org":"NO_REFERENCE","score":0.0,"second_org":"-","second_score":0.0,"margin":0.0,"decision":"NO_REFERENCE","feature_kind":feature_kind,"top_candidates":[],"top_evidence":{}}
    evs=[]
    for tf in tfs:
        for rf in refs:
            if tf.file_hash == rf.file_hash: continue
            evs.append(compare_page_to_ref(tf, rf))
    by_org: Dict[str,List[MatchEvidence]] = {}
    for e in evs: by_org.setdefault(e.org, []).append(e)
    scores=[]
    for org, items in by_org.items():
        sitems=sorted(items,key=lambda x:x.score,reverse=True); top=sitems[0]; top3=sitems[:3]
        final=0.70*top.score + 0.30*(sum(x.score for x in top3)/len(top3))
        scores.append((org,float(final),top))
    scores=sorted(scores,key=lambda x:x[1],reverse=True)
    if not scores: return {"file_hash":file_hash,"predicted_org":"NO_REFERENCE","score":0.0,"second_org":"-","second_score":0.0,"margin":0.0,"decision":"NO_REFERENCE","feature_kind":feature_kind,"top_candidates":[],"top_evidence":{}}
    best_org,best_score,best_ev=scores[0]
    second_org,second_score=(scores[1][0],scores[1][1]) if len(scores)>=2 else ("-",0.0)
    margin=best_score-second_score
    return {"file_hash":file_hash,"predicted_org":best_org,"score":round(best_score,4),"second_org":second_org,"second_score":round(second_score,4),"margin":round(margin,4),"decision":decide_image_result(best_score,margin),"feature_kind":feature_kind,"top_candidates":[{"org":o,"score":round(s,4)} for o,s,_ in scores[:5]],"top_evidence":{"target_page":best_ev.target_page,"ref_file":best_ev.ref_file,"ref_page":best_ev.ref_page,"ref_hash":best_ev.ref_hash,"full_hash_score":round(best_ev.full_hash_score,4),"header_hash_score":round(best_ev.header_hash_score,4),"orb_score":round(best_ev.orb_score,4),"feature_kind":feature_kind}}

def get_manual_decision(file_hash: str) -> Optional[Dict]:
    with get_conn() as conn:
        row=conn.execute('SELECT * FROM cert_org_decisions WHERE file_hash=?',(file_hash,)).fetchone()
    return dict(row) if row else None

def save_candidates(result: Dict) -> None:
    run_id=f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{result['file_hash'][:10]}"
    with DB_WRITE_LOCK:
        with get_conn() as conn:
            conn.execute('DELETE FROM cert_org_candidates WHERE file_hash=?',(result['file_hash'],))
            for idx,c in enumerate(result.get('top_candidates') or [], start=1):
                conn.execute('''INSERT INTO cert_org_candidates
                (file_hash,candidate_org,rank_no,image_score,margin,decision,feature_kind,evidence_json,run_id,created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                    result['file_hash'], c['org'], idx, float(c['score']),
                    float(result.get('margin') or 0), result.get('decision') or 'UNKNOWN',
                    result.get('feature_kind') or 'basic',
                    json.dumps(result.get('top_evidence') if idx==1 else {}, ensure_ascii=False),
                    run_id, now_text()
                ))

def classify_file_path(file_path: str, enhanced_retry: bool=True, max_pages: int=DEFAULT_MAX_PAGES) -> Dict:
    init_cert_template_db(); path=Path(file_path)
    if not path.exists(): raise FileNotFoundError(f"파일이 없습니다: {path}")
    fhash=ensure_features_for_file(path,"basic",max_pages,source_type="runtime")
    manual=get_manual_decision(fhash)
    if manual:
        is_excluded = int(manual.get("is_excluded") or 0) == 1 or str(manual.get("decision_type") or "").upper() == "EXCLUDED"
        final_org = manual.get("final_org") or manual.get("predicted_org") or "-"

        if is_excluded:
            return {
                "file_hash": fhash,
                "filename": path.name,
                "file_path": str(path),
                "predicted_org": final_org,
                "score": manual.get("decision_score") or manual.get("image_score") or 0.0,
                "second_org": "-",
                "second_score": 0.0,
                "margin": manual.get("margin") or 0.0,
                "decision": "EXCLUDED",
                "feature_kind": "manual",
                "top_candidates": [],
                "top_evidence": {"manual_reason": manual.get("decision_reason") or manual.get("memo") or "excluded"},
                "manual_decision": manual,
            }

        return {
            "file_hash": fhash,
            "filename": path.name,
            "file_path": str(path),
            "predicted_org": final_org,
            "score": manual.get("decision_score") or manual.get("image_score") or 1.0,
            "second_org": "-",
            "second_score": 0.0,
            "margin": manual.get("margin") or 1.0,
            "decision": manual.get("decision_type") or "MANUAL_CONFIRMED",
            "feature_kind": "manual",
            "top_candidates": [{"org": final_org, "score": manual.get("decision_score") or manual.get("image_score") or 1.0}],
            "top_evidence": {"manual_reason": manual.get("decision_reason") or manual.get("memo") or "manual"},
            "manual_decision": manual,
        }

    basic=classify_by_feature_kind(fhash,"basic"); chosen=basic
    if enhanced_retry and (float(basic.get('score') or 0) < RETRY_SCORE_THRESHOLD or float(basic.get('margin') or 0) < RETRY_MARGIN_THRESHOLD):
        ensure_features_for_file(path,"enhanced",max_pages,source_type="runtime")
        enh=classify_by_feature_kind(fhash,"enhanced")
        if float(enh.get('score') or 0) > float(basic.get('score') or 0) or float(enh.get('margin') or 0) > float(basic.get('margin') or 0):
            chosen=enh
    chosen.update({"filename":path.name,"file_path":str(path),"manual_decision":None})
    save_candidates(chosen)
    return chosen

def classify_paths(paths: List[str], enhanced_retry: bool=True) -> List[Dict]:
    rows=[]
    for p in paths:
        try: rows.append(classify_file_path(p, enhanced_retry=enhanced_retry))
        except Exception as e: rows.append({"file_path":p,"filename":Path(p).name,"predicted_org":"ERROR","score":0.0,"second_org":"-","second_score":0.0,"margin":0.0,"decision":"ERROR","top_candidates":[],"top_evidence":{},"error":str(e),"traceback":traceback.format_exc()})
    return rows

def classify_folder(folder_path: str, enhanced_retry: bool=True) -> Dict:
    folder=Path(folder_path)
    if not folder.exists(): raise FileNotFoundError(f"테스트 폴더가 없습니다: {folder}")
    files=list_supported_files(folder)
    return {"ok":True,"folder_path":str(folder),"count":len(files),"rows":classify_paths([str(p) for p in files], enhanced_retry=enhanced_retry)}

def get_review_items(limit: int=100) -> Dict:
    with get_conn() as conn:
        rows=conn.execute('''SELECT c.file_hash,c.decision,c.margin,MAX(CASE WHEN c.rank_no=1 THEN c.candidate_org END) top1_org,MAX(CASE WHEN c.rank_no=1 THEN c.image_score END) top1_score,MAX(CASE WHEN c.rank_no=2 THEN c.candidate_org END) top2_org,MAX(CASE WHEN c.rank_no=2 THEN c.image_score END) top2_score,cf.original_filename,cf.stored_path FROM cert_org_candidates c LEFT JOIN cert_files cf ON cf.file_hash=c.file_hash LEFT JOIN cert_org_decisions d ON d.file_hash=c.file_hash WHERE c.decision IN ('REVIEW','MANUAL_REVIEW','NO_REFERENCE') AND d.file_hash IS NULL GROUP BY c.file_hash ORDER BY MAX(c.created_at) DESC LIMIT ?''',(limit,)).fetchall()
    return {"ok":True,"rows":[dict(r) for r in rows]}

def normalize_decision_type(value: str) -> str:
    text = str(value or "").strip().upper()
    allowed = {
        "AUTO_CONFIRMED",
        "MANUAL_CONFIRMED",
        "MANUAL_CORRECTED",
        "EXCLUDED",
        "RESTORED",
        "MANUAL",
    }
    return text if text in allowed else "MANUAL_CONFIRMED"


def decision_is_excluded(decision_type: str) -> int:
    return 1 if normalize_decision_type(decision_type) == "EXCLUDED" else 0


def save_org_decision(
    file_hash: str,
    final_org: str,
    decision_type: str = "MANUAL_CONFIRMED",
    decision_score: float = 1.0,
    decision_reason: str = "",
    confirmed_by: str = "admin",
    predicted_org: str = "",
    original_decision: str = "",
    original_filename: str = "",
    file_path: str = "",
    image_score: float = 0.0,
    margin: float = 0.0,
    memo: str = "",
) -> Dict:
    init_cert_template_db()

    normalized_type = normalize_decision_type(decision_type)
    org = normalize_org_label(final_org or predicted_org or "-")
    pred = normalize_org_label(predicted_org or final_org or "-")
    excluded = decision_is_excluded(normalized_type)
    score = float(decision_score or image_score or 0)
    image_score_value = float(image_score or score or 0)
    margin_value = float(margin or 0)
    reason = decision_reason or memo or normalized_type

    with DB_WRITE_LOCK:
        with get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO cert_org_decisions (
                    file_hash, final_org, decision_type, decision_score, decision_reason,
                    confirmed_by, confirmed_at, predicted_org, original_decision,
                    original_filename, file_path, image_score, margin, is_excluded, memo, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    file_hash,
                    org,
                    normalized_type,
                    score,
                    reason,
                    confirmed_by or "admin",
                    now_text(),
                    pred,
                    original_decision or "",
                    original_filename or "",
                    file_path or "",
                    image_score_value,
                    margin_value,
                    excluded,
                    memo or "",
                    now_text(),
                ),
            )

    return {
        "ok": True,
        "file_hash": file_hash,
        "predicted_org": pred,
        "final_org": org,
        "decision_type": normalized_type,
        "is_excluded": excluded,
    }


def save_org_decisions_bulk(items: List[Dict], confirmed_by: str = "admin") -> Dict:
    saved = []
    errors = []

    for idx, item in enumerate(items or []):
        try:
            saved.append(
                save_org_decision(
                    file_hash=item.get("file_hash") or "",
                    predicted_org=item.get("predicted_org") or "",
                    final_org=item.get("final_org") or item.get("predicted_org") or "-",
                    decision_type=item.get("decision_type") or "MANUAL_CONFIRMED",
                    decision_score=float(item.get("decision_score") or item.get("score") or item.get("image_score") or 0),
                    decision_reason=item.get("decision_reason") or item.get("memo") or "",
                    confirmed_by=item.get("confirmed_by") or confirmed_by or "admin",
                    original_decision=item.get("original_decision") or item.get("decision") or "",
                    original_filename=item.get("original_filename") or item.get("filename") or "",
                    file_path=item.get("file_path") or "",
                    image_score=float(item.get("image_score") or item.get("score") or 0),
                    margin=float(item.get("margin") or 0),
                    memo=item.get("memo") or "",
                )
            )
        except Exception as exc:
            errors.append({"index": idx, "file_hash": item.get("file_hash"), "error": str(exc)})

    return {"ok": len(errors) == 0, "saved_count": len(saved), "error_count": len(errors), "saved": saved, "errors": errors}


def get_org_decisions(include_excluded: bool = True, limit: int = 500) -> Dict:
    init_cert_template_db()

    where = ""
    params: List = []

    if not include_excluded:
        where = "WHERE COALESCE(is_excluded, 0) = 0 AND decision_type <> 'EXCLUDED'"

    params.append(int(limit))

    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT
                d.*,
                cf.original_filename AS current_filename,
                cf.stored_path AS current_file_path
            FROM cert_org_decisions d
            LEFT JOIN cert_files cf ON cf.file_hash = d.file_hash
            {where}
            ORDER BY COALESCE(d.updated_at, d.confirmed_at) DESC
            LIMIT ?""",
            params,
        ).fetchall()

    return {"ok": True, "rows": [dict(r) for r in rows]}


def clear_org_decision(file_hash: str, confirmed_by: str = "admin") -> Dict:
    """Remove the administrator decision for a file_hash.

    This is intentionally a hard delete from cert_org_decisions so that
    the next test/classification falls back to the raw image decision
    (AUTO_IMAGE / REVIEW / MANUAL_REVIEW).
    """
    init_cert_template_db()
    target_hash = str(file_hash or "").strip()

    if not target_hash:
        raise ValueError("file_hash is required")

    with DB_WRITE_LOCK:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM cert_org_decisions WHERE file_hash = ?",
                (target_hash,),
            ).fetchone()

            conn.execute(
                "DELETE FROM cert_org_decisions WHERE file_hash = ?",
                (target_hash,),
            )

    return {
        "ok": True,
        "file_hash": target_hash,
        "cleared": bool(row),
        "confirmed_by": confirmed_by or "admin",
    }


def clear_org_decisions_bulk(file_hashes: List[str], confirmed_by: str = "admin") -> Dict:
    cleared = []
    errors = []

    for idx, file_hash in enumerate(file_hashes or []):
        try:
            cleared.append(clear_org_decision(file_hash=file_hash, confirmed_by=confirmed_by))
        except Exception as exc:
            errors.append({"index": idx, "file_hash": file_hash, "error": str(exc)})

    return {
        "ok": len(errors) == 0,
        "cleared_count": len(cleared),
        "error_count": len(errors),
        "cleared": cleared,
        "errors": errors,
    }

def get_candidates(file_hash: str) -> Dict:
    with get_conn() as conn:
        rows=conn.execute('SELECT * FROM cert_org_candidates WHERE file_hash=? ORDER BY rank_no ASC',(file_hash,)).fetchall()
    return {"ok":True,"rows":[dict(r) for r in rows]}

def get_preview_image_path(file_hash: str) -> Optional[Path]:
    with get_conn() as conn:
        row=conn.execute('SELECT image_path FROM cert_image_features WHERE file_hash=? ORDER BY page_no ASC LIMIT 1',(file_hash,)).fetchone()
    if not row or not row['image_path']: return None
    p=Path(row['image_path'])
    return p if p.exists() else None
