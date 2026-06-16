# Patrasche Backend

FastAPI backend services for Patrasche.

## Services

- `user-service`: User API, subscriptions, verification, and unsubscribe flows. Default local port: `8000`.
- `mail-service`: Email delivery service. Default local port: `8002`.
- `news-fetcher-service`: RSS fetcher and S3 snapshot uploader. Default local port: `8003`.
- `news-summarizer-service`: News summarizer and news read API. Default local port: `8004`.

Each service has its own README with local run, migration, troubleshooting, and test notes.

## Tests

The Jenkins app pipeline installs each service's requirements and runs:

```bash
cd backend/mail-service && pytest tests/ -v
cd backend/news-fetcher-service && pytest tests/ -v
cd backend/news-summarizer-service && pytest tests/ -v
cd backend/user-service && pytest tests/ -v
```

It also runs flake8 against all four services with `--max-line-length=130`.

## Docker Builds

Build context is the `backend/` directory. Dockerfiles live directly under `backend/`, matching the Jenkins image build paths.

From the repository root:

```bash
docker build -f backend/Dockerfile.user backend
docker build -f backend/Dockerfile.mail backend
docker build -f backend/Dockerfile.fetcher backend
docker build -f backend/Dockerfile.summarizer backend
```

From inside `backend/`:

```bash
docker build -f Dockerfile.user .
```

## ECR Image Mapping

- `Dockerfile.user` -> `patrasche-backend`
- `Dockerfile.fetcher` -> `patrasche-crawler`
- `Dockerfile.summarizer` -> `patrasche-analyzer`
- `Dockerfile.mail` -> `patrasche-notifier`

Images are tagged with the 40-character app repository Git SHA used as `IMAGE_TAG` in Jenkins.
