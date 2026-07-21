FROM python:3.11-slim

WORKDIR /app

# Install deps first (for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend and frontend
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

WORKDIR /app/backend

CMD ["python", "app.py"]
