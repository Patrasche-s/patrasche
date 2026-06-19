# Patrasche Backend

FastAPI 기반 백엔드 모듈입니다. 사용자 요청 처리, 메일 발송, RSS 수집, 뉴스 요약/저장을 기능별 서비스가 나누어 담당합니다.

## 서비스 구성

| Service | Port | 역할 |
| --- | --- | --- |
| `user-service` | 8000 | 구독, 이메일 인증, 구독 해지, 뉴스 목록 proxy |
| `mail-service` | 8002 | 인증 메일, 뉴스레터 메일 발송, 발송 로그 저장 |
| `news-fetcher-service` | 8003 | RSS 수집, summarizer 호출, S3 snapshot 업로드 |
| `news-summarizer-service` | 8004 | 뉴스 요약, 저장, 조회 API |

`user-service`, `mail-service`, `news-summarizer-service`는 Alembic migration을 사용합니다. `news-fetcher-service`는 직접 DB를 관리하지 않고 summarizer API를 통해 저장 흐름에 참여합니다.

## 테스트

Jenkins 앱 파이프라인은 서비스별 의존성을 설치한 뒤 다음 테스트를 실행합니다.

```bash
cd backend/mail-service && pytest tests/ -v
cd backend/news-fetcher-service && pytest tests/ -v
cd backend/news-summarizer-service && pytest tests/ -v
cd backend/user-service && pytest tests/ -v
```

네 개 서비스에 대해 flake8도 실행하며, 현재 기준 line length는 130으로 맞춰져 있습니다.

## Docker 이미지

Docker build context는 `backend/` 디렉터리입니다.

- `Dockerfile.user` -> `patrasche-backend`
- `Dockerfile.fetcher` -> `patrasche-crawler`
- `Dockerfile.summarizer` -> `patrasche-analyzer`
- `Dockerfile.mail` -> `patrasche-notifier`

이미지는 Jenkins의 `IMAGE_TAG` 값으로 전달되는 40자리 앱 레포 Git SHA를 사용합니다.

## 환경 변수와 Secret

운영 환경의 DB, SMTP, 내부 token, 외부 API key 값은 코드에 저장하지 않습니다. 인프라 레포의 SSM Parameter Store와 External Secrets Operator 설정을 통해 Kubernetes Secret으로 주입받습니다.

로컬 실행 시에는 각 서비스 README에 적힌 기본 SQLite DB 또는 필요한 환경 변수를 사용합니다.
