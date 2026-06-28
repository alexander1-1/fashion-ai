FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir flask requests beautifulsoup4 pillow \
    anthropic numpy gunicorn sentence-transformers

COPY . .

ENV PYTHONUNBUFFERED=1

CMD gunicorn app:app --bind 0.0.0.0:${PORT:-7860} --workers 1 --timeout 300
