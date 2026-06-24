from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import pmf, suppliers, mail, lhln, ocr
from app.routers import cert_template
from app.routers import ai_rule_review

app = FastAPI(
    title="SEWOO Halal Console API",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
app.include_router(cert_template.router)

@app.get("/health")
def health():
    return {"ok": True}