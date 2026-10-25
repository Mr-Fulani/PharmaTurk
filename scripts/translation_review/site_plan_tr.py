# План точечных замен в опубликованных разделах лекарств ПО ТУРЕЦКОМУ ИСХОДНИКУ (только чтение).
#   BACKUPS="/tmp/membk/a.json /tmp/membk/b.json" python manage.py shell < site_plan_tr.py  → /tmp/site_plan.json
# Абзац раздела сопоставляется с исходником по строкам (как section_paragraph_problems); строка
# меняется, только если её турецкий абзац — исправленная запись памяти и строка равна одной из
# старых версий перевода этой записи (из бэкапов). Совпадение одного лишь русского текста не считается:
# «содержащихся в ADELEKS» у таблеток и «в ампуле ADELEKS» у ампул — разные исходники.
import json, os, re
from collections import Counter, defaultdict
from apps.ai.models import AIProcessingLog, AITranslationMemory
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.medicine_memory import BRAND_TOKEN, normalize_paragraph, split_paragraphs
from apps.ai.services.medicine_title import paragraph_brand
from apps.ai.services.translation_memory import source_hash
from apps.catalog.models import MedicineProductTranslation as T

olds = defaultdict(lambda: {"ru": set(), "en": set()})
for path in os.environ["BACKUPS"].split():
    for row in json.load(open(path)):
        f = row["fields"]
        if f["namespace"] == "medicine_paragraph":
            olds[f["source_hash"]]["ru"].add((f["ru_text"] or "").strip())
            olds[f["source_hash"]]["en"].add((f["en_text"] or "").strip())
new = {m.source_hash: {"ru": (m.ru_text or "").strip(), "en": (m.en_text or "").strip()}
       for m in AITranslationMemory.objects.filter(namespace="medicine_paragraph", source_hash__in=list(olds))}
print("исправленных записей:", len(olds), "| найдено в памяти:", len(new))

gen = ContentGenerator.__new__(ContentGenerator)
sources = {}
def source_for(base_id):
    if base_id not in sources:
        log = (AIProcessingLog.objects.filter(product_id=base_id, processing_type="full", application_status="applied")
               .order_by("-id").only("input_data").first())
        inp = (log.input_data if log else None) or {}
        sources[base_id] = (gen._build_medicine_source_sections(inp),
                            paragraph_brand(inp.get("name"), inp.get("active_ingredient")))
    return sources[base_id]

F = ("indications", "usage_instructions", "side_effects", "contraindications", "storage_conditions")
plan, stats, products = [], Counter(), set()
for t in T.objects.filter(locale__in=("ru", "en")).select_related("product").iterator(chunk_size=300):
    base = t.product.base_product_id or t.product_id
    secs, brand = None, None
    for f in F:
        text = getattr(t, f) or ""
        if not text.strip():
            continue
        if secs is None:
            secs, brand = source_for(base)
        src = secs.get(f) or ""
        lines = [(i, s.strip()) for i, s in enumerate(text.split("\n")) if s.strip()]
        for parts in (split_paragraphs(src), re.split(r"(\n+)", src.strip())):
            tr_parts = [p.strip() for p in parts[::2] if p.strip()]
            if len(tr_parts) == len(lines):
                break
        else:
            stats["раздел не сопоставлен"] += 1
            continue
        for part, (i, s) in zip(tr_parts, lines):
            h = source_hash(normalize_paragraph(part, brand))
            if h not in new:
                continue
            loc = t.locale
            cur = s.replace(brand, BRAND_TOKEN) if brand else s
            fixed = new[h][loc]
            if cur == fixed:
                stats["уже исправлено"] += 1
            elif cur in olds[h][loc]:
                plan.append({"base": base, "tr_id": t.pk, "locale": loc, "field": f, "line": i, "old": s,
                             "new": fixed.replace(BRAND_TOKEN, brand), "kind": "paragraph", "source": part})
                stats["замена"] += 1
                products.add(base)
            else:
                stats["на сайте другой текст — не трогаем"] += 1
print(dict(stats), "| лекарств:", len(products))
json.dump(plan, open("/tmp/site_plan.json", "w"), ensure_ascii=False)
print("→ /tmp/site_plan.json", len(plan))
