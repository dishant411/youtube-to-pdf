FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 65532 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY tests /app/tests
COPY examples /app/examples
COPY node-backend/prompts /app/node-backend/prompts

USER 65532:65532

ENTRYPOINT ["python", "-m", "app.cli"]
