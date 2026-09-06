# Backend image: FastAPI + PyMongo Async, non-root, read-only-rootfs friendly.
#
# Stages:
#   deps    - creates /opt/venv with the fully pinned runtime closure (no compiler needed: all wheels)
#   test    - adds pinned test deps and runs the unit tests; the runtime stage copies the
#             application code from here, so a failing test fails the whole build
#   runtime - slim image, dedicated uid/gid 10001, no shell login, listens on 0.0.0.0:8000

FROM python:3.13.15-slim-trixie AS deps
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
RUN python -m venv /opt/venv
COPY requirements.txt ./
RUN /opt/venv/bin/pip install --no-deps --requirement requirements.txt \
 && /opt/venv/bin/pip check

FROM deps AS test
COPY requirements-dev.txt ./
RUN /opt/venv/bin/pip install --no-deps --requirement requirements-dev.txt \
 && /opt/venv/bin/pip check
COPY pyproject.toml ./
COPY app ./app
COPY tests ./tests
RUN /opt/venv/bin/python -m pytest -q

FROM python:3.13.15-slim-trixie AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid 10001 --no-create-home \
      --home-dir /nonexistent --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=deps /opt/venv /opt/venv
COPY --from=test /build/app ./app
USER 10001:10001
EXPOSE 8000
# uvicorn is PID 1: it handles SIGTERM, stops accepting connections, waits for in-flight
# requests (bounded by --timeout-graceful-shutdown) and then runs the lifespan shutdown,
# which closes the MongoDB client.
CMD ["uvicorn", "app.main:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "20", "--no-server-header"]
