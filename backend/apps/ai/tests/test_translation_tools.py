"""Инструменты проверки переводов (TD-031): режим показа, бэкап, отсев правок, перенос на сайт."""

import gzip
import json
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.serializers import deserialize

from apps.ai.models import AIProcessingLog, AITranslationMemory
from apps.ai.services import claude_batches, medicine_dictionaries as dictionaries, memory_review as review
from apps.ai.services.medicine_memory import BRAND_TOKEN, INN_NAMESPACE, PARAGRAPH_NAMESPACE
from apps.ai.services.medicine_seo import BRAND_NAMESPACE
from apps.ai.services.translation_memory import source_hash
from apps.catalog.models import MedicineProduct, MedicineProductTranslation, Product


def _run(*args) -> str:
    out = StringIO()
    call_command(*args, stdout=out)
    return out.getvalue()


def _memory(source, ru, en, namespace=PARAGRAPH_NAMESPACE):
    return AITranslationMemory.objects.create(
        namespace=namespace, source_hash=source_hash(source), source_text=source, ru_text=ru, en_text=en,
    )


def _record(pk, tr, ru, en, hits=0, ns=PARAGRAPH_NAMESPACE):
    return {"id": pk, "ns": ns, "tr": tr, "ru": ru, "en": en, "hits": hits, "log": None}


def _result(custom_id, payload, stop="end_turn"):
    usage = {"input": 1000, "output": 100, "cache_read": 0, "cache_write": 0}
    return {"id": custom_id, "type": "succeeded", "stop": stop, "text": json.dumps(payload, ensure_ascii=False), "usage": usage}


def _jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return str(path)


# Словарь: «dijit» устойчиво переводится как «дигит»/«digita».
ALIGNMENT = review.Alignment({
    "N": 100, "tr_df": {"dijit": 10},
    "ru": {"dijit": [["дигита", 0.9, 0.9]]},
    "en": {"dijit": [["digita", 0.9, 0.9]]},
})
VOCABULARY = {"ru": {"принимайте", "препарат"}, "en": {"take", "medicine"}}


def test_canon_joins_pdf_variants():
    assert review.canon("Doz  1O mg ’dir.") == review.canon("Doz 10 mg'dir")
    assert review.canon("Doz 1O mg") != review.canon("Doz 20 mg")


def test_alignment_counts_shared_records():
    records = [_record(i, "dijital ilaç", "дигиталис", "digitalis") for i in range(1, 4)]
    records += [_record(i, f"başka{i} metin{i}", f"другой{i}", f"other{i}") for i in range(4, 200)]
    data = review.build_alignment(records)
    assert data["N"] == 199
    assert data["tr_df"]["dijit"] == 3
    assert data["ru"]["dijit"] == [["дигита", 1.0, 1.0]]


def test_alignment_score_flags_missing_usual_term():
    assert ALIGNMENT.score("Dijital ilaç", "Цифровое лекарство", "Digitalis drug") == 0.9
    assert ALIGNMENT.score("Dijital ilaç", "Препарат дигиталиса", "Digitalis drug") == 0


def test_chunks_skip_checked_groups_and_rank_by_suspicion():
    records = [
        _record(1, "Dijital ilaç.", "Цифровое лекарство.", "Digital drug."),
        _record(2, "Dijital ilaç", "Цифровое лекарство", "Digital drug", hits=5),
        _record(3, "Normal metin.", "Обычный текст.", "Plain text."),
        _record(4, "Kontrol edildi.", "Проверено.", "Checked."),
        _record(5, "Kontrol edildi", "Проверено", "Checked"),
        _record(6, "Dijital metin.", "", "Digital text."),
        _record(7, "metformin", "Метформин", "Metformin", ns=INN_NAMESPACE),
    ]
    chunks, groups, reviewed, stats = review.build_chunks(records, ALIGNMENT, seen=[4], chunk_size=1)

    assert [chunk["items"][0]["i"] for chunk in chunks] == [2, 3]  # варианты — один представитель с большим hits
    assert "RU lacks the usual translation of 'dijital'" in chunks[0]["items"][0]["hint"]
    assert groups == {"2": [1, 2]}
    assert reviewed == [1, 2, 3, 4]
    assert stats["без перевода"] == 1
    assert review.build_chunks(records, ALIGNMENT, limit=1)[0][0]["items"][0]["i"] == 2


CHUNKS = {0: [{"i": 1, "tr": "Dijital ilaç alınız.", "ru": "Принимайте цифровой препарат.", "en": "Take digital medicine."}]}
ISSUE = {"i": 1, "lang": "ru", "severity": "critical", "category": "term", "problem": "x", "ru_fix": "", "en_fix": ""}


def _verdict(ru, en, real=True):
    return {"items": [{"i": 1, "real": real, "severity": "critical", "fix_was_wrong": False,
                       "ru_final": ru, "en_final": en, "reason": "y"}]}


def _collect(tmp_path, verify, fragments=()):
    review_file = _jsonl(tmp_path / "r.jsonl", [_result("r-0", {"checked": 1, "issues": [ISSUE]})])
    verify_file = _jsonl(tmp_path / "v.jsonl", [_result("v-0", verify)])
    return review.collect_fixes(CHUNKS, {}, ALIGNMENT, VOCABULARY, [review_file], [verify_file], list(fragments))


def test_collect_keeps_good_fix(tmp_path):
    fixes, rejected, summary = _collect(tmp_path, _verdict("Принимайте препарат дигиталиса.", "Take digitalis medicine."))
    assert [row["id"] for row in fixes] == [1] and not rejected
    assert summary["fix_critical"] == 1
    assert summary["cost_usd"]["total"] == pytest.approx((2 * 1000 * 0.05 + 2 * 100 * 0.25) / 1e6, abs=1e-4)


def test_collect_refuted_issue_gives_no_fix(tmp_path):
    fixes, rejected, summary = _collect(tmp_path, _verdict("", "", real=False))
    assert not fixes and not rejected
    assert summary["refuted"] == 1


@pytest.mark.parametrize("ru, en, reason", [
    ("Принимайте цифровой препарат.", "Take digital medicine.", "no_change"),
    ("Принимайте препарат дигиталиса ...", "Take digitalis medicine.", "ellipsis_added"),
    ("Принимайте препарат дигитал", "Take digitalis medicine.", "cut_word"),
])
def test_collect_rejects_bad_fix(tmp_path, ru, en, reason):
    fixes, rejected, _ = _collect(tmp_path, _verdict(ru, en))
    assert not fixes
    assert reason in rejected[0]["rejected"]


def test_rejection_keeps_brand_token():
    item = {"tr": f"{BRAND_TOKEN} alınız", "ru": f"Принимайте {BRAND_TOKEN}", "en": f"Take {BRAND_TOKEN}"}
    assert "brand_token_missing" in review.rejection_reasons(item, "Принимайте препарат", item["en"], ALIGNMENT, VOCABULARY)


def test_fragment_arbiter_decides(tmp_path):
    chunks = {0: [{"i": 1, "tr": "Dijital ilaç al", "ru": "Принимайте цифровой препарат", "en": "Take digital medicine"}]}
    review_file = _jsonl(tmp_path / "r.jsonl", [_result("r-0", {"checked": 1, "issues": [ISSUE]})])
    verify_file = _jsonl(tmp_path / "v.jsonl", [_result("v-0", _verdict("Принимайте препарат дигиталиса", ""))])
    verdict = {"items": [{"i": 1, "choice": "old", "ru_final": "", "en_final": "", "reason": "z"}]}
    fragment_file = _jsonl(tmp_path / "f.jsonl", [_result("f-0", verdict)])

    fixes, rejected, _ = review.collect_fixes(chunks, {}, ALIGNMENT, VOCABULARY, [review_file], [verify_file], [fragment_file])
    assert not fixes
    assert rejected[0]["rejected"][:1] == ["fragment_keep_old"]

    empty_file = _jsonl(tmp_path / "empty.jsonl", [])
    _, rejected, _ = review.collect_fixes(chunks, {}, ALIGNMENT, VOCABULARY, [review_file], [verify_file], [empty_file])
    assert "fragment_unjudged" in rejected[0]["rejected"]


def test_flagged_skips_foreign_ids_and_counts_cut_answers(tmp_path):
    results = _jsonl(tmp_path / "r.jsonl", [
        _result("r-0", {"checked": 1, "issues": [ISSUE, {**ISSUE, "i": 99}]}),
        _result("r-1", {"checked": 0, "issues": []}, stop="max_tokens"),
    ])
    rows, stats = review.flagged_rows(CHUNKS, [results])
    assert [item["i"] for item in rows[0]["items"]] == [1]
    assert stats["review_bad_id"] == 1
    assert stats["r_stop_max_tokens"] == 1


def test_updates_fit_variant_tail_to_its_source():
    records = [_record(1, "Doz alınız.", "Примите дозу", "Take"), _record(2, "Doz alınız", "Примите дозу", "Take"),
               _record(3, "Başka", "Другое", "Other")]
    fixes = [{"id": 1, "severity": "major", "ru_new": "Примите дозу вовремя.", "en_new": "Take in time.", "variants": [1, 2]}]
    updates = review.build_updates(records, fixes)
    assert [(row["id"], row["ru_new"]) for row in updates] == [(1, "Примите дозу вовремя."), (2, "Примите дозу вовремя")]


def _update(record, ru_new, en_new, **extra):
    return {"id": record.id, "rep": record.id, "severity": "major", "src": record.source_text,
            "ru_old": record.ru_text, "en_old": record.en_text, "ru_new": ru_new, "en_new": en_new, **extra}


@pytest.mark.django_db
def test_memory_apply_requires_flag_and_backup(tmp_path):
    record = _memory("Doz alınız.", "Примите дозу.", "Take a dose.")
    updates = tmp_path / "updates.json"
    updates.write_text(json.dumps([_update(record, "Примите дозу вовремя.", "Take a dose in time.")]), encoding="utf-8")

    assert "Только показ" in _run("medicine_memory_review", "apply", "--updates", str(updates))
    record.refresh_from_db()
    assert record.ru_text == "Примите дозу."

    with pytest.raises(CommandError, match="--backup"):
        _run("medicine_memory_review", "apply", "--updates", str(updates), "--apply")

    backup = tmp_path / "before.json"
    _run("medicine_memory_review", "apply", "--updates", str(updates), "--apply", "--backup", str(backup))
    record.refresh_from_db()
    assert record.ru_text == "Примите дозу вовремя."
    saved = next(deserialize("json", backup.read_text(encoding="utf-8"))).object
    assert (saved.pk, saved.ru_text) == (record.pk, "Примите дозу.")
    assert "совпадает" in _run("medicine_memory_review", "apply", "--updates", str(updates), "--verify")

    with pytest.raises(CommandError, match="уже есть"):
        _run("medicine_memory_review", "apply", "--updates", str(updates), "--apply", "--backup", str(backup))


@pytest.mark.django_db
def test_memory_apply_skips_changed_record_and_new_problems():
    changed = _memory("Birinci.", "Первый.", "First.")
    worse = _memory("Doz 10 mg.", "Доза 10 мг.", "Dose 10 mg.")
    updates = [_update(changed, "Первое.", "First one."), _update(worse, "Доза 20 мг.", "Dose 20 mg.")]
    AITranslationMemory.objects.filter(pk=changed.pk).update(ru_text="Правка в админке.")

    rows, stats, skipped = review.plan_memory_updates(updates)

    assert not rows
    assert stats["запись изменилась"] == 1
    assert stats["новые замечания проверки"] == 1
    assert [item[0] for item in skipped] == [changed.pk, worse.pk]


@pytest.mark.django_db
def test_export_writes_paragraphs_and_inn_only(tmp_path):
    _memory("Doz alınız.", "Примите дозу.", "Take a dose.")
    _memory("metformin", "Метформин", "Metformin", INN_NAMESPACE)
    _memory("MAJEZIK", "Мажезик", "MAJEZIK", BRAND_NAMESPACE)
    path = tmp_path / "memory.jsonl.gz"
    _run("medicine_memory_review", "export", "--out", str(path))
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        assert sorted(json.loads(line)["ns"] for line in handle) == [INN_NAMESPACE, PARAGRAPH_NAMESPACE]


def test_score_counts_fixed_and_found():
    labels = [{"idx": 1, "severity": "critical"}, {"idx": 2, "severity": "critical"}, {"idx": 3, "severity": "minor"}]
    report = review.score_against_labels([{"id": 1}, {"id": 9}], [{"id": 2}], labels)
    assert report[0] == {"severity": "critical", "labelled": 2, "fixed": 1, "found": 2}


def test_batch_submit_shows_estimate_without_api(tmp_path):
    source = _jsonl(tmp_path / "chunks.jsonl", [{"k": 0, "items": [{"i": 1, "tr": "a", "ru": "б", "en": "c", "hint": ""}]}])
    with mock.patch.object(claude_batches, "_client") as client:
        out = _run("medicine_claude_batch", "submit", "--kind", "review", "--effort", "high", "--input", source)
    client.assert_not_called()
    assert "Только показ" in out
    assert json.loads(out.splitlines()[0])["requests"] == 1


def test_batch_send_uses_strict_json_and_part_number(tmp_path, settings):
    settings.ANTHROPIC_API_KEY = "test"
    row = {"k": 7, "items": [{"id": 1}], "decisions": [{"id": 1, "status": "ok"}]}
    source = _jsonl(tmp_path / "chunks.jsonl", [row])
    with mock.patch.object(claude_batches, "_client") as client:
        client.return_value.messages.batches.create.return_value.id = "msgbatch_1"
        out = _run("medicine_claude_batch", "submit", "--kind", "inn_verify", "--effort", "xhigh", "--input", source, "--send")
    request = client.return_value.messages.batches.create.call_args.kwargs["requests"][0]
    assert json.loads(out) == {"batch_id": "msgbatch_1", "requests": 1}
    assert request["custom_id"] == "i-7"
    params = request["params"]
    assert params["model"] == "claude-haiku-5-5"
    assert params["max_tokens"] == 32000
    assert params["output_config"]["effort"] == "xhigh"
    assert params["output_config"]["format"]["schema"]["required"] == ["items"]
    assert "Решение первого проверяющего" in params["messages"][0]["content"]


def test_batch_results_flatten_answers():
    message = mock.Mock(stop_reason="end_turn", content=[mock.Mock(type="text", text="{}")])
    message.usage = mock.Mock(input_tokens=5, output_tokens=2, cache_read_input_tokens=None, cache_creation_input_tokens=1)
    entries = [
        mock.Mock(custom_id="r-0", result=mock.Mock(type="succeeded", message=message)),
        mock.Mock(custom_id="r-1", result=mock.Mock(type="expired")),
    ]
    with mock.patch.object(claude_batches, "_client") as client:
        client.return_value.messages.batches.results.return_value = entries
        rows = list(claude_batches.results("msgbatch_1"))
    assert rows[0]["usage"] == {"input": 5, "output": 2, "cache_read": 0, "cache_write": 1}
    assert rows[1] == {"id": "r-1", "type": "expired"}


def test_inn_chunks_sorted_by_atc_with_wikidata(tmp_path):
    (tmp_path / "wd_atc_labels.csv").write_text("item,code,ru,en,la\nQ1,a10ba02,метформин,metformin,metforminum\n", encoding="utf-8")
    (tmp_path / "wd_atc_alias.csv").write_text("item,lang,alias\nQ1,ru,Сиофор\n", encoding="utf-8")
    (tmp_path / "wd_who_inn.csv").write_text("item,inn,lang,codes\nQ1,metformin,en,A10BA02\n", encoding="utf-8")
    export = [
        {"id": 1, "tr": "yok", "ru": "Нет", "en": "None", "products": 1, "atc": []},
        {"id": 2, "tr": "metformin", "ru": "Метформин", "en": "Metformin", "products": 3, "atc": [["A10BA02", 1, 3]]},
    ]
    chunks = dictionaries.inn_chunks(export, dictionaries.wikidata_evidence(tmp_path), size=1)
    assert [chunk["items"][0]["id"] for chunk in chunks] == [2, 1]
    evidence = chunks[0]["items"][0]["atc"][0]["wikidata"][0]
    assert evidence["ru_aliases"] == ["Сиофор"]
    assert evidence["who_inn"] == ["en: metformin"]


def _inn_item(pk, tr, ru="Старое", en="Old", products=2):
    return {"id": pk, "tr": tr, "ru": ru, "en": en, "products": products, "atc": []}


def _inn_row(pk, tr, ru, en, status="fixed"):
    return {"id": pk, "tr": tr, "ru": ru, "en": en, "status": status, "reason": ""}


def test_collect_inn_filters_answers(tmp_path):
    chunks = [{"k": 0, "items": [
        _inn_item(1, "ketiapin", "Кетиапин", "Quetiapine"), _inn_item(2, "gliserin", "Глицерин", "Glycerol"),
        _inn_item(3, "x", "Икс", "X"), _inn_item(4, "y", "Игрек", "Y"), _inn_item(5, "z", "Зет", "Z"),
        _inn_item(6, "sennosid b", "Сеннозид", "Sennoside"), _inn_item(7, "w", "Вэ", "W"),
        _inn_item(8, "vitamin b1", "Витамин b1", "Vitamin b1"),
    ]}]
    answer = {"items": [
        _inn_row(1, "ketiapin", "Кветиапин", "Quetiapine"), _inn_row(2, "gliserin", "Глицерол", "Glycerol"),
        _inn_row(3, "x", "Ikс", "X"), _inn_row(4, "y", "Игрек", "Игрек"), _inn_row(5, "z", "Зет", "Z"),
        _inn_row(6, "sennosid b", "Сеннозид B", "Sennoside B"), _inn_row(7, "w", "Вэ", "W", status="unsure"),
        _inn_row(8, "vitamin b1", "Витамин B1", "Vitamin B1"),
        _inn_row(99, "чужая", "Чужая", "Foreign"),
    ]}
    updates, stats, notes = dictionaries.collect_inn(chunks, [_jsonl(tmp_path / "v.jsonl", [_result("i-0", answer)])])
    assert [row["id"] for row in updates] == [1, 6, 8]  # правка только регистра — тоже правка
    assert stats["оставлено решением владельца"] == 1
    assert stats["латиница в RU"] == 1
    assert stats["кириллица в EN"] == 1
    assert stats["без изменений"] == 1
    assert stats["unsure"] == 1
    assert stats["чужая запись"] == 1
    assert len(notes) == 2


@pytest.fixture
def medicine(db):
    product = Product.objects.create(name="METFORAL 500 MG FILM TABLET", slug="metforal-500", product_type="medicines")
    MedicineProduct.objects.filter(base_product=product).update(active_ingredient="metformin", atc_code="a10ba02")
    return product, MedicineProduct.objects.get(base_product=product)


@pytest.mark.django_db
def test_inn_apply_updates_dictionary_and_products(tmp_path, medicine):
    _, item = medicine
    record = _memory("metformin", "Метформен", "Metformin", INN_NAMESPACE)
    row = MedicineProductTranslation.objects.create(product=item, locale="ru", active_ingredient="Метформен")
    updates = tmp_path / "updates.json"
    updates.write_text(json.dumps([{
        "id": record.id, "tr": "metformin", "ru_old": "Метформен", "en_old": "Metformin",
        "ru_new": "Метформин", "en_new": "Metformin", "products": 1,
    }]), encoding="utf-8")

    export = dictionaries.export_inn()
    assert export[0]["products"] == 1
    assert export[0]["atc"] == [["A10BA02", 1, 1]]

    _run("medicine_inn_dictionary", "apply", "--updates", str(updates))
    record.refresh_from_db()
    assert record.ru_text == "Метформен"

    with pytest.raises(CommandError):
        _run("medicine_inn_dictionary", "apply", "--updates", str(updates), "--apply")

    backup = tmp_path / "before.json"
    _run("medicine_inn_dictionary", "apply", "--updates", str(updates), "--apply", "--backup", str(backup))
    record.refresh_from_db()
    row.refresh_from_db()
    assert record.ru_text == "Метформин"
    assert row.active_ingredient == "Метформин"
    assert "Метформен" in backup.read_text(encoding="utf-8")


@pytest.mark.parametrize("brand, ru, expected", [
    ("ENCEF", "Энджеф", "Энцеф"),
    ("CRESTOR", "Джрестор", "Крестор"),
    ("TEGELINE", "Тегелине", "Тегелин"),
    ("NICORETTE", "Никоретте", "Никоретте"),
    ("MAJEZIK", "Мажезик", "Мажезик"),
    ("BIO CEF", "Биоджеф", None),
    ("FUCITEC", "Фуджитек", "Фуцитек"),
])
def test_latin_reading(brand, ru, expected):
    assert dictionaries.latin_reading(brand, ru) == expected


def test_collect_brands_filters_answers(tmp_path):
    chunks = [{"k": 0, "items": [
        {"i": 1, "brand": "ENCEF"}, {"i": 2, "brand": "CAPD"}, {"i": 3, "brand": "NEXIUM"},
        {"i": 4, "brand": "TABLO"}, {"i": 5, "brand": "BIO CEF"},
    ]}]
    answer = {"items": [
        {"i": 1, "brand": "ENCEF", "ru": "Энджеф", "kind": "transliteration", "note": ""},
        {"i": 2, "brand": "CAPD", "ru": "CAPD", "kind": "abbreviation", "note": ""},
        {"i": 3, "brand": "NEXIUM", "ru": "Нексиум", "kind": "established", "note": ""},
        {"i": 4, "brand": "TABLO", "ru": "Табло таблетки", "kind": "established", "note": ""},
        {"i": 5, "brand": "BIO CEF", "ru": "Биоджеф", "kind": "transliteration", "note": ""},
    ]}
    brands, stats, dropped = dictionaries.collect_brands(chunks, [_jsonl(tmp_path / "v.jsonl", [_result("b-0", answer)])])
    assert brands == {"ENCEF": "Энцеф", "NEXIUM": "Нексиум"}
    assert stats["без кириллицы"] == 1
    assert [row[0] for row in dropped] == ["TABLO", "BIO CEF"]


def test_with_decisions_drops_chunks_without_answer(tmp_path):
    chunks = [{"k": 0, "items": [{"i": 1}]}, {"k": 1, "items": [{"i": 2}]}]
    results = _jsonl(tmp_path / "r.jsonl", [_result("b-0", {"items": [{"i": 1, "ru": "А"}]})])
    rows, stats = dictionaries.with_decisions(chunks, [results])
    assert [row["k"] for row in rows] == [0]
    assert rows[0]["decisions"] == [{"i": 1, "ru": "А"}]
    assert stats["частей без ответа"] == 1


@pytest.mark.django_db
def test_brand_export_and_apply_only_new_keys(tmp_path, medicine):
    assert [row["brand"] for row in dictionaries.export_brands()] == ["METFORAL"]
    _memory("MAJEZIK", "Мажезик", "MAJEZIK", BRAND_NAMESPACE)
    path = tmp_path / "brands.json"
    path.write_text(json.dumps({"MAJEZIK": "Другое", "METFORAL": "Метфорал"}), encoding="utf-8")

    _run("medicine_brand_dictionary", "apply", "--brands", str(path))
    assert AITranslationMemory.objects.filter(namespace=BRAND_NAMESPACE).count() == 1

    with pytest.raises(CommandError):
        _run("medicine_brand_dictionary", "apply", "--brands", str(path), "--apply")

    backup = tmp_path / "created.json"
    _run("medicine_brand_dictionary", "apply", "--brands", str(path), "--apply", "--backup", str(backup))
    assert json.loads(backup.read_text(encoding="utf-8")) == [source_hash("METFORAL")]
    assert AITranslationMemory.objects.get(namespace=BRAND_NAMESPACE, source_text="METFORAL").en_text == "METFORAL"
    assert AITranslationMemory.objects.get(namespace=BRAND_NAMESPACE, source_text="MAJEZIK").ru_text == "Мажезик"
    assert dictionaries.export_brands() == []


def _site_setup(medicine, tmp_path, shown):
    product, item = medicine
    AIProcessingLog.objects.create(
        product=product, processing_type="full", status="approved", application_status="applied",
        input_data={"name": product.name, "active_ingredient": "metformin", "attributes": {"source_tabs": {
            "usage_instructions": {"text": "METFORAL'i alınız.\n\nDoktora sorunuz."},
        }}},
    )
    key = f"{BRAND_TOKEN}'i alınız."
    record = _memory(key, f"Принимайте {BRAND_TOKEN}.", f"Take {BRAND_TOKEN}.")
    row = MedicineProductTranslation.objects.create(product=item, locale="ru", usage_instructions=shown)
    backup = tmp_path / "memory-before.json"
    backup.write_text(json.dumps([{"fields": {
        "namespace": PARAGRAPH_NAMESPACE, "source_hash": record.source_hash,
        "ru_text": f"Не принимайте {BRAND_TOKEN}.", "en_text": f"Do not take {BRAND_TOKEN}.",
    }}]), encoding="utf-8")
    return row, backup


@pytest.mark.django_db
def test_site_lines_replace_old_version_by_turkish_source(tmp_path, medicine):
    row, memory_backup = _site_setup(medicine, tmp_path, "Не принимайте METFORAL.\nСпросите врача.")
    plan = tmp_path / "plan.json"
    _run("medicine_site_lines", "plan", "--backups", str(memory_backup), "--out", str(plan))
    assert json.loads(plan.read_text(encoding="utf-8"))[0]["new"] == "Принимайте METFORAL."

    assert "Только показ" in _run("medicine_site_lines", "apply", "--plan", str(plan))
    row.refresh_from_db()
    assert row.usage_instructions.startswith("Не принимайте")

    with pytest.raises(CommandError):
        _run("medicine_site_lines", "apply", "--plan", str(plan), "--apply")

    backup = tmp_path / "rows-before.json"
    _run("medicine_site_lines", "apply", "--plan", str(plan), "--apply", "--backup", str(backup))
    row.refresh_from_db()
    assert row.usage_instructions == "Принимайте METFORAL.\nСпросите врача."
    assert "Не принимайте METFORAL" in backup.read_text(encoding="utf-8")


@pytest.mark.django_db
def test_site_lines_leave_other_text_alone(tmp_path, medicine):
    row, memory_backup = _site_setup(medicine, tmp_path, "Ручная правка.\nСпросите врача.")
    plan = tmp_path / "plan.json"
    out = _run("medicine_site_lines", "plan", "--backups", str(memory_backup), "--out", str(plan))
    assert json.loads(plan.read_text(encoding="utf-8")) == []
    assert "на сайте другой текст" in out


@pytest.mark.django_db
def test_site_lines_skip_line_changed_after_plan(tmp_path, medicine):
    row, memory_backup = _site_setup(medicine, tmp_path, "Не принимайте METFORAL.\nСпросите врача.")
    plan = tmp_path / "plan.json"
    _run("medicine_site_lines", "plan", "--backups", str(memory_backup), "--out", str(plan))
    MedicineProductTranslation.objects.filter(pk=row.pk).update(usage_instructions="Новый текст.\nСпросите врача.")
    backup = tmp_path / "rows-before.json"
    out = _run("medicine_site_lines", "apply", "--plan", str(plan), "--apply", "--backup", str(backup))
    assert "текст изменился" in out
    row.refresh_from_db()
    assert row.usage_instructions == "Новый текст.\nСпросите врача."


@pytest.mark.django_db
def test_title_diagnostics_save_and_compare(tmp_path, medicine):
    product, _ = medicine
    Product.objects.create(name="NEPONYATNO", slug="neponyatno", product_type="medicines")
    snapshot = tmp_path / "titles.json"
    out = _run("medicine_title_diagnostics", "--save", str(snapshot))
    assert '"шаблон собрал": 1' in out
    assert "NEPONYATNO" in out

    data = json.loads(snapshot.read_text(encoding="utf-8"))
    assert data[str(product.id)]["title"]["ru"].startswith("METFORAL 500 мг")
    data[str(product.id)]["title"] = None
    snapshot.write_text(json.dumps(data), encoding="utf-8")
    assert '"появилось": 1' in _run("medicine_title_diagnostics", "--compare", str(snapshot))


@pytest.mark.django_db
def test_title_diagnostics_moderation_splits_template_and_check(medicine):
    product, _ = medicine
    AIProcessingLog.objects.create(product=product, processing_type="full", status="moderation", generated_title="METFORAL", input_data={})
    with mock.patch("apps.ai.management.commands.medicine_title_diagnostics.SemanticValidator") as validator:
        validator.return_value.validate_log.return_value.reasons = ["title_untranslated", "seo_bad"]
        out = _run("medicine_title_diagnostics", "--moderation")
    assert '"title_untranslated: шаблон собрал, брак проверки": 1' in out
