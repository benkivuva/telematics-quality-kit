FROM python:3.12-slim AS builder

ENV UV_VERSION=0.13.7 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN python -m pip install --no-cache-dir "uv==${UV_VERSION}"
WORKDIR /build
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv export --frozen --no-dev --no-emit-project -o /build/requirements.txt
RUN uv build --wheel --out-dir /wheels

FROM python:3.12-slim AS runtime
ENV VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /opt/venv \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app
COPY --from=builder /build/requirements.txt /tmp/requirements.txt
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
    && pip install --no-cache-dir --no-deps /wheels/*.whl \
    && rm -rf /wheels /tmp/requirements.txt
WORKDIR /app
COPY docker/entrypoint.py docker/healthcheck.py /app/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["python", "/app/healthcheck.py"]
ENTRYPOINT ["python", "/app/entrypoint.py"]
CMD ["serve", "--transport", "streamable-http", "--port", "8000"]
