##############################################
# Stage 1 — Build dependencies
##############################################
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    libzmq3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Metadata for dependency resolver
COPY pyproject.toml .
COPY README.md .
COPY LICENSE .

RUN pip install --upgrade pip setuptools wheel
RUN pip install --prefix=/install .

##############################################
# Stage 2 — Runtime Image
##############################################
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libzmq3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

WORKDIR /app

# Copy source and examples
COPY src /app/src
COPY examples /app/examples

# Critical: make both src/ and examples/ importable
ENV PYTHONPATH="/app/src:/app"

##############################################
# Default Command (FastAPI)
##############################################
CMD ["uvicorn", "examples.advanced.web_server:app", "--host", "0.0.0.0", "--port", "8000"]
