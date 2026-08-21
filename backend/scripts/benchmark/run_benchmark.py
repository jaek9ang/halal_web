import os
import json
import re
import time
import base64
import fitz  # PyMuPDF
from openai import OpenAI
from pydantic import BaseModel, Field

# ==========================================
# 1. 설정
# ==========================================
API_KEY = os.environ.get("OPENAI_API_KEY")

if not API_KEY:
    print("❌ 오류: OpenAI API 키가 설정되지 않았습니다.")
    exit(1)

client = OpenAI(api_key=API_KEY)

PDF_DIR = r"D:\halal_baseline_review_100"
BASELINE_HTML_PATH = r"C:\Users\user\Downloads\halal_ocr_baseline_google_dashboard.html"
OUTPUT_HTML_PATH = r"C:\Users\user\Downloads\llm_comparison_report.html"

class HalalCert(BaseModel):
    cert_org: str = Field(description="인증기관명 (예: MUI, JAKIM, BPJPH, HFFIA 등)")
    cert_country: str = Field(description="인증국가 영문명")
    cert_no: str = Field(description="할랄 인증번호")
    expiry_date: str = Field(description="유효기간 (YYYY-MM-DD 형식, 없으면 빈 문자열)")
    manufacturer: str = Field(description="제조사명 (주소나 노이즈 제외한 순수 회사명)")
    manufacturing_country: str = Field(description="제조국가 영문명 (인증국가가 아닌 실제 공장/제조사 위치 기준)")

def load_ground_truth(html_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    match = re.search(r'const DATA = ({.*?});\s*const FIELDS', content, re.DOTALL)
    if match:
        data = json.loads(match.group(1))
        return {row['파일명'].strip(): row for row in data['review_rows']}
    return {}

def find_gt_row(filename, gt_data):
    if filename.strip() in gt_data:
        return gt_data[filename.strip()]
    for gt_file, row in gt_data.items():
        if filename in gt_file or gt_file in filename:
            return row
    return None

def pdf_to_base64_image(pdf_path):
    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode('utf-8')

# ==========================================
# 메인 로직
# ==========================================
def main():
    print("🚀 OpenAI (GPT-4o-mini) 할랄 인증서 벤치마크를 시작합니다...")
    
    gt_data = load_ground_truth(BASELINE_HTML_PATH)
    if not gt_data:
        print("❌ 기존 HTML에서 정답 데이터를 찾을 수 없습니다. 경로를 확인해주세요.")
        return
        
    print(f"✅ Baseline 정답 데이터 {len(gt_data)}건 로드 완료.\n")
    
    results = []
    pdf_files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith('.pdf')]
    
    stats = {
        "docs": 0, "total_fields": 0,
        "rule_correct": 0, "llm_correct": 0, "hybrid_correct": 0,
        "rule_full_match": 0, "llm_full_match": 0, "hybrid_full_match": 0
    }
    
    for idx, filename in enumerate(pdf_files, 1):
        gt_row = find_gt_row(filename, gt_data)
        if not gt_row:
            print(f"⚠️ 매칭되는 정답을 찾지 못함 스킵: {filename}")
            continue
            
        pdf_path = os.path.join(PDF_DIR, filename)
        print(f"[{idx}/{len(pdf_files)}] 분석 중: {filename}")
        
        try:
            base64_image = pdf_to_base64_image(pdf_path)
            
            # ★ Rate Limit(429) 에러 발생 시 대기 후 재시도하는 로직 추가 ★
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    response = client.beta.chat.completions.parse(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "당신은 할랄 인증서 판독 전문가입니다. 첨부된 이미지의 텍스트와 레이아웃을 종합적으로 분석하여 요청된 JSON 형식으로 데이터를 정확하게 추출하세요."},
                            {"role": "user", "content": [{"type": "text", "text": "이 인증서에서 정보를 추출해줘."}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}]}
                        ],
                        response_format=HalalCert,
                        temperature=0.0
                    )
                    elapsed_time = time.time() - start_time
                    break  # 성공하면 루프 탈출
                    
                except Exception as e:
                    if "429" in str(e) or "rate_limit" in str(e):
                        wait_time = 20  # 20초 대기
                        print(f"   ⏳ API 한도 초과! {wait_time}초 대기 후 재시도합니다... ({attempt+1}/{max_retries})")
                        time.sleep(wait_time)
                    else:
                        raise e # 다른 에러면 그대로 던짐
                        
            llm_result = json.loads(response.choices[0].message.content)
            
            fields_to_check = {
                "인증기관": "cert_org", "인증국가": "cert_country", 
                "인증번호": "cert_no", "유효기간": "expiry_date", 
                "제조사": "manufacturer", "제조국": "manufacturing_country"
            }
            
            row_data = {
                "filename": filename,
                "org": gt_row.get("기관", "Unknown"),
                "conf": gt_row.get("시스템CONFIDENCE", "UNKNOWN"),
                "time": elapsed_time,
                "fields": {}
            }
            
            rule_errors = 0
            llm_errors = 0
            hybrid_errors = 0
            
            is_low_conf = (row_data["conf"] == "LOW" or gt_row.get("PARSE_STATUS") in ["LOW_CONFIDENCE", "FILENAME_ONLY"])

            for kr_field, en_field in fields_to_check.items():
                gt_val = gt_row.get(f"정답_{kr_field}", "").strip().lower()
                rule_val = gt_row.get(f"추출_{kr_field}", "").strip().lower()
                llm_val = str(llm_result.get(en_field, "")).strip().lower()
                hybrid_val = llm_val if is_low_conf else rule_val

                r_match = (gt_val == rule_val)
                l_match = (gt_val == llm_val)
                h_match = (gt_val == hybrid_val)

                if not r_match: rule_errors += 1
                if not l_match: llm_errors += 1
                if not h_match: hybrid_errors += 1
                
                stats["total_fields"] += 1
                if r_match: stats["rule_correct"] += 1
                if l_match: stats["llm_correct"] += 1
                if h_match: stats["hybrid_correct"] += 1
                
                row_data["fields"][kr_field] = {
                    "gt": gt_row.get(f"정답_{kr_field}", ""),
                    "rule_val": gt_row.get(f"추출_{kr_field}", ""),
                    "llm_val": str(llm_result.get(en_field, "")),
                    "hybrid_val": str(llm_result.get(en_field, "")) if is_low_conf else gt_row.get(f"추출_{kr_field}", ""),
                    "r_match": r_match, "l_match": l_match, "h_match": h_match
                }
                
            stats["docs"] += 1
            if rule_errors == 0: stats["rule_full_match"] += 1
            if llm_errors == 0: stats["llm_full_match"] += 1
            if hybrid_errors == 0: stats["hybrid_full_match"] += 1
            
            results.append(row_data)
            
            # 다음 문서로 넘어가기 전에 기본적으로 2초 휴식 (한도 초과 방지)
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ 오류 발생 ({filename}): {e}")

    if stats["docs"] == 0:
        print("❌ 테스트된 문서가 없습니다.")
        return

    # ==========================================
    # 5. 리포트 생성 (UI 코드 내장)
    # ==========================================
    html_template = """
    <!doctype html>
    <html lang="ko">
    <head>
    <meta charset="utf-8">
    <title>Halal OCR: Rule vs LLM Performance</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { margin:0; background:#F8FAFC; color:#0F172A; font-family:-apple-system, sans-serif; }
        .topbar { background:#fff; padding:20px 32px; border-bottom:1px solid #E2E8F0; display:flex; justify-content:space-between; align-items:center; }
        .title { font-size: 22px; font-weight: bold; color:#1E293B; }
        .badge { background:#EEF2FF; color:#4F46E5; padding:6px 12px; border-radius:20px; font-size:13px; font-weight:bold; }
        .content { padding: 40px; max-width: 1400px; margin: 0 auto; }
        .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin-bottom: 30px; }
        .card { background:#fff; padding:24px; border-radius:16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #E2E8F0; }
        .kpi { font-size: 42px; font-weight: 800; margin: 10px 0; }
        .kpi.rule { color: #64748B; } .kpi.hybrid { color: #4F46E5; } .kpi.llm { color: #10B981; }
        .sub-text { font-size: 14px; color: #64748B; font-weight: bold; }
        table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }
        th, td { padding: 12px 16px; border-bottom: 1px solid #E2E8F0; text-align: left; font-size: 13px; }
        th { background: #F8FAFC; color: #64748B; font-weight: bold; }
        .err { color: #EF4444; font-weight: bold; }
        .ok { color: #10B981; font-weight: bold; }
        .filters { margin-bottom: 20px; display: flex; gap: 10px; }
        select { padding: 8px 12px; border-radius: 8px; border: 1px solid #E2E8F0; outline: none; }
    </style>
    </head>
    <body>
        <div class="topbar">
            <div class="title">Halal OCR Benchmark Report (OpenAI)</div>
            <div class="badge">검증 완료: {DOCS}건</div>
        </div>
        <div class="content">
            <div class="grid-3">
                <div class="card" style="border-top: 4px solid #64748B;">
                    <h3>1. 기존 Rule 방식</h3>
                    <div class="kpi rule">{RULE_ACC}%</div>
                    <div class="sub-text">완전일치 문서: {RULE_FULL} / {DOCS}건</div>
                </div>
                <div class="card" style="border-top: 4px solid #4F46E5; background: #F8FAFF;">
                    <h3>2. Hybrid 방식 (Low Conf만 LLM)</h3>
                    <div class="kpi hybrid">{HYBRID_ACC}%</div>
                    <div class="sub-text">완전일치 문서: {HYBRID_FULL} / {DOCS}건</div>
                </div>
                <div class="card" style="border-top: 4px solid #10B981;">
                    <h3>3. Full LLM 방식</h3>
                    <div class="kpi llm">{LLM_ACC}%</div>
                    <div class="sub-text">완전일치 문서: {LLM_FULL} / {DOCS}건</div>
                </div>
            </div>

            <div class="card" style="margin-bottom:30px;">
                <h3>상세 데이터 비교 (Rule vs LLM)</h3>
                <div class="filters">
                    <select id="fField" onchange="renderTable()">
                        <option value="인증번호">인증번호 비교</option>
                        <option value="제조사">제조사 비교</option>
                        <option value="유효기간">유효기간 비교</option>
                        <option value="제조국">제조국 비교</option>
                        <option value="인증기관">인증기관 비교</option>
                        <option value="인증국가">인증국가 비교</option>
                    </select>
                </div>
                <div style="overflow-x: auto;">
                    <table id="dataTable">
                        <thead>
                            <tr>
                                <th>파일명</th>
                                <th>기관</th>
                                <th>Conf</th>
                                <th>PDF 정답</th>
                                <th>Rule 추출</th>
                                <th>LLM 추출</th>
                                <th>Hybrid 채택값</th>
                            </tr>
                        </thead>
                        <tbody id="dataBody"></tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <script>
            const results = {RESULTS_JSON};
            
            function formatCell(val, match) {
                return match ? `<span class="ok">${val || '-'}</span>` : `<span class="err">${val || '미추출'}</span>`;
            }

            function renderTable() {
                const field = document.getElementById('fField').value;
                const tbody = document.getElementById('dataBody');
                tbody.innerHTML = '';
                
                results.forEach(r => {
                    const fData = r.fields[field];
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td style="max-width:200px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${r.filename}">${r.filename}</td>
                        <td><b>${r.org}</b></td>
                        <td>${r.conf}</td>
                        <td style="color:#10B981; font-weight:bold;">${fData.gt || '-'}</td>
                        <td>${formatCell(fData.rule_val, fData.r_match)}</td>
                        <td>${formatCell(fData.llm_val, fData.l_match)}</td>
                        <td style="background:#F8FAFF;">${formatCell(fData.hybrid_val, fData.h_match)}</td>
                    `;
                    tbody.appendChild(tr);
                });
            }
            renderTable();
        </script>
    </body>
    </html>
    """

    html_out = html_template.replace("{DOCS}", str(stats["docs"]))
    html_out = html_out.replace("{RULE_ACC}", f"{(stats['rule_correct']/stats['total_fields']*100):.1f}")
    html_out = html_out.replace("{HYBRID_ACC}", f"{(stats['hybrid_correct']/stats['total_fields']*100):.1f}")
    html_out = html_out.replace("{LLM_ACC}", f"{(stats['llm_correct']/stats['total_fields']*100):.1f}")
    html_out = html_out.replace("{RULE_FULL}", str(stats["rule_full_match"]))
    html_out = html_out.replace("{HYBRID_FULL}", str(stats["hybrid_full_match"]))
    html_out = html_out.replace("{LLM_FULL}", str(stats["llm_full_match"]))
    html_out = html_out.replace("{RESULTS_JSON}", json.dumps(results, ensure_ascii=False))

    with open(OUTPUT_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html_out)
        
    print(f"\n🎉 벤치마크 완료! 세련된 대시보드가 생성되었습니다: {OUTPUT_HTML_PATH}")

if __name__ == "__main__":
    main()