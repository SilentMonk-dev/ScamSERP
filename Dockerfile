FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SCAMSERP_DATA_DIR=/data
WORKDIR /app
COPY . /app
RUN if [ -f requirements.lock ]; then \
        python -m pip install --no-cache-dir -r requirements.lock && \
        python -m pip install --no-cache-dir --no-deps .; \
    else python -m pip install --no-cache-dir .; fi \
    && groupadd --gid 10001 scamserp \
    && useradd --uid 10001 --gid scamserp --no-create-home scamserp \
    && mkdir -p /data \
    && chown scamserp:scamserp /data
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).read()"
CMD ["python", "-m", "scamserp.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
