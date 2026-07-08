FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install system build deps required for pydantic-core compilation.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       curl \
       gcc \
       libpq-dev \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install rust toolchain into /usr/local to allow building pydantic-core when needed.
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH

RUN curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal --no-modify-path \
    && . /usr/local/cargo/env || true

COPY backend/requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install -r requirements.txt

COPY backend /app
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
