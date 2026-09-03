FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app
COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY src ./src
COPY migrations ./migrations
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/papers /models-cache \
    && chown -R app:app /app /data /models-cache
USER app

EXPOSE 8088
CMD ["uvicorn", "omniscope.main:app", "--host", "0.0.0.0", "--port", "8088"]
