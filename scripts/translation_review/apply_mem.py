# Исправления проверки памяти (TD-025) → память medicine_paragraph. Запуск в контейнере backend:
#   UPDATES=/tmp/td025_updates.json BACKUP=/tmp/td025_mem_before.json [APPLY=1] \
#   python manage.py shell -c "exec(open('/tmp/td025_apply_mem.py').read())"
# Без APPLY=1 — пробный прогон. Пишем, только если исходник и перевод записи не менялись с выгрузки и
# paragraph_problems не даёт новых замечаний. Бэкап затронутых строк — BACKUP (до записи); запись —
# партиями по 1000 в своей транзакции; записи не удаляются. VERIFY=1 — только сверка уже записанного.
import json, os
from collections import Counter
from django.core import serializers
from django.db import transaction
from apps.ai.models import AITranslationMemory as M
from apps.ai.services.medicine_memory import paragraph_problems

updates = json.load(open(os.environ["UPDATES"]))
by_id = M.objects.in_bulk([u["id"] for u in updates])
if os.environ.get("VERIFY") == "1":
    print(dict(Counter("совпадает" if by_id[u["id"]].ru_text == u["ru_new"] and by_id[u["id"]].en_text == u["en_new"]
                       else "расходится" for u in updates)))
    raise SystemExit
norm = lambda s: " ".join((s or "").split())
stats, rows, skipped = Counter(), [], []
for u in updates:
    m = by_id.get(u["id"])
    if not m or m.namespace != "medicine_paragraph" or m.source_text != u["src"]:
        stats["нет записи"] += 1; skipped.append((u["id"], "missing")); continue
    if norm(m.ru_text) != norm(u["ru_old"]) or norm(m.en_text) != norm(u["en_old"]):
        stats["запись изменилась"] += 1; skipped.append((u["id"], "changed")); continue
    before = set(paragraph_problems(m.source_text, m.ru_text, m.en_text))
    after = set(paragraph_problems(m.source_text, u["ru_new"], u["en_new"]))
    if after - before:
        stats["новые замечания проверки"] += 1; skipped.append((u["id"], sorted(after - before))); continue
    rows.append((m, u["ru_new"], u["en_new"])); stats["к записи " + u["severity"]] += 1
print(dict(stats), "всего к записи", len(rows))
for s in skipped[:20]:
    print("  ПРОПУСК", s)
if os.environ.get("APPLY") == "1":
    open(os.environ["BACKUP"], "w").write(serializers.serialize("json", [m for m, _, _ in rows]))
    for start in range(0, len(rows), 1000):
        with transaction.atomic():
            for m, ru, en in rows[start:start + 1000]:
                m.ru_text, m.en_text = ru, en
                m.save(update_fields=["ru_text", "en_text", "updated_at"])
    print("записано", len(rows))
