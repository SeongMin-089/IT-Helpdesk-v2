# IT-Helpdesk v2

**사내 IT 문의 접수·처리 관리 시스템**  
React 프론트엔드와 FastAPI를 통해 Odoo 19 Community 및 OCA Helpdesk의 기존 업무 기능을 활용하는 개인 미니 프로젝트입니다.

> 개발 기준: `feat/oca-helpdesk` 브랜치, 커밋 `3c974f4` (2026-10-29). 이 문서는 해당 시점의 소스 코드를 기준으로 작성했습니다. 실제 배포 환경과 테스트 결과는 별도 검증이 필요합니다.

## 1. 프로젝트 개요

사내 직원이 IT 장애나 기술 지원을 요청하면 IT 담당자가 이를 확인하고 배정·처리·종료할 수 있도록 만든 웹 서비스입니다.

- **사용 대상:** 일반 직원, IT 담당자
- **핵심 흐름:** 문의 등록 → 담당자 배정 → 처리 진행 → 해결 → 종료
- **개발 목표:** 로그인·권한, 문의 관리, 검색·필터, 담당자 배정, 상태 변경 이력, 댓글·첨부 기능을 하나의 업무 흐름으로 연결
- **설계 방향:** 새 ERP 모델을 직접 개발하기보다 Odoo/OCA의 검증된 모델을 재사용하고, 사용자 화면과 API 계층을 별도로 구성

본 프로젝트는 「2주 미니 프로젝트 — 사내 IT 헬프데스크 게시판 만들기」 과제의 필수 기능을 중심으로 개발했으며, FAQ 추천·유형별 자동배정·대시보드 등 일부 편의 기능을 확장했습니다.

## 2. 시스템 아키텍처

```text
[일반 직원 / IT 담당자]
         │ 브라우저
         ▼
[React + TypeScript + Vite]
  화면·입력·검색·상태 표시
         │ /api 요청 (개발 시 Vite 프록시)
         ▼
[FastAPI / Python]
  로그인 세션 검증 · 권한 · 업무 규칙 · 응답 변환
         │ Odoo API / 세션 통신
         ▼
[Odoo 19 Community + OCA 모듈]
  Helpdesk 티켓 · 문의 유형 · Chatter · FAQ 문서
         │ ORM
         ▼
[PostgreSQL]
  Odoo가 관리하는 업무 데이터
```

### 기술 스택

| 구분 | 기술 | 역할 |
| --- | --- | --- |
| 프론트엔드 | React, TypeScript, Vite, SCSS | 직원·담당자 웹 화면 구성 |
| 백엔드 | Python, FastAPI, Pydantic | 인증 연동, 접근 제어, 업무 API 제공 |
| ERP·업무 모델 | Odoo 19 Community, OCA Helpdesk | 문의·단계·사용자·메시지 등 기존 모델 사용 |
| FAQ 데이터 | Odoo `document.page`, `document.page.tag` | FAQ 본문·공개 분류·태그 관리 |
| 데이터베이스 | PostgreSQL | Odoo ORM이 데이터 저장·조회 |
| 개발 환경 | Windows / PowerShell, VS Code | 로컬 개발 및 테스트 |

**DB 설계 방침:** FastAPI에서 별도 티켓 테이블을 만들지 않습니다. Odoo에서 제공하는 `helpdesk.ticket`, `helpdesk.ticket.category`, `mail.message`, `ir.attachment` 등을 재사용합니다. 문의 유형의 기본 담당자 설정은 기존 `ir.config_parameter`에 저장합니다. 따라서 이 저장소에는 신규 업무 테이블을 생성하는 별도 SQL 스크립트나 커스텀 Odoo 애드온이 포함되어 있지 않습니다.

## 3. 주요 기능

### 일반 직원

- Odoo 계정을 이용한 로그인 및 본인 문의 조회
- 문의 등록: 제목, 내용, 문의 유형, 긴급도 선택
- 문의 목록 검색·정렬·필터·페이지 이동
- 문의 상세 화면에서 진행 단계와 처리 결과 확인
- 댓글 작성, 허용된 형식의 파일 첨부·다운로드
- 공개 FAQ 조회·검색 및 새 문의 제목에 따른 관련 FAQ 추천
- 문의 보관함 및 처리 이력 확인

### IT 담당자

- 전체 문의, 내 담당 문의, 미배정·보관 문의 조회
- 유형별 기본 담당자 설정과 문의 등록 시 자동배정
- 담당자·긴급도 변경 및 단계별 처리 진행
- 해결 내용 입력, 종료, 재처리 요청에 대한 업무 흐름 처리
- 댓글·내부 메모, 첨부파일, 상태·담당자 변경 이력 확인
- 문의 유형 생성·수정·보관·복원 및 상위 유형 관리
- FAQ 초안 생성·수정, 태그 선택, 공개·비공개 전환, 보관·복원
- 해결된 문의를 바탕으로 FAQ 초안 생성
- 대시보드의 상태별·긴급도별 통계와 최근 문의 확인

### 업무 단계 및 데이터 처리

- **5단계 흐름:** 접수 → 배정 → 처리 중 → 해결 → 종료. 실제 단계는 Odoo에 설정된 5개 단계의 순서와 종료 속성을 기준으로 검증합니다.
- **이력 관리:** 새로운 이력 테이블 대신 Odoo의 `mail.message`, `mail.tracking.value`를 조회해 상태·담당자 변경을 표시합니다.
- **첨부파일:** 현재 코드 기준 파일당 최대 **10MB**, 확장자·MIME 유형 제한을 적용합니다.
- **보관:** Odoo 레코드의 `active` 상태를 활용해 보관·복원하며, 관련 데이터를 유지합니다.

> 일부 보안 보완 사항(업로드 파일 실제 내용 검사, 문의당 첨부 개수 제한, 담당자 역할 검증 강화, Odoo 직접 접근 경로 점검)은 후속 검토 항목입니다. 구현·검증이 끝나기 전에는 완료된 기능으로 간주하지 않습니다.

## 4. 폴더 구조

```text
IT-Helpdesk-v2/
├── backend/
│   ├── main.py                 # FastAPI 앱, 라우터 및 미들웨어
│   ├── .env.example            # 백엔드 환경변수 예시
│   ├── app/
│   │   ├── config.py           # 환경설정
│   │   ├── constants.py        # Odoo 필드·긴급도·첨부 정책
│   │   ├── schemas.py          # API 요청 데이터 검증
│   │   ├── transformers.py     # Odoo 응답 변환
│   │   ├── routers/            # 인증·문의·유형·FAQ 등 API
│   │   └── services/           # Odoo 통신·담당자 배정
│   ├── tests/test_main.py      # Mock 기반 단위 테스트
│   └── run_integration_tests.ps1
├── frontend/
│   ├── src/
│   │   ├── pages/              # 로그인·대시보드·문의·FAQ 등
│   │   ├── components/         # 공통 UI 및 문의 활동 영역
│   │   ├── contexts/           # 인증 상태
│   │   ├── services/           # API 요청·표시 형식
│   │   ├── types/              # API 타입
│   │   └── styles/             # SCSS
│   ├── vite.config.ts          # 로컬 개발 서버 및 API 프록시
│   └── package.json
└── README.md
```

## 5. 실행 환경 준비

### 사전 준비

1. Python 3.12 계열 개발 환경 및 Node.js/npm
2. PostgreSQL과 연결된 **Odoo 19 Community** 서버
3. OCA Helpdesk의 `helpdesk_mgmt` 등, 코드에서 사용하는 `helpdesk.ticket` 관련 모델을 제공하는 모듈
4. `document.page`, `document.page.tag` 모델을 제공하는 Odoo/OCA 문서·지식 모듈
5. Odoo DB, API 키, 로그인 가능한 직원·담당자 계정 및 필요한 Helpdesk 권한 그룹
6. FAQ를 사용할 경우 `document.page`에 **공개용 분류**와 **초안용 분류**를 별도로 준비

Odoo/OCA 모듈 자체와 PostgreSQL 구성 파일은 이 저장소에 포함되지 않습니다. 따라서 **새 PC에서 실행하려면 Odoo 환경과 해당 모델·권한·기본 단계·FAQ 분류를 먼저 구성**해야 합니다.

### 5-1. 백엔드 환경변수

프로젝트 루트에서 PowerShell을 열고 다음과 같이 환경설정 파일을 복사합니다.

```powershell
Copy-Item .\backend\.env.example .\backend\.env
```

`backend/.env`에서 실제 개발 환경에 맞게 설정합니다.

```dotenv
ODOO_URL=http://127.0.0.1:8069
ODOO_DB=It_Helpdesk_v2
ODOO_API_KEY=실제_Odoo_API_키

# Odoo document.page의 실제 category 레코드 ID
ODOO_FAQ_PUBLIC_CATEGORY_ID=공개_분류_ID
ODOO_FAQ_DRAFT_CATEGORY_ID=초안_분류_ID

# 로컬 개발 환경에서 FAQ 쓰기 기능이 필요할 때만 활성화
ODOO_FAQ_WRITE_ENABLED=true

# 로컬 HTTP 개발 환경 예시. 운영 환경에서는 HTTPS와 보안 쿠키 사용
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_SAMESITE=strict
AUTH_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:8000
```

- `ODOO_URL`은 **FastAPI가 접근할 Odoo 서버 주소**입니다. 동일 PC에서 실행할 때 `127.0.0.1`을 사용할 수 있습니다.
- `ODOO_API_KEY`는 프론트엔드가 아니라 **백엔드 환경변수에만** 저장합니다.
- FAQ의 두 분류 ID는 실제 Odoo에서 확인한 서로 다른 `document.page` 분류 ID여야 합니다.
- `ODOO_FAQ_WRITE_ENABLED`는 개발용 쓰기 허용 설정이며, **사용자 인증이나 권한 확인을 대신하지 않습니다.**
- `.env` 파일에는 비밀정보가 있으므로 Git에 커밋하지 않습니다.

### 5-2. Odoo 실행

설치된 Odoo 19 서버를 실행하고, 설정한 DB(`It_Helpdesk_v2`)가 접근 가능한지 확인합니다. 기본 로컬 접속 주소는 다음과 같습니다.

```text
http://127.0.0.1:8069
```

Odoo 실행 명령과 애드온 경로는 로컬 설치 방식에 따라 달라지므로, 이 저장소에 없는 Odoo 구성 파일이나 설치 스크립트를 전제로 하지 않습니다.

### 5-3. FastAPI 실행

```powershell
cd .\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install fastapi "uvicorn[standard]" requests python-dotenv httpx
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

이미 가상환경과 패키지가 설치돼 있다면 생성·설치 단계는 생략할 수 있습니다. 현재 저장소에는 버전을 고정한 백엔드 `requirements.txt`가 없으므로, 위 명령은 **현재 코드에서 사용하는 주요 라이브러리 설치 예시**이며 재현 가능한 고정 버전 설치를 보장하지는 않습니다.

- API 주소: <http://127.0.0.1:8000>
- FastAPI API 문서: <http://127.0.0.1:8000/docs>

### 5-4. React 실행

별도 PowerShell 창을 열어 실행합니다.

```powershell
cd .\frontend
npm ci
npm run dev
```

- 기본 웹 주소: <http://localhost:5173>
- `frontend/vite.config.ts`에서 `/api` 요청을 기본적으로 `http://localhost:8000`에 프록시합니다.
- **Odoo(8069) → FastAPI(8000) → React(5173)** 순서로 서버가 준비돼 있는지 확인합니다.

> **다른 PC에서 시연할 때:** 현재 Vite 설정은 기본적으로 `localhost`에 바인딩됩니다. LAN에서 접속하려면 개발 서버 바인딩(예: `npm run dev -- --host 0.0.0.0`), 윈도우 방화벽, 동일 네트워크, `AUTH_ALLOWED_ORIGINS`에 접속 주소 추가 및 HTTP/HTTPS 쿠키 설정을 별도로 확인해야 합니다. 다른 PC의 브라우저에서 `127.0.0.1`은 **그 PC 자신**을 가리킵니다. 반면 백엔드의 `ODOO_URL=127.0.0.1:8069`는 백엔드와 Odoo가 같은 PC에서 실행된다면 그대로 유지할 수 있습니다.

## 6. 주요 API

| 기능 | 주요 경로 | 설명 |
| --- | --- | --- |
| 인증 | `/api/auth/login`, `/api/auth/me`, `/api/auth/logout` | Odoo 세션 기반 로그인·조회·로그아웃 |
| 문의 | `/api/oca/tickets` | 등록·목록·관리 |
| 문의 진행 | `/api/oca/tickets/{id}/stage`, `/resolve`, `/close`, `/reprocess` | 단계 전환 및 처리 |
| 댓글·이력·첨부 | `/api/oca/tickets/{id}/comments`, `/history`, `/attachments` | Chatter 및 첨부 연동 |
| 문의 유형 | `/api/oca/categories` | 활성 유형 조회 및 담당자용 관리 |
| 담당자 | `/api/oca/assignees` | 배정 가능한 사용자 조회 |
| FAQ | `/api/oca/faqs`, `/api/oca/faqs/suggestions` | 공개 FAQ 및 추천 |
| 대시보드 | `/api/oca/dashboard` | 통계·최근 문의 |

세부 HTTP 메서드, 요청 필드 및 응답 형태는 FastAPI `/docs`와 해당 라우터 구현을 기준으로 확인합니다.

## 7. 테스트와 확인 방법

### 백엔드 단위 테스트

```powershell
cd .\backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`backend/tests/test_main.py`는 **Mock 기반 테스트**를 포함합니다. Odoo API 동작을 모의하므로 실제 Odoo DB에 연결한 통합 테스트와는 구분해야 합니다.

`run_integration_tests.ps1` 역시 이름과 달리, `.env.test`의 DB·포트 안전 조건을 확인한 뒤 **Mock 기반 unittest**를 실행합니다. 실제 DB 통합 테스트를 자동으로 수행하는 것으로 해석하지 마세요.

### 프론트엔드 검사

```powershell
cd .\frontend
npm run build
npm run lint
```

### 실제 Odoo 연동 수동 점검

- [ ] 직원 계정과 IT 담당자 계정 로그인 및 메뉴 분리
- [ ] 직원이 문의 등록 → 내 문의 목록·상세에서 확인
- [ ] 유형별 자동배정 또는 담당자 수동 지정
- [ ] 문의 단계 변경, 해결·종료·재처리 흐름
- [ ] 댓글·내부 메모의 역할별 접근 및 종료 문의 입력 제한
- [ ] 첨부파일 업로드·다운로드, 보관 후 기존 파일 조회
- [ ] 다른 직원 문의의 상세·댓글·첨부 접근 차단
- [ ] FAQ 초안·태그·공개·보관·검색·신규 문의 추천
- [ ] 검색·상세 필터·페이지 이동·대시보드 숫자 확인
- [ ] API 오류·잘못된 입력·비활성 데이터의 예외 처리

**문서 작성 시점에는 위 수동 점검 결과를 모두 통과했다고 단정하지 않습니다.** 제출 시 실제 실행 결과와 주요 화면 캡처를 별도로 첨부하는 것이 좋습니다.

## 8. 설계 선택과 v1 대비 변화

| 항목 | v1 | v2 |
| --- | --- | --- |
| 사용자 화면 | Odoo 내부 XML/Owl 기반 | React 웹 프론트엔드 |
| 서버 처리 | 커스텀 Odoo 애드온 중심 | FastAPI 중간 API 계층 |
| 문의 데이터 | 자체 `it.helpdesk.ticket` 모델 | OCA `helpdesk.ticket` 재사용 |
| FAQ | 자체 FAQ 모델 | `document.page` 기반 FAQ |
| 상태·담당자 이력 | 커스텀 이력 로직 | Odoo Chatter 추적 데이터 활용 |
| 주요 의도 | 개별 기능 직접 구현 | 기존 ERP 기능 활용과 계층 분리 |

**v2 전환 이유:** 기능을 모두 새로 작성하기보다 Odoo/OCA가 이미 제공하는 CRUD, 메시지, 이력, 권한 체계 등을 재사용해 업무 로직의 중복 구현을 줄이기 위함입니다. 대신 React·FastAPI·Odoo의 설정 및 통합 검증이 필요하다는 구조적 복잡성은 존재합니다.

## 9. 알려진 제한 및 후속 과제

현재 커밋 기준으로 다음 항목은 검증 또는 개선이 남아 있습니다.

1. **보안 강화:** 담당자 지정 시 Helpdesk 권한 재검증, 파일 실제 내용 검사, 문의별 첨부 개수 제한, FastAPI 우회 Odoo 접근 권한 점검
2. **문의 유형:** `기타(ETC)`의 상위 유형 후보 제외 및 `Administrator` 유형 데이터 원인 확인
3. **이메일 알림:** Odoo/OCA의 단계별 메일 템플릿과 발신 서버 설정을 검토 중이며, 현재 v2의 검증된 기능으로 표기하지 않음
4. **선택 기능:** 만족도 평가, 별도 처리 기한, 상세 담당자별 실적 통계, 문의 간 직접 연결은 구현 범위 밖
5. **배포·재현:** 백엔드 의존성 버전 고정, Odoo/DB 환경 초기화 절차, 외부 접속·HTTPS 운영 구성 문서화 필요
6. **테스트:** Mock 단위 테스트와 별도로 실제 Odoo DB를 이용한 통합·권한 검증 필요

## 10. 발표 시연 권장 흐름 (약 5분)

1. **프로젝트 소개:** 사내 IT 요청을 한곳에서 접수·추적하는 목적 설명
2. **구조 설명:** React → FastAPI → Odoo/OCA → PostgreSQL
3. **직원 시연:** 로그인 → FAQ 추천 확인 → 문의 등록
4. **담당자 시연:** 문의 확인 → 담당자 배정 → 진행·해결 → 이력·FAQ 확인
5. **마무리:** Odoo/OCA 재사용의 장점과 남은 보안·운영 개선 계획 설명

---

**GitHub 저장소:** https://github.com/SeongMin-089/IT-Helpdesk-v2  
**작업 브랜치:** `feat/oca-helpdesk`
