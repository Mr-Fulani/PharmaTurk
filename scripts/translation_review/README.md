# Проверка памяти абзацев инструкций лекарств через Claude API (TD-025)

Скрипты проверки и исправления записей `AITranslationMemory` (namespace `medicine_paragraph`)
моделью `claude-haiku-5-5` через Message Batches API. Схема, цифры и ловушки —
[MEDICINE_TRANSLATION_KNOWLEDGE_BASE.md](../../docs/MEDICINE_TRANSLATION_KNOWLEDGE_BASE.md).

Где выполняются: `batch_review.py`, `apply_mem.py`, `site_plan_tr.py`, `site_apply.py` — в контейнере
backend прода (ключ `ANTHROPIC_API_KEY` берётся из окружения контейнера, наружу не копируется).
Остальное — на рабочей машине, `python3 -I`. Словарь `alignment.json` и выгрузка памяти лежат вне
репозитория (`~/pharmaturk-translation-work/`).

| шаг | скрипт | что делает |
|---|---|---|
| 1 | `export_memory.py` из `memory_export/` рабочей папки | выгрузка памяти в JSON lines |
| 2 | `prepare_chunks.py` | непроверенные записи → представители вариантов PDF → части по 40 с подсказкой словаря |
| 3 | `batch_review.py submit review high` и `… xhigh` | два прохода проверяющего (данные — stdin/stdout) |
| 4 | `collect_fixes.py flagged` → `batch_review.py submit verify high` | скептик сверяет каждую правку |
| 5 | `collect_fixes.py fragments` → `batch_review.py submit fragment high` | арбитр правок абзацев-обрывков |
| 6 | `collect_fixes.py fixes` | фильтры, итог, стоимость по `usage` |
| 7 | `make_updates.py` | файл записи: представитель + варианты, хвостовая пунктуация вариантов |
| 8 | `apply_mem.py` | пробный прогон, затем `APPLY=1`: бэкап строк, запись партиями, `VERIFY=1` — сверка |
| 9 | `site_plan_tr.py` → `site_apply.py` | замена исправленных абзацев на сайте только по турецкому исходнику |

Пример запуска шага 3 с рабочей машины (обёртка `rb.sh` копирует скрипт в контейнер и сжимает поток):

```bash
gzip -c part0.jsonl | ssh -i ~/3116 deploy@204.168.175.164 "docker cp /tmp/batch_review.py mudaroba-backend-1:/tmp/ && gunzip -c | docker exec -i mudaroba-backend-1 /app/.venv/bin/python /tmp/batch_review.py submit review high | gzip -c" | gunzip -c
```
