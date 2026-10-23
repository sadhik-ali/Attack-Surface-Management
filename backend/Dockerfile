FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# asyncpg and cryptography ship manylinux wheels; no compiler is needed.
COPY requirements-prod.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt

RUN useradd --create-home --uid 10001 asm
COPY --chown=asm:asm alembic.ini ./
COPY --chown=asm:asm alembic ./alembic
COPY --chown=asm:asm app ./app

USER asm
EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010", "--proxy-headers", "--forwarded-allow-ips", "*"]
