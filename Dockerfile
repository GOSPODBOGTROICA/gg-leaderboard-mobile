# ==============================================================================
# GGPoker Spin & Gold Mobile Leaderboard HUD — Production Container
# Base Image: Python 3.11-slim (minimal attack surface, ~140MB layer)
# ==============================================================================

FROM python:3.11-slim

# Prevent Python from writing bytecode and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Upgrade pip and install pinned application requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend application package, static PWA assets, and default config
COPY app ./app
COPY static ./static
COPY config.json .

# Create unprivileged service user for production isolation
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose HTTP port (default 8000, dynamically configurable via cloud $PORT env)
EXPOSE 8000

# Health check to ensure service readiness
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, os; port = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://localhost:{port}/api/health')" || exit 1

# Launch uvicorn bound to 0.0.0.0 and dynamic cloud $PORT with exec for signal propagation
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
