# =============================================================================
# Dockerfile - Crypto Trading Bot (Main Bot)
# =============================================================================
# Multi-stage build untuk image size minimal
# =============================================================================

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files + unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Python dependencies (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Create required directories
RUN mkdir -p data logs models backups

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import os; print('OK')" || exit 1

# Non-root user
RUN useradd -m -u 1000 cryptobot && \
    chown -R cryptobot:cryptobot /app
USER cryptobot

# Default command
CMD ["python", "bot.py"]
