FROM python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    API_PORT=8000

WORKDIR /srv/promptvault

RUN groupadd --system promptvault \
    && useradd --system --gid promptvault --home-dir /srv/promptvault promptvault

COPY api/requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir -r /tmp/requirements.lock

FROM base AS runtime

COPY --chown=promptvault:promptvault api ./api
COPY --chown=promptvault:promptvault db ./db
COPY --chown=promptvault:promptvault scripts ./scripts

USER promptvault

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["sh", "-c", "exec uvicorn api.app.main:app --host 0.0.0.0 --port ${API_PORT:-8000}"]

FROM base AS test

USER root
COPY api/requirements-dev.lock /tmp/requirements-dev.lock
RUN python -m pip install --no-cache-dir -r /tmp/requirements-dev.lock

COPY --chown=promptvault:promptvault pyproject.toml ./pyproject.toml
COPY --chown=promptvault:promptvault api ./api
COPY --chown=promptvault:promptvault db ./db
COPY --chown=promptvault:promptvault docs ./docs
COPY --chown=promptvault:promptvault scripts ./scripts
COPY --chown=promptvault:promptvault tests ./tests

USER promptvault
