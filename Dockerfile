FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN python -m pip install --upgrade pip

COPY pyproject.toml README.md ./
COPY main.py config.yaml ./
COPY models ./models
COPY pipeline ./pipeline
COPY sources ./sources
COPY tui ./tui
COPY util ./util
COPY web ./web

RUN python -m pip install -e .

EXPOSE 8787

CMD ["nase-web"]
