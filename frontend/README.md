# Patrasche Frontend

Patrasche 프론트엔드는 React/Vite 기반 웹 애플리케이션입니다. 사용자는 이 화면에서 뉴스 목록을 보고, 관심 카테고리를 선택해 구독을 신청하거나 인증/해지 흐름을 진행합니다.

## 로컬 실행

```bash
npm install
npm run dev
```

API 서버 주소는 `VITE_API_BASE_URL`로 지정합니다.

설정하지 않으면 기본값은 다음 주소입니다.

```text
https://api.patrasche.cloud
```

로컬 백엔드를 직접 바라보게 하려면 다음처럼 실행할 수 있습니다.

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## 빌드

```bash
npm run build
```

Jenkins 앱 파이프라인은 운영 Docker 이미지를 빌드할 때 `VITE_API_BASE_URL`을 주입합니다.

결과 이미지는 ECR에 다음 형식으로 push됩니다.

```text
patrasche-webserving:<40-character-git-sha>
```

## 배포

프론트엔드는 nginx 기반 Docker 이미지로 서빙됩니다. Kubernetes에서는 `webserving` deployment와 service로 배포되고, Ingress를 통해 public domain과 연결됩니다.
