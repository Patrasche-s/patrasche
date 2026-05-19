# MSA 백엔드 CI 빌드용 초안.
# 운영 배포 시에는 서비스별 이미지(user/mail/fetcher/summarizer)로 분리하는 것을 권장합니다.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY user-service/ ./user-service/
COPY mail-service/ ./mail-service/
COPY news-fetcher-service/ ./news-fetcher-service/
COPY news-summarizer-service/ ./news-summarizer-service/

# news-fetcher-service: 팀 CronJob(news-crawler) 기본 타깃
WORKDIR /app/news-fetcher-service
ENV ENABLE_SCHEDULER=false
EXPOSE 8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
