# mail-service

인증 메일과 뉴스레터 메일 발송을 담당하는 FastAPI 서비스입니다. SMTP 설정을 사용해 HTML 메일을 발송하고, 발송 결과를 DB에 기록합니다.

## 주요 기능

- 구독 인증 메일 발송
- 카테고리별 뉴스 요약 메일 발송
- user-service의 내부 구독자 API 조회
- 메일 발송 로그 저장
- scheduler 기반 뉴스레터 발송 흐름

## 의존성 설치

```bash
cd backend/mail-service
pip install -r requirements.txt
```

CI에서는 레포지토리 공통 의존성 파일인 `backend/requirements.txt`도 사용합니다.

## 로컬 실행

작업 디렉터리는 `backend/mail-service`입니다.

```bash
cd backend/mail-service
alembic upgrade head
uvicorn main:app --host 0.0.0.0 --port 8002
```

`DATABASE_URL`이 없으면 기본 SQLite 파일 `mail_db.sqlite`를 사용합니다.

## 주요 환경 변수

- `DATABASE_URL`: 메일 로그 DB 연결 문자열
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`: SMTP 접속 정보
- `SMTP_TLS`, `SMTP_SSL`: SMTP 보안 연결 옵션
- `MAIL_FROM`: 발신자 주소
- `VERIFY_BASE_URL`: 인증 링크 base URL
- `UNSUBSCRIBE_BASE_URL`: 구독 해지 링크 base URL
- `INTERNAL_API_TOKEN`: user-service 내부 API 호출 token
- `HOST`, `PORT`: 서비스 실행 host와 port

운영 환경의 SMTP와 token 값은 Kubernetes Secret으로 주입받는 것을 기준으로 합니다.

## 테스트

```bash
cd backend/mail-service
pytest tests/ -v
```

테스트는 임시 SQLite DB에 Alembic migration을 적용한 뒤 실행됩니다.

## 문제 해결

- `no such table` 또는 DB schema 오류가 발생하면 `backend/mail-service`에서 `alembic upgrade head`를 먼저 실행했는지 확인합니다.
- 메일이 발송되지 않으면 SMTP Secret, `MAIL_FROM`, mail-service log, `mail_send_logs` 저장 여부를 함께 확인합니다.
