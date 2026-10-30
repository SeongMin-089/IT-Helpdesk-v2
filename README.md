# IT-Helpdesk v2

사내 직원의 IT 문의를 접수하고 처리하기 위한 웹 애플리케이션입니다.

2주 개인 프로젝트로, Odoo의 기존 업무 기능을 활용해 개발했습니다.

처음에는 Odoo 내부 커스텀 모듈 방식으로 개발했지만, 이후 React와 FastAPI를 분리하고 Odoo/OCA의 기존 모델을 재사용하는 구조로 변경했습니다.

## 기술 스택

| 구분 | 기술 |
|---|---|
| Frontend | React, TypeScript, Vite, SCSS |
| Backend | Python, FastAPI |
| ERP | Odoo 19 Community, OCA Helpdesk |
| Database | PostgreSQL |

### 시스템 구조

```text
React + TypeScript
        ↓
     FastAPI
        ↓
 Odoo 19 + OCA
        ↓
   PostgreSQL
```

React에서 사용자 화면을 처리하고, FastAPI가 인증과 권한 및 업무 API를 담당합니다.

FastAPI는 데이터베이스에 직접 접근하지 않고 Odoo API를 통해 데이터를 처리합니다.

## 주요 기능

### 일반 직원
- Odoo 계정 로그인
- 문의 등록·조회·수정
- 내 문의 검색 및 상태 확인
- 댓글 작성 및 파일 첨부
- 공개 FAQ 검색 및 관련 FAQ 추천
- 문의 보관함 조회

### IT 담당자
- 전체 문의 및 내 담당 문의 조회
- 문의 유형별 담당자 자동배정
- 문의 상태 변경 및 해결·종료 처리
- 댓글·내부 메모·첨부파일 관리
- 상태 및 담당자 변경 이력 조회
- FAQ 초안·태그·공개 상태 관리
- 문의 유형 관리 및 대시보드 조회

### 문의 처리 흐름

접수 → 담당자 확인 → 처리 중 → 해결 → 종료

문의 유형에 따라 담당자를 자동배정하며, 담당자가 직접 확인하면 다음 처리 단계로 전환됩니다.

## v1과 v2 비교

| 구분 | v1 | v2 |
|---|---|---|
| 화면 | Odoo XML / Owl | React |
| 서버 처리 | Odoo 커스텀 모듈 | FastAPI |
| 문의 모델 | 자체 모델 | OCA Helpdesk 모델 |
| 처리 이력 | 커스텀 로직 | Odoo Chatter |
| FAQ | 자체 FAQ 모델 | document.page |

v1도 Odoo 기본 기능을 활용했지만, 별도로 구현한 모델과 로직이 많았습니다.

v2에서는 기존 업무 모델을 최대한 재사용하고, Odoo 원본 소스를 수정하지 않는 방향으로 개발했습니다.

## 실행 방법

주요 기능은 `feat/oca-helpdesk` 브랜치를 기준으로 개발했습니다.

실행 전 Odoo 19 Community, PostgreSQL, OCA Helpdesk 및 FAQ 관련 문서 모듈이 준비되어 있어야 합니다.

### Backend

`backend/.env.example`을 복사해 `.env` 파일을 만들고 Odoo 접속 정보와 API 키, FAQ 분류 ID를 설정합니다.

```powershell
cd backend
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install fastapi "uvicorn[standard]" requests python-dotenv httpx
.\venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

API 문서: http://localhost:8000/docs

### Frontend

```powershell
cd frontend
npm ci
npm run dev
```

웹 주소: http://localhost:5173

백엔드 명령은 개발 환경 기준 설치 예시입니다. 실제 실행에는 Odoo 서버와 DB, 모듈, 사용자 권한 등의 사전 설정이 필요합니다.

## 테스트

백엔드는 Mock 기반 단위 테스트를 작성했습니다.

```powershell
cd backend
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

프론트엔드 빌드 및 코드 검사:

```powershell
cd frontend
npm run build
npm run lint
```

실제 Odoo DB를 이용한 추가 통합 테스트와 운영 환경의 보안 검증은 후속 작업으로 남아 있습니다.

## 향후 개선 사항

- 문의 접수 및 상태 변경 시 이메일 알림
- 처리 기한 설정 및 지연 문의 관리
- 담당자별 처리 성과 통계
- 실제 운영 환경 배포
- 보안 및 통합 테스트 보완

---

2026.10 | 현장실습 개인 프로젝트
