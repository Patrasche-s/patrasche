# Patrasche App

Patrasche 앱 레포지토리는 RSS 뉴스 수집, 요약, 사용자 구독, 이메일 인증, 뉴스레터 발송 기능을 담당합니다. 프론트엔드는 React/Vite로 구성되어 있고, 백엔드는 기능별 FastAPI 서비스로 분리되어 있습니다.

인프라 리소스와 Kubernetes 매니페스트는 인프라 레포지토리에서 관리하며, 이 레포지토리는 애플리케이션 코드, Docker 이미지 빌드, 테스트, 앱 배포 자동화를 담당합니다.

## 주요 기능

- 관심 카테고리 기반 사용자 구독
- 이메일 인증과 구독 해지
- RSS 뉴스 수집
- 뉴스 요약과 조회 API 제공
- 인증 메일과 뉴스레터 메일 발송
- Jenkins 기반 이미지 빌드, ECR push, EKS 배포

## 레포지토리 구조

- `frontend/`: React/Vite 기반 웹 애플리케이션
- `backend/`: FastAPI 백엔드 서비스와 Dockerfile
- `backend/user-service`: 구독, 이메일 인증, 해지, 뉴스 목록 proxy
- `backend/mail-service`: 인증 메일, 뉴스레터 발송, 발송 로그 저장
- `backend/news-fetcher-service`: RSS 수집, summarizer 호출, S3 snapshot 업로드
- `backend/news-summarizer-service`: 뉴스 요약, 저장, 조회 API
- `ansible/`: EKS Deployment와 CronJob image tag 갱신 playbook
- `Jenkinsfile-app`: 보안 스캔, lint/test, Docker build/push, EKS 배포 파이프라인

## 서비스 구성

| Service | Port | 역할 |
| --- | --- | --- |
| `frontend` | 80 | 사용자 화면, 구독/인증/뉴스 조회 UI |
| `user-service` | 8000 | 사용자 구독, 인증, 해지, 뉴스 목록 API |
| `mail-service` | 8002 | 인증 메일, 뉴스레터 메일 발송 |
| `news-fetcher-service` | 8003 | RSS 수집과 저장 흐름 실행 |
| `news-summarizer-service` | 8004 | 뉴스 요약, 저장, 내부 조회 API |

## 배포 흐름

1. Jenkins가 Gitleaks, Trivy, flake8, pytest를 실행합니다.
2. 배포 대상 `IMAGE_TAG`를 40자리 Git SHA로 확정합니다.
3. 프론트엔드와 백엔드 Docker 이미지를 빌드해 ECR에 push합니다.
4. Ansible playbook이 EKS Deployment와 fetcher CronJob image tag를 갱신합니다.
5. Kubernetes rollout을 통해 서비스 배포 상태를 확인합니다.

운영 프론트엔드 빌드는 `VITE_API_BASE_URL=https://api.patrasche.cloud` 값을 사용합니다.

## 환경과 Secret

로컬 실행에서는 서비스별 기본 SQLite DB 또는 README에 적힌 환경 변수를 사용할 수 있습니다. 운영 환경에서는 DB, SMTP, 외부 API key, 내부 token 값을 코드에 저장하지 않고, 인프라 레포의 SSM Parameter Store와 External Secrets Operator를 통해 Kubernetes Secret으로 주입합니다.

## 현재 검증 상태

다음 항목은 현재 배포 환경에서 검증 완료된 상태입니다.

- 앱 서비스 배포
- RDS 연결
- SSM / ExternalSecret / Kubernetes Secret 기반 환경 변수 주입 흐름
- fetcher CronJob 테스트
- 메일 발송 테스트
- 주요 도메인/Ingress/API 라우팅 흐름
- Jenkins 기반 앱 배포 흐름

## 로컬 실행 예시

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

각 모듈의 자세한 실행 방법은 `frontend/README.md`, `backend/README.md`, 각 backend service README를 참고합니다.
