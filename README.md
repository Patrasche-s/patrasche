# Patrasche App

Patrasche 앱 레포지토리입니다. RSS 기반 뉴스 수집, 요약, 사용자 구독, 메일 발송 기능을 담당하며, React/Vite 프론트엔드와 FastAPI 백엔드 서비스들로 구성되어 있습니다.

인프라 리소스와 Kubernetes 매니페스트는 별도의 인프라 레포지토리에서 관리하고, 이 레포지토리는 애플리케이션 코드, Docker 이미지 빌드, 앱 배포 자동화를 관리합니다.

## 구성

- `frontend/`: React/Vite 기반 웹 애플리케이션
- `backend/`: FastAPI 백엔드 서비스와 Dockerfile
- `backend/user-service`: 구독, 이메일 인증, 구독 해지, 뉴스 조회 API
- `backend/mail-service`: 인증 메일과 뉴스레터 메일 발송
- `backend/news-fetcher-service`: RSS 수집과 S3 snapshot 업로드
- `backend/news-summarizer-service`: 뉴스 요약, 저장, 조회 API
- `ansible/`: EKS 배포용 Ansible playbook
- `Jenkinsfile-app`: 보안 스캔, 테스트, 이미지 빌드, EKS 배포 파이프라인

## 로컬 실행

프론트엔드:

```bash
cd frontend
npm install
npm run dev
```

백엔드 예시:

```bash
cd backend/user-service
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --host 0.0.0.0 --port 8000
```

각 백엔드 서비스는 자체 README에 포트, migration, 테스트 방법을 정리해두었습니다.

## 백엔드 서비스

| Service | Port | 역할 |
|---------|------|------|
| `user-service` | 8000 | 사용자 구독, 인증, 해지, 뉴스 목록 proxy |
| `mail-service` | 8002 | 인증 메일, 뉴스레터 메일 발송 |
| `news-fetcher-service` | 8003 | RSS 수집, summarizer 호출, S3 snapshot 업로드 |
| `news-summarizer-service` | 8004 | 뉴스 요약, 저장, 조회 API |

## CI/CD

앱 파이프라인은 `Jenkinsfile-app`에 정의되어 있습니다.

주요 흐름:

1. Gitleaks로 secret 노출 여부를 검사합니다.
2. Trivy로 파일 시스템 취약점을 검사합니다.
3. flake8로 백엔드 코드 스타일을 검사합니다.
4. pytest로 백엔드 서비스별 테스트를 실행합니다.
5. Jenkins app deploy role을 assume합니다.
6. `IMAGE_TAG`가 40자리 Git SHA인지 검증합니다.
7. Docker 이미지를 빌드해 ECR에 올립니다.
8. Ansible playbook으로 선택한 image tag를 EKS에 배포합니다.

주요 파라미터:

- `IMAGE_TAG`: 앱 레포 Git SHA 40자리
- `DEPLOY_BACKEND`: `false`면 프론트엔드만 배포, `true`면 프론트엔드와 백엔드를 함께 배포

## Docker 이미지

이미지는 앱 레포 Git SHA로 태그됩니다.

- `patrasche-webserving`: 프론트엔드
- `patrasche-backend`: user-service
- `patrasche-crawler`: news-fetcher-service
- `patrasche-analyzer`: news-summarizer-service
- `patrasche-notifier`: mail-service

프론트엔드 운영 빌드는 `VITE_API_BASE_URL`을 통해 API 주소를 주입합니다.

## 배포 대상

- AWS region: `ap-northeast-2`
- EKS cluster: `patrasche-news`
- Kubernetes namespace: `patrasche`

## 현재 상태

- EKS 배포 흐름과 메일 발송 흐름을 테스트했습니다.
- 계정 이주 이후 운영 RDS 접속 정보, SSM/ExternalSecret 동기화, DB migration 상태는 최종 환경 기준으로 다시 확인해야 합니다.
- fetcher의 S3 snapshot 업로드와 summarizer의 외부 요약 API 호출은 운영 Secret과 quota 상태를 기준으로 최종 점검이 필요합니다.
