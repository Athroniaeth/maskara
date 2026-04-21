# syntax=docker/dockerfile:1.7

# =============================================================================
# Stage 1: builder — install piighost into a venv we can copy into distroless
# =============================================================================
# TODO: pin to real digest before publish — fetch via `docker buildx imagetools inspect python:3.12-slim-bookworm`
FROM python:3.12-slim-bookworm@sha256:0000000000000000000000000000000000000000000000000000000000000000 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install uv for deterministic dependency resolution
RUN pip install --no-cache-dir "uv>=0.4" && \
    rm -rf /root/.cache

# Copy dependency manifests first (better layer cache)
COPY pyproject.toml uv.lock ./
COPY README.md ./

# Copy source
COPY src/ ./src/

# Install piighost + slim extras into an isolated venv
RUN uv venv /opt/piighost && \
    . /opt/piighost/bin/activate && \
    uv pip install --python /opt/piighost/bin/python \
        --no-deps -e ".[mcp,client]" && \
    uv pip install --python /opt/piighost/bin/python \
        "fastmcp>=2.0" "typer>=0.12" "httpx>=0.28" \
        "cryptography>=43" "sqlalchemy>=2" "aiosqlite>=0.20"

# Append UID 10001 entry for runtime
RUN echo "piighost:x:10001:10001::/var/lib/piighost:/sbin/nologin" >> /etc/passwd && \
    cp /etc/passwd /etc/passwd.piighost

# =============================================================================
# Stage 2: slim — distroless runtime, no shell, no package manager
# =============================================================================
# TODO: pin to real digest before publish — fetch via `docker buildx imagetools inspect gcr.io/distroless/python3-debian12:nonroot`
FROM gcr.io/distroless/python3-debian12:nonroot@sha256:0000000000000000000000000000000000000000000000000000000000000000 AS slim

# Override the default nonroot UID (65532) with the piighost UID (10001)
COPY --from=builder /etc/passwd.piighost /etc/passwd

# Copy the venv
COPY --from=builder /opt/piighost /opt/piighost

# Copy entrypoint (read-only)
COPY --chown=10001:10001 docker/entrypoint.sh /entrypoint.sh

ENV PATH=/opt/piighost/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIIGHOST_DATA_DIR=/var/lib/piighost \
    PIIGHOST_IMAGE_VARIANT=slim

USER 10001

WORKDIR /var/lib/piighost

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-m", "piighost.cli.main", "healthcheck"]

ENTRYPOINT ["/entrypoint.sh"]
CMD ["mcp"]
