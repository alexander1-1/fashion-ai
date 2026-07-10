FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir flask requests beautifulsoup4 pillow \
    anthropic numpy gunicorn sentence-transformers

COPY . .

# Фаза 2: сборка trend_signals.db из репозиторных данных
# (БД в .gitignore — регенерируется при каждом деплое, ~30 сек)
# signals_sync import подтягивает локально собранные сигналы MPStats/WB
# из output/wb_signals_export.json.gz — без него все тренды «ИННОВАТОРЫ».
RUN python migrate_csv_to_db.py \
    && python trends.py autoregister \
    && python signals_sync.py import \
    && python trends.py score

ENV PYTHONUNBUFFERED=1

CMD gunicorn app:app --bind 0.0.0.0:${PORT:-7860} --workers 1 --timeout 300
