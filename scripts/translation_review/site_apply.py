# Запись плана /tmp/site_plan.json в опубликованные разделы лекарств. Бэкап строк — /tmp/site-before.json.
# Строка меняется, только если на её месте по-прежнему старый текст.
import json
from collections import Counter, defaultdict
from django.core import serializers
from django.db import transaction
from apps.catalog.models import MedicineProductTranslation as T

plan = json.load(open("/tmp/site_plan.json"))
by_row = defaultdict(list)
for p in plan:
    by_row[p["tr_id"]].append(p)
rows = {t.pk: t for t in T.objects.filter(pk__in=list(by_row))}
open("/tmp/site-before.json", "w").write(serializers.serialize("json", list(rows.values())))
stats = Counter()
with transaction.atomic():
    for pk, items in by_row.items():
        t = rows[pk]
        fields = set()
        for f in {p["field"] for p in items}:
            lines = (getattr(t, f) or "").split("\n")
            for p in (x for x in items if x["field"] == f):
                i = p["line"]
                if i < len(lines) and lines[i].strip() == p["old"]:
                    lines[i] = lines[i].replace(p["old"], p["new"])
                    stats["applied"] += 1
                    fields.add(f)
                else:
                    stats["skipped_changed"] += 1
            setattr(t, f, "\n".join(lines))
        if fields:
            t.save(update_fields=sorted(fields))
            stats["rows_saved"] += 1
print(dict(stats), "| лекарств:", len({p["base"] for p in plan}))
