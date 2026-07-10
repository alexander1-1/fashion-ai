# Fashion-CLIP: пересборка подиума

Что сделано в этой фазе: замена ванильного CLIP (`clip-ViT-B-32`) на
**Fashion-CLIP** (`patrickjohncyh/fashion-clip`, дообучен на 800K fashion-пар,
F1 0.83 vs 0.66), переиндексация всех 17 880 луков, RU→EN перевод
поисковых запросов и диверсификация «Похожих» (кап 12 луков из того же показа,
`?same_show=all` отключает).

## Новые/изменённые файлы

- `reindex_fashion_clip.py` — сборка нового индекса (новое)
- `translate_query.py` — RU→EN: словарь + стемминг + Haiku-фолбэк (новое)
- `deploy_hf_fclip.py` — деплой на HF Space (новое)
- `app_hf.py` — авто-выбор Fashion-CLIP при наличии `fclip_*`, диверсификация
- `app.py` — перевод запроса до проксирования, проброс `same_show`, лимит CSV

## Порядок запуска (на твоём Mac)

### 1. Зависимости (один раз)
```bash
cd ~/Desktop/runway_scraper
pip3 install torch transformers pillow requests numpy
```

### 2. Тест на 100 луках (~2 мин)
```bash
python3 reindex_fashion_clip.py --limit 100
python3 reindex_fashion_clip.py --selftest
```
В selftest у «tweed jacket and skirt suit» в топе должны быть Chanel.
После теста удали пробный индекс, чтобы полный прогон начался с нуля:
```bash
rm output/fclip_index.npy output/fclip_metadata.json
```

### 3. Полная переиндексация (~1–3 ч на Apple Silicon)
```bash
python3 reindex_fashion_clip.py
```
Можно прерывать — прогресс сохраняется каждые 200 луков.
Итог: `output/fclip_index.npy` (~34 MB) + `output/fclip_metadata.json`.

### 4. Локальная проверка приложения
```bash
python3 app_hf.py   # в логе: "Fashion-CLIP loaded — 17880 looks indexed"
```
Проверь в браузере: поиск «красное вечернее платье», кнопку «Похожие».

### 5. Деплой HF Space
Старый HF-токен светился в истории чатов — создай новый на
huggingface.co/settings/tokens (и отзови старый), затем:
```bash
export HF_TOKEN=hf_НОВЫЙ_ТОКЕН
python3 deploy_hf_fclip.py
```

### 6. Деплой Railway (git)
```bash
git add app.py app_hf.py translate_query.py reindex_fashion_clip.py deploy_hf_fclip.py README_FCLIP.md
git commit -m "Fashion-CLIP: переиндексация подиума + RU-перевод запросов + диверсификация похожих"
git push origin main
```
Внимание: локально есть незапушенная Фаза 6 (`bb2b1e5`) — push отправит и её.

### 7. Проверка после деплоя
```bash
curl "https://fashion-ai-production-1e53.up.railway.app/api/search?q=красное+вечернее+платье" | head -c 400
curl "https://fashion-ai-production-1e53.up.railway.app/api/enrichment-status"
```
Второй запрос должен показать `enriched: 17880` (до этого показывал 184 —
если после редеплоя не исправится, копаем дальше).
