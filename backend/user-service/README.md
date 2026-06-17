# user-service

사용자 구독, 이메일 인증, 구독 해지, 뉴스 목록 조회 proxy를 담당하는 FastAPI 서비스입니다.

## 주요 기능

- 구독 신청과 카테고리 저장
- 인증 메일 발송 요청
- 이메일 인증 처리
- 구독 해지 페이지와 해지 처리
- summarizer 서비스의 뉴스 목록을 frontend용 API로 중계
- mail-service에서 사용할 내부 구독자 조회 API 제공

## 의존성 설치

```bash
cd backend/user-service
pip install -r requirements.txt
```

CI에서는 레포지토리 공통 의존성 파일인 `backend/requirements.txt`도 사용합니다.

## 로컬 실행

작업 디렉터리는 `backend/user-service`입니다.

```bash
cd backend/user-service
alembic upgrade head
uvicorn main:app --host 0.0.0.0 --port 8000
```

`DATABASE_URL`이 없으면 기본 SQLite 파일 `user_db.sqlite`를 사용합니다.

## 주요 환경 변수

- `DATABASE_URL`: 사용자 DB 연결 문자열
- `MAIL_SERVICE_URL`: mail-service 주소
- `NEWS_API_BASE_URL`: news-summarizer-service 주소
- `INTERNAL_API_TOKEN`: 내부 API 호출 검증 token
- `ALLOWED_ORIGINS`: CORS 허용 origin 목록
- `HOST`, `PORT`: 서비스 실행 host와 port

운영 환경의 Secret 값은 Kubernetes Secret으로 주입받는 것을 기준으로 합니다.

## 테스트

```bash
cd backend/user-service
pytest tests/ -v
```

테스트는 임시 SQLite DB에 Alembic migration을 적용한 뒤 실행됩니다.

## 문제 해결

- `no such table` 또는 DB schema 오류가 발생하면 `backend/user-service`에서 `alembic upgrade head`를 먼저 실행했는지 확인합니다.
- 내부 구독자 조회 API가 401을 반환하면 `INTERNAL_API_TOKEN` 주입 상태와 호출 header를 확인합니다.
