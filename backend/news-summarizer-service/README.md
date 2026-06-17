# news-summarizer-service

뉴스 요약, 저장, 조회 API를 담당하는 FastAPI 서비스입니다. fetcher가 전달한 RSS 기사 정보를 요약하고, 요약 결과를 DB에 저장합니다.

## 주요 기능

- 뉴스 요약 API 제공
- 요약 결과 저장
- 카테고리별 뉴스 목록 조회
- user-service와 mail-service에서 사용할 내부 뉴스 조회 API 제공
- S3 snapshot key 저장

## 의존성 설치

```bash
cd backend/news-summarizer-service
pip install -r requirements.txt
```

CI에서는 레포지토리 공통 의존성 파일인 `backend/requirements.txt`도 사용합니다.

## 로컬 실행

작업 디렉터리는 `backend/news-summarizer-service`입니다.

```bash
cd backend/news-summarizer-service
alembic upgrade head
uvicorn main:app --host 0.0.0.0 --port 8004
```

`DATABASE_URL`이 없으면 기본 SQLite 파일 `news.db`를 사용합니다. `NEWS_DB_PATH`로 로컬 DB 파일 경로를 바꿀 수 있습니다.

## 주요 환경 변수

- `DATABASE_URL`: 뉴스 DB 연결 문자열
- `NEWS_DB_PATH`: SQLite 기본 DB 파일 경로
- `GEMINI_API_KEY`: 외부 요약 API key
- `GEMINI_MODEL`: 사용할 Gemini 모델 이름
- `HOST`, `PORT`: 서비스 실행 host와 port

운영 환경의 API key와 DB 값은 Kubernetes Secret으로 주입받는 것을 기준으로 합니다.

## 테스트

```bash
cd backend/news-summarizer-service
pytest tests/ -v
```

테스트는 임시 SQLite DB에 Alembic migration을 적용한 뒤 실행됩니다.

## 문제 해결

- `no such table` 또는 DB schema 오류가 발생하면 `backend/news-summarizer-service`에서 `alembic upgrade head`를 먼저 실행했는지 확인합니다.
- 예전 Alembic 적용 전 `news.db`를 계속 사용 중이라면 schema가 맞지 않을 수 있습니다. 필요한 데이터를 백업한 뒤 새 migration 기준으로 DB를 다시 준비합니다.
- 요약 API 호출이 실패하면 `GEMINI_API_KEY`, `GEMINI_MODEL`, API quota 상태를 확인합니다.

## S3 snapshot key

fetcher가 S3에 RSS snapshot을 업로드하면 object key를 `summarized_news.s3_key`에 저장할 수 있습니다. 일반 뉴스 조회 API는 이 값을 외부 응답에 노출하지 않습니다.
