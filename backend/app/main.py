import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import ensure_runtime_dirs
from app.routers import pmf, suppliers, mail, lhln, ocr
from app.routers import cert_template
from app.routers import ai_rule_review
from app.routers import certificate_filing

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "").strip() or DEFAULT_CORS_ORIGINS
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 캐시·출력·DB 폴더는 gitignore 대상이라 새 작업본에는 없다.
    ensure_runtime_dirs()
    yield


app = FastAPI(
    title="SEWOO Halal Console API",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pmf.router, prefix="/pmf", tags=["PMF"])
app.include_router(suppliers.router, prefix="/suppliers", tags=["Suppliers"])
app.include_router(mail.router, prefix="/mail", tags=["Mail"])
app.include_router(lhln.router, prefix="/lhln", tags=["LHLN"])
app.include_router(ocr.router, prefix="/ocr", tags=["OCR"])
app.include_router(
    ai_rule_review.router,
    prefix="/ai-rule-review",
    tags=["AI Rule Review"],
)
# cert_template 라우터는 prefix를 자기 파일에 들고 있다.
app.include_router(cert_template.router)
app.include_router(
    certificate_filing.router,
    prefix="/certificate-filing",
    tags=["Certificate Filing"],
)


@app.get("/health")
def health():
    return {"ok": True}
