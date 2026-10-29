# JUSTICE — all-in-one deploy image.
# Stage 1 builds the React/Vite frontend; stage 2 runs the FastAPI backend,
# which serves the built frontend and gates everything behind SITE_PASSWORD.
FROM node:22-slim AS frontend-build
WORKDIR /frontend
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libxcb1 \
    libx11-xcb1 \
    libxrender1 \
    libxi6 \
    libxext6 \
    libsm6 \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend
COPY --from=frontend-build /frontend/dist ./dist
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
