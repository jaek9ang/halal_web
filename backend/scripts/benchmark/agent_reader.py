"""도구를 쓰는 인증서 판독 에이전트.

기존 LLM 판독은 단발 호출이었다 — 1페이지를 PNG로 렌더해 던지고 JSON을 받는다.
모델은 자기가 뭘 더 봐야 하는지 알아도 가져올 수단이 없었다. 그래서:

- 부속서(BPJPH LAMPIRAN 등)에 제품·제조사가 있어도 1페이지만 보고 답했다.
- PDF에 텍스트 레이어가 있어도 흐린 이미지만 보고 인증번호를 읽었다.
- 우리 시스템의 정규 기관명 목록을 모른 채 서류 원문 표기를 그대로 뱉었다.
- 이미 계산되어 있는 양식 분류 결과를 쓰지 못했다.

여기서는 그 정보들을 **도구**로 열어주고 모델이 필요할 때 직접 부르게 한다.
루프는 두 단계다: 도구를 쓰며 탐색 -> 마지막에 구조화 스키마로 확정.

## 넣지 않은 도구 (의도적)

- **PMF 기존값 조회.** 기존 인증번호·제조사를 보여주면 모델이 그대로 베껴 쓴다.
  업체가 작년 인증서를 재발송해도 "일치"로 통과시키게 된다. 기존값 대조는 판독이
  끝난 뒤 별도 검증 단계(`rules/context.py`)에서 한다. 판독 중에는 서류만 본다.
- **쓰기 도구 전부.** 이 에이전트는 아무것도 바꾸지 않는다. 판독 결과만 돌려준다.
- **메일 본문 조회.** 관리번호로 연결된 메일에는 업체가 자기 제품명을 적어 보내지만,
  그건 업체 주장이지 인증서 내용이 아니다. 교차검증 재료지 판독 재료가 아니다.

## 비용

도구 호출은 매 라운드 컨텍스트를 키운다. `max_iterations`와 `max_tool_calls`로
상한을 두고, 넘으면 그 시점까지의 정보로 확정한다.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any, Callable

import fitz

# 도구들이 app.services.* 를 쓴다. 호출자가 경로를 잡아 줬으리라 가정하지 않는다.
BACKEND_DIR = Path(__file__).resolve().parents[2]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


MAX_TEXT_CHARS = 4000

MAX_RULE_TEXT_PAGES = 3


# ==========================================
# 도구 구현
# ==========================================

class CertificateToolbox:
    """읽기 전용 도구 모음. 한 문서에 하나씩 만든다."""

    def __init__(self, pdf_path: Path, zoom: float = 2.0) -> None:
        self.pdf_path = Path(pdf_path)
        self.zoom = zoom
        self.calls: list[dict[str, Any]] = []
        self.pending_images: list[tuple[int, str]] = []

    # -- 문서 구조 ---------------------------------------------------

    def get_document_overview(self) -> dict[str, Any]:
        """페이지 수와 페이지별 텍스트 레이어 유무."""
        doc = fitz.open(self.pdf_path)
        try:
            pages = [
                {"page": i + 1, "text_chars": len(doc.load_page(i).get_text("text").strip())}
                for i in range(doc.page_count)
            ]
        finally:
            doc.close()

        return {
            "filename": self.pdf_path.name,
            "page_count": len(pages),
            "pages": pages,
            "has_text_layer": any(p["text_chars"] > 0 for p in pages),
        }

    def read_page_text(self, page: int) -> dict[str, Any]:
        """PDF에 박혀 있는 텍스트 레이어를 그대로 읽는다. OCR보다 정확하다."""
        doc = fitz.open(self.pdf_path)
        try:
            if not 1 <= page <= doc.page_count:
                return {"error": f"page {page}는 범위 밖입니다 (1~{doc.page_count})"}
            text = doc.load_page(page - 1).get_text("text").strip()
        finally:
            doc.close()

        if not text:
            return {"page": page, "text": "", "note": "이 페이지에는 텍스트 레이어가 없습니다. view_page_image로 보세요."}
        return {"page": page, "text": text[:MAX_TEXT_CHARS], "truncated": len(text) > MAX_TEXT_CHARS}

    def view_page_image(self, page: int) -> dict[str, Any]:
        """해당 페이지를 이미지로 첨부한다. 실제 이미지는 다음 메시지로 전달된다."""
        doc = fitz.open(self.pdf_path)
        try:
            if not 1 <= page <= doc.page_count:
                return {"error": f"page {page}는 범위 밖입니다 (1~{doc.page_count})"}
            pix = doc.load_page(page - 1).get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom))
            encoded = base64.b64encode(pix.tobytes("png")).decode("utf-8")
        finally:
            doc.close()

        self.pending_images.append((page, encoded))
        return {"page": page, "status": "이미지를 첨부했습니다. 다음 메시지에서 확인하세요."}

    # -- 우리 시스템의 지식 -------------------------------------------

    def list_certification_organizations(self) -> dict[str, Any]:
        """시스템이 아는 인증기관 정규명과 별칭. 답은 반드시 이 정규명으로 낸다."""
        from app.services.rules.organizations import ORG_ALIASES

        return {
            "note": "cert_org는 반드시 code 값으로 답하십시오. 서류 원문 표기가 aliases에 있으면 대응하는 code로 바꾸십시오.",
            "organizations": [
                {"code": org, "default_country": country, "aliases": aliases}
                for org, country, aliases in ORG_ALIASES
            ],
        }

    def classify_document_template(self) -> dict[str, Any]:
        """서류 생김새(pHash/ORB)를 등록된 양식과 대조해 기관 후보를 낸다."""
        try:
            from app.services.cert_template_service import classify_file_path
        except Exception as exc:
            return {"available": False, "reason": f"양식 분류를 쓸 수 없습니다: {type(exc).__name__}"}

        try:
            row = classify_file_path(str(self.pdf_path), enhanced_retry=True, max_pages=1)
        except Exception as exc:
            return {"available": False, "reason": f"분류 실패: {type(exc).__name__}"}

        return {
            "available": True,
            "predicted_org": row.get("predicted_org"),
            "score": row.get("score"),
            "second_org": row.get("second_org"),
            "margin": row.get("margin"),
            "decision": row.get("decision"),
            "note": "decision이 AUTO_IMAGE일 때만 신뢰할 만합니다. 그 외에는 참고만 하고 서류를 직접 보십시오.",
        }

    def read_with_rule_engine(self) -> dict[str, Any]:
        """기존 규칙 판독기의 결과. 다르면 서류를 다시 보고 스스로 판단하십시오."""
        from app.services.rules.core import parse_certificate_rule

        doc = fitz.open(self.pdf_path)
        try:
            pages = min(doc.page_count, MAX_RULE_TEXT_PAGES)
            raw_text = "\n".join(doc.load_page(i).get_text("text") for i in range(pages))
        finally:
            doc.close()

        if not raw_text.strip():
            return {"available": False, "reason": "텍스트 레이어가 없어 규칙 판독기를 돌릴 수 없습니다."}

        result = parse_certificate_rule(raw_text=raw_text, filename=self.pdf_path.name)
        return {
            "available": True,
            "cert_org": result.get("cert_org"),
            "cert_country": result.get("cert_country"),
            "cert_no": result.get("cert_no"),
            "expiry_date": result.get("expiry_date"),
            "manufacturer": result.get("manufacturer"),
            "confidence": result.get("confidence"),
            "parse_status": result.get("parse_status"),
            "note": "이것은 정답이 아니라 다른 판독기의 의견입니다. 서류와 다르면 서류를 따르십시오.",
        }

    def lookup_cross_recognition(self, keyword: str = "", country: str = "") -> dict[str, Any]:
        """BPJPH가 인정한 해외 인증기관(LHLN) 목록 조회."""
        try:
            from app.services.lhln_service import get_lhln_records
        except Exception as exc:
            return {"available": False, "reason": f"LHLN 조회를 쓸 수 없습니다: {type(exc).__name__}"}

        try:
            data = get_lhln_records(country=country, keyword=keyword, limit=20)
        except Exception as exc:
            return {"available": False, "reason": f"조회 실패: {type(exc).__name__}"}

        records = data.get("records") or data.get("rows") or []
        if not records:
            return {"available": True, "matches": [], "note": "일치하는 인정기관이 없습니다. LHLN 참조 데이터가 비어 있을 수도 있습니다."}

        return {
            "available": True,
            "matches": [
                {
                    "name": r.get("nama_lhln") or r.get("nama_lhln_raw"),
                    "abbreviation": r.get("abbreviation"),
                    "country": r.get("negara"),
                    "status": r.get("status"),
                }
                for r in records[:10]
            ],
        }

    # -- 디스패치 ------------------------------------------------------

    def dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "get_document_overview": lambda: self.get_document_overview(),
            "read_page_text": lambda: self.read_page_text(int(arguments.get("page", 1))),
            "view_page_image": lambda: self.view_page_image(int(arguments.get("page", 1))),
            "list_certification_organizations": lambda: self.list_certification_organizations(),
            "classify_document_template": lambda: self.classify_document_template(),
            "read_with_rule_engine": lambda: self.read_with_rule_engine(),
            "lookup_cross_recognition": lambda: self.lookup_cross_recognition(
                keyword=str(arguments.get("keyword", "")),
                country=str(arguments.get("country", "")),
            ),
        }

        handler = handlers.get(name)
        if handler is None:
            result: dict[str, Any] = {"error": f"알 수 없는 도구: {name}"}
        else:
            try:
                result = handler()
            except Exception as exc:
                result = {"error": f"{type(exc).__name__}: {exc}"}

        self.calls.append({"tool": name, "arguments": arguments})
        return result


# ==========================================
# 도구 스펙 (OpenAI function calling)
# ==========================================

def _tool(name: str, description: str, properties: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters = {
        "type": "object",
        "properties": properties or {},
        "required": list((properties or {}).keys()),
        "additionalProperties": False,
    }
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": parameters},
    }


TOOL_SPECS: list[dict[str, Any]] = [
    _tool(
        "get_document_overview",
        "문서의 페이지 수와 페이지별 텍스트 레이어 유무를 확인한다. 부속서가 있는 다페이지 "
        "인증서인지 먼저 이걸로 파악하라.",
    ),
    _tool(
        "read_page_text",
        "PDF에 박혀 있는 텍스트 레이어를 읽는다. 이미지를 눈으로 읽는 것보다 정확하므로 "
        "텍스트 레이어가 있으면 인증번호·날짜는 이걸로 확인하라.",
        {"page": {"type": "integer", "description": "1부터 시작하는 페이지 번호"}},
    ),
    _tool(
        "view_page_image",
        "지정한 페이지를 이미지로 본다. 텍스트 레이어가 없거나 도장·로고·표 배치를 봐야 할 때 쓴다.",
        {"page": {"type": "integer", "description": "1부터 시작하는 페이지 번호"}},
    ),
    _tool(
        "list_certification_organizations",
        "이 시스템이 아는 인증기관 정규명(code)과 별칭 목록. cert_org는 반드시 code로 답해야 "
        "하므로, 서류에 적힌 기관 표기를 code로 바꾸려면 이걸 조회하라.",
    ),
    _tool(
        "classify_document_template",
        "서류 생김새를 등록된 인증서 양식과 대조해 기관 후보를 낸다. 텍스트가 흐릴 때 유용하다.",
    ),
    _tool(
        "read_with_rule_engine",
        "기존 규칙 기반 판독기의 판독 결과를 본다. 참고 의견이며 정답이 아니다. "
        "결과가 서류와 다르면 서류를 따르라.",
    ),
    _tool(
        "lookup_cross_recognition",
        "BPJPH가 인정한 해외 인증기관(LHLN) 목록을 조회한다. 인도네시아 교차인정 여부를 확인할 때 쓴다.",
        {
            "keyword": {"type": "string", "description": "기관명 일부. 없으면 빈 문자열."},
            "country": {"type": "string", "description": "국가명. 없으면 빈 문자열."},
        },
    ),
]


SYSTEM_PROMPT = """당신은 할랄 인증서 판독 전문가입니다.

주어진 도구로 필요한 정보를 직접 확인한 뒤 인증서의 6개 항목을 추출하십시오.

작업 순서 권장:
1. get_document_overview로 페이지 수와 텍스트 레이어 유무를 먼저 확인한다.
2. 텍스트 레이어가 있으면 read_page_text로 읽는다. 이미지보다 정확하다.
3. 부속서가 있는 다페이지 문서라면 제품·제조사 정보가 뒤 페이지에 있을 수 있다.
4. 기관 표기가 서류 원문 그대로라면 list_certification_organizations로 정규명을 찾는다.
5. 판단이 서지 않으면 classify_document_template이나 read_with_rule_engine을 참고한다.

원칙:
- 서류에서 확인되지 않는 값은 지어내지 마십시오. 비워 두는 편이 낫습니다.
- 도구의 답은 참고 의견입니다. 서류와 다르면 서류에서 본 것을 따르십시오.
- 확인이 끝나면 도구를 그만 부르고 최종 답을 내십시오."""


# ==========================================
# 루프
# ==========================================

FINALIZE_INSTRUCTION = (
    "확인한 내용을 근거로 최종 답을 내십시오. 확인되지 않은 값은 지어내지 말고 비워 두십시오."
)

BUDGET_WARNING = (
    "도구 호출 한도에 도달했습니다. 지금까지 확인한 내용만으로 최종 답을 내십시오."
)


def _image_content(encoded_png: str) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_png}"}}


def _assistant_message_to_dict(message: Any) -> dict[str, Any]:
    """SDK 응답 객체와 평범한 dict를 모두 받아 messages에 넣을 형태로 만든다."""
    if isinstance(message, dict):
        return message

    tool_calls = []
    for call in getattr(message, "tool_calls", None) or []:
        tool_calls.append({
            "id": call.id,
            "type": "function",
            "function": {"name": call.function.name, "arguments": call.function.arguments},
        })

    payload: dict[str, Any] = {
        "role": "assistant",
        "content": getattr(message, "content", None),
    }
    if tool_calls:
        payload["tool_calls"] = tool_calls
    return payload


def _extract_tool_calls(message: Any) -> list[Any]:
    if isinstance(message, dict):
        return message.get("tool_calls") or []
    return getattr(message, "tool_calls", None) or []


def _tool_call_parts(call: Any) -> tuple[str, str, dict[str, Any]]:
    """SDK 객체 / dict 양쪽에서 (id, 이름, 인자)를 꺼낸다."""
    if isinstance(call, dict):
        call_id = call.get("id", "")
        function = call.get("function") or {}
        name = function.get("name", "")
        raw_arguments = function.get("arguments") or "{}"
    else:
        call_id = call.id
        name = call.function.name
        raw_arguments = call.function.arguments or "{}"

    try:
        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else dict(raw_arguments)
    except json.JSONDecodeError:
        arguments = {}

    return call_id, name, arguments


def build_initial_messages(toolbox: CertificateToolbox) -> list[dict[str, Any]]:
    """첫 페이지 이미지는 미리 붙여 준다. 매번 그걸 부르게 할 이유가 없다.

    도구 사용량(`toolbox.calls`)에는 잡히지 않는다. 그건 `dispatch`를 거친
    호출만 기록하고, 여기서는 구현을 직접 부르기 때문이다.
    """
    first_page = toolbox.view_page_image(1)

    content: list[dict[str, Any]] = [
        {"type": "text", "text": f"파일명: {toolbox.pdf_path.name}\n이 인증서에서 6개 항목을 추출하십시오."}
    ]

    if not first_page.get("error"):
        _page, encoded = toolbox.pending_images.pop()
        content.append({"type": "text", "text": "1페이지 이미지입니다."})
        content.append(_image_content(encoded))

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def run_agent(
    client: Any,
    model: str,
    pdf_path: Path,
    schema: type,
    zoom: float = 2.0,
    max_iterations: int = 6,
    max_tool_calls: int = 12,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """도구를 쓰며 탐색한 뒤 구조화 스키마로 확정한다.

    반환: (판독 결과 dict, 추적 정보 dict)
    """
    toolbox = CertificateToolbox(pdf_path, zoom)
    messages = build_initial_messages(toolbox)

    iterations = 0
    budget_exhausted = False

    for _ in range(max_iterations):
        iterations += 1

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_SPECS,
            temperature=0.0,
        )
        message = response.choices[0].message
        tool_calls = _extract_tool_calls(message)

        if not tool_calls:
            break

        messages.append(_assistant_message_to_dict(message))

        for call in tool_calls:
            call_id, name, arguments = _tool_call_parts(call)

            if len(toolbox.calls) >= max_tool_calls:
                budget_exhausted = True
                result: dict[str, Any] = {"error": BUDGET_WARNING}
            else:
                result = toolbox.dispatch(name, arguments)

            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False),
            })

        if toolbox.pending_images:
            content: list[dict[str, Any]] = []
            for page, encoded in toolbox.pending_images:
                content.append({"type": "text", "text": f"{page}페이지 이미지입니다."})
                content.append(_image_content(encoded))
            messages.append({"role": "user", "content": content})
            toolbox.pending_images.clear()

        if budget_exhausted:
            break

    final = client.chat.completions.parse(
        model=model,
        messages=messages + [{"role": "user", "content": FINALIZE_INSTRUCTION}],
        response_format=schema,
        temperature=0.0,
    )

    trace = {
        "iterations": iterations,
        "tool_calls": len(toolbox.calls),
        "tools_used": sorted({call["tool"] for call in toolbox.calls}),
        "call_sequence": [call["tool"] for call in toolbox.calls],
        "budget_exhausted": budget_exhausted,
    }

    return json.loads(final.choices[0].message.content), trace
