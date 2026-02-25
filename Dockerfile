FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements ./requirements
RUN pip install --upgrade pip \
    && pip install -r requirements/prod.txt

COPY . .

RUN mkdir -p /app/staticfiles /app/media /app/tmp /app/docker \
    && chmod +x /app/docker/entrypoint.sh \
    && addgroup --system django \
    && adduser --system --ingroup django django \
    && chown -R django:django /app

USER django

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
