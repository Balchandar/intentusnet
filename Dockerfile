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

# Copy metadata first (better caching)
COPY pyproject.toml .
COPY README.md .
COPY LICENSE .

RUN pip install --upgrade pip setuptools wheel
RUN pip install --prefix=/install .

##############################################
# Stage 2 — Runtime image
##############################################
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libzmq3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy source code and demos
COPY src /app/src
COPY examples /app/examples

# Make both src/ and examples/ importable
ENV PYTHONPATH="/app/src:/app"

##############################################
# Default command — advanced demo (CLI)
##############################################
CMD ["python", "examples/advanced/demo_advanced_research.py"]
