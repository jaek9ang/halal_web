# 이 프로젝트에서 Claude Code로 개발하기

Windows PowerShell 환경 기준. 이 저장소는 Claude Code가 코드를 찾고 검증할 수 있도록
정리돼 있다 — 이 문서는 그걸 어떻게 쓰는지 설명한다.

## 1. 설치

```powershell
npm install -g @anthropic-ai/claude-code
```

프로젝트 루트에서 실행한다. **반드시 루트에서 열어야 한다** — Claude가 `CLAUDE.md`를
읽고 backend/frontend를 함께 보려면 루트가 작업 디렉토리여야 한다.

```powershell
cd C:\...\halal_web
claude
```

## 2. 처음 한 번: 환경 준비

Claude에게 시키지 말고 직접 한다. 오래 걸리고 중간에 확인할 게 많다.

```powershell
.\scripts\setup_venv.ps1
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
cd frontend; npm install; cd ..
```

확인:

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest
cd ..
```

`217 passed` 같은 결과가 나오면 준비 완료다. 여기서 실패하면 Claude에게 코드를
고치라고 하기 전에 환경 문제부터 해결한다.

## 3. CLAUDE.md가 하는 일

루트의 `CLAUDE.md`는 Claude Code가 **매 세션 자동으로 읽는** 파일이다. 여기에는:

- 프로젝트가 뭘 하는지, 도메인 용어 (PMF, LHLN, BPJPH, 교차인정, 자동확정)
- **"무엇을 고치려면 어디를 보라"** 표 — Claude가 파일을 헤매지 않게 한다
- 검증 명령 — Claude가 스스로 확인하게 한다
- 이 저장소의 금지 사항

작업하다가 "Claude가 자꾸 엉뚱한 파일을 본다" 싶으면, 그건 `CLAUDE.md`의 지도가
낡았다는 뜻이다. 코드를 옮겼으면 그 표도 같이 고친다.

## 4. 요청하는 방법

### 좋은 요청

Claude는 이 저장소에서 **검증할 수단**을 갖고 있다. 그걸 쓰라고 말해주면 결과가 다르다.

```
JAKIM 인증서에서 발급일을 유효기간으로 잘못 읽는 경우가 있어.
tests/fixtures/certificate_samples.py 에 실패 케이스를 하나 추가하고,
그게 실패하는 걸 먼저 확인한 다음 rules/dates.py 를 고쳐줘.
```

```
수신메일 화면에서 첨부 목록이 안 뜨는데 원인 찾아줘.
백엔드 띄우고 실제로 /mail/inbox/attachments 호출해서 확인해줘.
```

### 피할 요청

```
코드 좀 정리해줘          ← 범위가 없다. Claude가 멋대로 넓힌다.
이거 왜 안 돼?            ← 무엇이 어떻게 안 되는지 말해야 한다.
전체적으로 개선해줘        ← 검증할 수 없는 변경이 쌓인다.
```

### 한 번에 하나씩

큰 작업은 나눠서 시키고, 각 단계마다 `pytest`가 통과하는 걸 확인한 뒤 커밋한다.
한 번에 열 파일을 고치게 두면 뭐가 깨졌는지 찾을 수 없다.

## 5. 판독 규칙을 고칠 때 (가장 자주 하는 작업)

기관별 OCR 규칙은 `backend/app/services/rules/`에 있다.

| 증상 | 파일 |
|---|---|
| 유효기간을 못 읽거나 잘못 읽음 | `rules/dates.py` |
| 기관을 UNKNOWN으로 판정 | `rules/organizations.py` |
| 인증번호를 못 읽음 | `rules/core.py` |
| 제조사명에 주소가 섞임 | `rules/companies.py` |
| 자동확정되면 안 되는 게 확정됨 | `rules/context.py` |

**규칙을 고치면 `tests/test_certificate_rules.py`가 깨질 수 있다.** 이건 정상이다 —
그 테스트는 판독 결과를 골든 파일로 고정해놓고 "동작이 바뀌었는지"를 알려준다.

바뀐 게 의도한 것이라면:

```powershell
cd backend
$env:UPDATE_CERTIFICATE_RULE_GOLDEN=1
..\.venv\Scripts\python.exe -m pytest tests\test_certificate_rules.py
Remove-Item Env:UPDATE_CERTIFICATE_RULE_GOLDEN
git diff tests\fixtures\certificate_rules_golden.json
```

**마지막 `git diff`를 반드시 눈으로 본다.** 고치려던 한 기관만 바뀌었는지, 다른 기관까지
같이 바뀌었는지가 거기 나온다. 다른 기관이 같이 바뀌었으면 그 수정은 되돌린다.

## 6. 화면을 고칠 때

`frontend/src/pages/` 아래 화면별 파일이 있다. 파일명이 메뉴 이름과 대응한다.

| 메뉴 | 파일 |
|---|---|
| PMF / 원료 | `PmfPage.jsx` |
| 메일주소 정리 | `MailAddressPage.jsx` |
| 발송관리 / 발송로그 | `SendPage.jsx`, `MailLogsPage.jsx` |
| 수신메일 | `ReceiveMailPage.jsx` |
| 인증서 판독 | `OcrPage.jsx` |
| 인증서 자동분류 | `FilingPage.jsx` |
| OCR 테스트 | `OcrTestPage.jsx` |
| 인증서양식학습 | `CertTemplateTrainingPage.jsx` |
| AI 규칙 리뷰 | `AiRuleReviewPage.jsx` |

**CSS는 조심한다.** `src/styles/`의 파일들은 시간순으로 쌓인 오버라이드 레이어라
**순서가 곧 우선순위**다. `App.css`의 import 순서를 바꾸면 화면이 깨진다.
새 규칙은 해당 화면 파일에 넣고, 기존 규칙을 이겨야 하면 뒤쪽 레이어에 넣는다.

검증:

```powershell
cd frontend
npm run build
npm run lint
```

## 7. 하지 말아야 할 것

이 저장소는 한때 "패치 스크립트로 소스를 고치고 백업본을 옆에 남기는" 방식으로
개발돼서 백업 파일 600여 개가 쌓였고, 같은 함수가 한 파일에 세 번 붙어 있었다.
그중 하나는 실제로 API 하나를 500 에러로 죽이고 있었다.

Claude에게도 사람에게도 똑같이 적용되는 규칙:

- **소스 옆에 백업 파일을 만들지 않는다.** `*.bak`, `*_backup_*`, `*_old*` 금지.
  되돌리기는 git으로 한다. 불안하면 브랜치를 파거나 `git tag`를 찍는다.
- **패치 스크립트로 소스를 고치지 않는다.** 파일을 직접 편집한다.
- **생성물을 커밋하지 않는다.** 트리 덤프, 검증 리포트, pip freeze 결과.

`.gitignore`가 대부분 막아두었고, `tests/test_no_duplicate_definitions.py`가 같은
이름이 두 번 정의되는 걸 잡는다. 그래도 습관이 먼저다.

## 8. 커밋

Claude에게 커밋을 맡길 때는 **무엇을 왜 바꿨는지** 쓰게 한다.

```
지금까지 변경사항 커밋해줘. 커밋 메시지에 왜 고쳤는지 쓰고,
어떤 검증을 통과했는지도 적어줘.
```

작업 전에 되돌릴 지점을 만들어두면 편하다.

```powershell
git tag before-jakim-fix
```

## 9. 막혔을 때

- **Claude가 같은 실패를 반복한다** → 새 세션을 연다. 컨텍스트가 오염된 것이다.
- **엉뚱한 파일을 고친다** → `CLAUDE.md`의 지도가 낡았는지 확인하고, 요청에 파일 경로를 직접 적어준다.
- **"테스트 통과했다"는데 실제로는 안 된다** → 검증 명령의 출력을 보여달라고 한다.
  이 저장소는 실제로 실행 가능하므로 근거를 요구할 수 있다.
- **공유폴더가 안 붙어서 PMF 기능이 안 된다** → [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md)의 로컬 테스트 폴더 설정.

## 관련 문서

- [../CLAUDE.md](../CLAUDE.md) — Claude가 자동으로 읽는 규칙
- [../README.md](../README.md) — 프로젝트 개요, 실행법
- [architecture.md](architecture.md) — 데이터 흐름, 모듈 지도
- [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md) — 로컬 환경 설정
