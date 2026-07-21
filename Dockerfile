FROM python:3.11-slim

# Cache buster: 2026-07-21-v3.0-qrcode
ARG CACHE_BUST=1

WORKDIR /app

# Install deps (qrcode[pil] requires Pillow for image generation)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend and frontend
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

WORKDIR /app/backend

# Expose port
EXPOSE 8000

CMD ["python", "app.py"]
