# Image unique : API + interface web compilée
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AP_FRONTEND_DIST=/app/frontend/dist AP_STORAGE_DIR=/data/storage
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
RUN useradd -r -u 1001 ap && mkdir -p /data/storage && chown -R ap /data
USER ap
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
