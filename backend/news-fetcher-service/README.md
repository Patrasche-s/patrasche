# news-fetcher-service

RSS 피드를 수집하고, 수집한 기사를 summarizer 서비스로 전달하는 FastAPI 서비스입니다. S3 설정이 있는 경우 RSS 원문 snapshot을 S3에 저장합니다.

## 주요 기능

- 카테고리별 RSS 뉴스 수집
- summarizer `/summarize` API 호출
- summarizer 저장 API를 통한 뉴스 저장 흐름 연동
- S3 RSS snapshot 업로드
- scheduler 기반 주기 실행

## 의존성 설치

```bash
cd backend/news-fetcher-service
pip install -r requirements.txt
```

CI에서는 레포지토리 공통 의존성 파일인 `backend/requirements.txt`도 사용합니다.

## 로컬 실행

```bash
cd backend/news-fetcher-service
uvicorn main:app --host 0.0.0.0 --port 8003
```

테스트나 로컬 실행에서 외부 호출을 막고 싶으면 `ENABLE_SCHEDULER=false`로 실행합니다.

## 주요 환경 변수

- `SUMMARIZER_URL`: summarizer의 `/summarize` API 주소
- `NEWS_STORE_BASE_URL`: summarizer 저장/조회 API base URL
- `ENABLE_SCHEDULER`: scheduler 실행 여부
- `AWS_REGION`: S3 사용 시 AWS region
- `S3_BUCKET` 또는 `S3_BUCKET_NAME`: RSS snapshot 저장 bucket
- `S3_PREFIX`: S3 object key prefix
- `HOST`, `PORT`: 서비스 실행 host와 port

`S3_BUCKET`과 `S3_BUCKET_NAME`이 모두 없으면 S3 업로드는 건너뜁니다.

S3 object key 형식:

```text
{S3_PREFIX}/rss_snapshots/{batch_date_kst}/{category_slug}/{sha256(link)[:16]}.json
```

## 테스트

```bash
cd backend/news-fetcher-service
pytest tests/ -v
```

S3 관련 테스트는 boto3 client를 mock 처리하므로 실제 AWS credential 없이 실행할 수 있습니다.

## 운영 메모

fetcher 런타임 IAM 권한은 RSS snapshot bucket에 대한 `PutObject` 중심으로 관리합니다. snapshot 보관 기간은 인프라 레포의 S3 lifecycle 설정과 함께 확인합니다.
