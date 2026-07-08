FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY backend /app
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
