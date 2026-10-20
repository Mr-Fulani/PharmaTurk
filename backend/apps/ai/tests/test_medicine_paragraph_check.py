"""Сдвинутые переводы абзацев инструкций: правила без LLM и аудит памяти.

Примеры — записи памяти medicine_paragraph с прода (20.10.2026).
"""

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import F

from apps.ai.management.commands.medicine_paragraph_audit import SUSPECT_NAMESPACE
from apps.ai.models import AITranslationMemory
from apps.ai.services.medicine_memory import PARAGRAPH_NAMESPACE, check_paragraph_payload, paragraph_problems
from apps.ai.services.medicine_paragraph_check import audit_sequence, item_problems, plain_numbers, request_shift
from apps.ai.services.translation_memory import lookup, remember

# Раздел инструкции VISCOTEARS с верными переводами (в памяти они стояли со сдвигом).
VISCOTEARS = [
    (
        "VISCOTEARS geçici bir süre için bulanık görmenize neden olabilir. Görüşünüz düzelene kadar araç ve "
        "makine kullanmayınız..",
        "VISCOTEARS может временно вызвать затуманивание зрения. Не управляйте автомобилем и не используйте "
        "машины, пока ваше зрение не восстановится.",
        "VISCOTEARS may temporarily cause blurred vision. Do not drive or operate machinery until your vision "
        "is clear.",
    ),
    (
        "VISCOTEARS'ın içeriğinde bulunan bazı yardımcı maddeler hakkında önemli bilgiler",
        "Важная информация о некоторых вспомогательных веществах, содержащихся в VISCOTEARS",
        "Important information about some excipients contained in VISCOTEARS",
    ),
    (
        "VISCOTEARS'ın içeriğinde bulunan maddelerden birine aşırı duyarlılığınız olmadığı sürece, bu "
        "maddelerin kullanımından doğacak bir problem beklenmez.",
        "Если у вас нет повышенной чувствительности к любому из компонентов, содержащихся в VISCOTEARS, не "
        "ожидается никаких проблем от их использования.",
        "Unless you have a hypersensitivity to any of the components contained in VISCOTEARS, no problems are "
        "expected from their use.",
    ),
    (
        "VISCOTEARS sodyum ve sorbitol içermektedir ancak, uygulama yolu nedeniyle herhangi bir uyarı "
        "gerekmemektedir.",
        "VISCOTEARS содержит натрий и сорбитол, однако, из-за способа применения никаких предупреждений не "
        "требуется.",
        "VISCOTEARS contains sodium and sorbitol, however, no warnings are required due to the route of "
        "administration.",
    ),
    (
        "Eğer reçeteli ya da reçetesiz herhangi bir ilacı şu anda kullanıyorsanız veya son zamanlarda "
        "kullandınızsa lütfen doktorunuza veya eczacınıza bunlar hakkında bilgi veriniz.",
        "Если вы в настоящее время принимаете или недавно принимали какие-либо рецептурные или безрецептурные "
        "препараты, пожалуйста, сообщите об этом вашему врачу или фармацевту.",
        "If you are currently taking or have recently taken any prescription or over-the-counter medications, "
        "please inform your doctor or pharmacist about them.",
    ),
    ("5. VISCOTEARS'IN SAKLANMASI", "5. ХРАНЕНИЕ VISCOTEARS", "5. STORAGE OF VISCOTEARS"),
    (
        "VISCOTEARS'ı çocukların göremeyeceği, erişemeyeceği yerlerde ve ambalajında saklayınız.",
        "Храните VISCOTEARS в недоступном для детей месте и в упаковке.",
        "Store VISCOTEARS in a place out of the reach of children and in its packaging.",
    ),
    (
        "25°C'nin altındaki oda sıcaklığında saklayınız.",
        "Храните при комнатной температуре ниже 25°C.",
        "Store at room temperature below 25°C.",
    ),
    (
        "Kullandıktan sonra kapağını hemen kapatınız.",
        "После использования сразу закройте крышку.",
        "Immediately close the cap after use.",
    ),
    (
        "Tüp açıldıktan sonra 6 hafta içerisinde kullanılmalıdır. Kullanılmayan kısmı saklamayınız.",
        "После открытия тюбик следует использовать в течение 6 недель. Не храните неиспользованную часть.",
        "The tube should be used within 6 weeks after opening. Do not store any unused portion.",
    ),
]
SOURCES = [source for source, _, _ in VISCOTEARS]


def _shifted_from(start):
    """Ответ модели, пропустившей абзац start: дальше каждому достаётся перевод следующего."""
    ru = [row[1] for row in VISCOTEARS]
    en = [row[2] for row in VISCOTEARS]
    return ru[:start] + ru[start + 1:] + [""], en[:start] + en[start + 1:] + [""]


@pytest.mark.parametrize("source, ru, en, problem", [
    (
        "2. GAVISCON'U KULLANMADAN ÖNCE DİKKAT EDİLMESİ GEREKENLER",
        "НЕ ИСПОЛЬЗУЙТЕ GAVISCON в следующих случаях:",
        "DO NOT USE GAVISCON in the following situations:",
        "heading_mismatch",
    ),
    (
        "5. VISCOTEARS'IN SAKLANMASI",
        "Храните при комнатной температуре ниже 25°C.",
        "Store at room temperature below 25°C.",
        "number_mismatch",
    ),
    (
        "5. MOUNJARO'NUN SAKLANMASI",
        "Используйте в соответствии с указанным сроком годности.",
        "Store in the refrigerator at a temperature between 2 and 8°C. Do not freeze.",
        "ru_en_mismatch",
    ),
    (
        "Yaygın olmayan: 100 hastanın birinden az, fakat 1.000 hastanın birinden fazla görülebilir.",
        "Нечасто: может наблюдаться у менее 1 из 100, но более 1 из 1000 пациентов.",
        "Rare: may occur in less than 1 in 1000 but more than 1 in 10000 patients.",
        "frequency_mismatch",
    ),
    (
        "Karaciğer veya böbrek hastalığınız varsa doktorunuza danışınız.",
        "Храните при комнатной температуре в недоступном для детей месте.",
        "Store at room temperature out of the reach of children.",
        "concept_mismatch",
    ),
    (
        "Papiller nekroz (böbrek hasarı)",
        "Храните при температуре ниже 25°C. После открытия храните в холодильнике.",
        "Store below 25°C. After opening, store in the refrigerator.",
        "length_mismatch",
    ),
    (
        "Ateşli dönemde 30-50 mg/kg gün, günde 3-4 dozda ateş düşene kadar tedaviye devam edilir.",
        "В период лихорадки 30-50 мг/кг в день, лечение продолжают до снижения температуры.",
        "During fever 30-50 mg/kg per day, treatment continues until the fever subsides.",
        "number_mismatch",
    ),
])
def test_foreign_translation_of_paragraph_is_rejected(source, ru, en, problem):
    assert problem in item_problems(source, ru, en)
    assert problem in paragraph_problems(source, ru, en)


@pytest.mark.parametrize("source, ru, en", [
    ("5. VISCOTEARS'IN SAKLANMASI", "5. ХРАНЕНИЕ VISCOTEARS", "5. STORAGE OF VISCOTEARS"),
    # Разделители тысяч, «birinden» = «1 из».
    (
        "Seyrek: 1.000 hastanın birinden az görülebilir.",
        "Редко: может наблюдаться менее чем у 1 из 1000 пациентов.",
        "Rare: may occur in less than 1 in 1,000 patients.",
    ),
    (
        "Seyrek yan etkiler, bin hastanın en fazla birinde ancak on bin hastanın da en az birinde görülmektedir.",
        "Редкие побочные эффекты наблюдаются не более чем у одного из тысячи, но не менее чем у одного из "
        "десяти тысяч пациентов.",
        "Rare side effects occur in no more than 1 in 1,000 patients but at least 1 in 10,000 patients.",
    ),
    # Числа словами, римские, «her iki» = «оба», «İ.V.» → «IV», аббревиатура «TEN».
    (
        "Tip II diyabeti olan hastalarda tedaviye 3 ay devam edilir.",
        "У пациентов с диабетом 2 типа лечение продолжают три месяца.",
        "In patients with type II diabetes, treatment is continued for three months.",
    ),
    ("Damlayı her iki gözünüze uygulayınız.", "Закапайте капли в оба глаза.", "Apply the drops to both eyes."),
    ("İ.V. infüzyon için çözelti", "Раствор для внутривенной инфузии", "Solution for IV infusion"),
    (
        "Toksik epidermal nekroliz (TEN) gibi ciddi deri reaksiyonları",
        "Серьезные кожные реакции, такие как токсический эпидермальный некролиз (ТЭН)",
        "Serious skin reactions such as toxic epidermal necrolysis (TEN)",
    ),
    # Порядковые «1. günde» — не заголовок; «Yaygın akıntılı …(» — не метка частоты.
    (
        "1. günde normal toplam doz 0,75 ila 1,25 mg'dır.",
        "В 1-й день обычная общая доза составляет от 0,75 до 1,25 мг.",
        "On day 1, the usual total dose is 0.75 to 1.25 mg.",
    ),
    (
        "Yaygın akıntılı döküntüler (akut jeneralize ekzantematöz püstüloz)",
        "Распространенные высыпания (острый генерализованный экзантематозный пустулез)",
        "Widespread exudative rashes (acute generalized exanthematous pustulosis)",
    ),
    # Короткие термины: перевод заметно длиннее/короче — норма.
    ("Gaz", "Газообразование", "Gas"),
    ("Mide yangısı (gastrit)", "Воспаление желудка (гастрит)", "Gastritis"),
])
def test_correct_translation_passes_item_rules(source, ru, en):
    assert item_problems(source, ru, en) == []


def test_plain_numbers_normalize_separators_fractions_and_roman():
    assert plain_numbers("50.000 IU, 0,75 mg, 1 000 ml") == plain_numbers("50,000 IU, 0.75 mg, 1000 ml")
    assert plain_numbers("yaklaşık 1/2 bardak") == plain_numbers("примерно ½ стакана") == {"2"}
    assert plain_numbers("tip II") == {"2"} and plain_numbers("İ.V.") == frozenset()


def test_request_shift_finds_answer_shifted_after_skipped_item():
    ru, en = [row[1] for row in VISCOTEARS], [row[2] for row in VISCOTEARS]
    assert request_shift(SOURCES, ru, en) == set()

    shifted = request_shift(SOURCES, *_shifted_from(6))
    assert shifted == {6, 7, 8, 9}
    assert {3, 4, 5, 6, 7, 8, 9} <= request_shift(SOURCES, *_shifted_from(3))


def test_shifted_answer_rejects_whole_request():
    ru, en = _shifted_from(6)
    items = {str(index): source for index, source in enumerate(SOURCES, 1)}
    payload = {str(index): {"ru": r, "en": e} for index, (r, e) in enumerate(zip(ru, en), 1) if r}

    accepted, rejected = check_paragraph_payload(items, payload)

    assert accepted == {}
    assert all("shifted" in rejected[source] for source in SOURCES)


def test_answer_in_per_item_and_previous_format_is_accepted():
    items = {str(index): source for index, source in enumerate(SOURCES, 1)}
    per_item = {str(index): {"ru": ru, "en": en} for index, (_, ru, en) in enumerate(VISCOTEARS, 1)}
    previous = {  # пакеты Batch API, отправленные до перехода на {"1": {"ru", "en"}}
        "ru": {str(index): ru for index, (_, ru, _) in enumerate(VISCOTEARS, 1)},
        "en": {str(index): en for index, (_, _, en) in enumerate(VISCOTEARS, 1)},
    }

    accepted, rejected = check_paragraph_payload(items, per_item)

    assert check_paragraph_payload(items, previous) == (accepted, rejected)
    assert not any("shifted" in problems for problems in rejected.values())
    assert accepted[SOURCES[0]] == {"ru": VISCOTEARS[0][1], "en": VISCOTEARS[0][2]}


def test_audit_sequence_marks_shifted_chain_in_memory_order():
    ru, en = _shifted_from(3)
    rows = list(zip(SOURCES[:-1], ru[:-1], en[:-1]))  # последний абзац в память не попал (нет перевода)

    reasons = audit_sequence(rows)

    assert reasons[0] == []
    assert all("shifted" in row for row in reasons[3:])
    assert audit_sequence(VISCOTEARS) == [[] for _ in VISCOTEARS]


def _memory_with_shifted_chain():
    remember(PARAGRAPH_NAMESPACE, {source: {"ru": ru, "en": en} for source, ru, en in VISCOTEARS[:6]})
    ru, en = _shifted_from(6)
    remember(PARAGRAPH_NAMESPACE, {SOURCES[i]: {"ru": ru[i], "en": en[i]} for i in range(6, 9)})


@pytest.mark.django_db
def test_audit_dry_run_reports_without_changes(tmp_path):
    _memory_with_shifted_chain()
    out = StringIO()
    report = tmp_path / "report.jsonl"

    call_command("medicine_paragraph_audit", "--dry-run", "--report", str(report), stdout=out)

    assert "Записей medicine_paragraph: 9; подозрительных: 3" in out.getvalue()
    lines = [json.loads(line) for line in report.read_text(encoding="utf-8").splitlines()]
    assert {line["source_text"] for line in lines} == set(SOURCES[6:9])
    assert all("shifted" in line["reasons"] for line in lines)
    assert AITranslationMemory.objects.filter(namespace=PARAGRAPH_NAMESPACE).count() == 9


@pytest.mark.django_db
def test_audit_requires_backup_then_quarantines_and_loaddata_restores(tmp_path):
    _memory_with_shifted_chain()
    edited = AITranslationMemory.objects.get(source_text=SOURCES[8])
    AITranslationMemory.objects.filter(pk=edited.pk).update(updated_at=F("created_at") + timedelta(hours=1))
    backup = tmp_path / "backup.json"

    with pytest.raises(CommandError):
        call_command("medicine_paragraph_audit", stdout=StringIO())
    call_command("medicine_paragraph_audit", "--backup", str(backup), stdout=StringIO())

    assert lookup(PARAGRAPH_NAMESPACE, SOURCES[6:8]) == {}
    assert set(lookup(PARAGRAPH_NAMESPACE, SOURCES[:6])) == set(SOURCES[:6])
    # ручная правка в админке — источник правды, её аудит не трогает
    assert AITranslationMemory.objects.get(pk=edited.pk).namespace == PARAGRAPH_NAMESPACE
    assert set(
        AITranslationMemory.objects.filter(namespace=SUSPECT_NAMESPACE).values_list("source_text", flat=True)
    ) == set(SOURCES[6:8])
    saved = json.loads(backup.read_text(encoding="utf-8"))
    assert {row["fields"]["namespace"] for row in saved} == {PARAGRAPH_NAMESPACE}

    call_command("loaddata", str(backup), stdout=StringIO())

    assert set(lookup(PARAGRAPH_NAMESPACE, SOURCES[6:8])) == set(SOURCES[6:8])
    assert not AITranslationMemory.objects.filter(namespace=SUSPECT_NAMESPACE).exists()
