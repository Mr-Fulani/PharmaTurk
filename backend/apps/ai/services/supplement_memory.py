"""Память переводов БАДов: состав, способ применения, предупреждения, хранение.

Разделы страницы БАДа (``source_tabs``) у разных товаров повторяются не абзацами, а
частями: компоненты состава («Kolekalsiferol (D3 vitamini)», «Kapsül (sığır
jelatini)») и типовые фразы этикетки («Tavsiye edilen günlük porsiyonu aşmayın.»).
Замер на 372 карточках источника 05.11.2026: повторяется половина компонентов
состава. Поэтому единица памяти — компонент состава или одно предложение раздела,
namespace ``supplement_line``.

Код находит в разделах четыре блока (по подписям «Ürün Bileşimi:», «Kullanım
Şekli:», «Uyarılar:», «Muhafaza Koşulları:» и по типовым фразам без подписи),
берёт готовые переводы из памяти, а новые переводит модель короткими
нумерованными запросами с проверкой сдвига ответа — как абзацы инструкций
лекарств (``medicine_memory.translate_paragraphs``). Блок попадает в карточку,
только если переведены все его части.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from django.db.models import Q

from apps.ai.models import AITranslationMemory
from apps.ai.services import medicine_memory, supplement_glossary
from apps.ai.services.medicine_reference import fold_tr
from apps.ai.services.rules.memory import REUSABLE_LOG_STATUSES
from apps.ai.services.translation_memory import lookup, normalize_source_text, remember, source_hash

LINE_NAMESPACE = "supplement_line"
BLOCK_KINDS = ("composition", "excipients", "usage", "warnings", "storage")
BLOCK_TITLES = {
    "composition": ("Состав", "Ingredients"),
    "excipients": ("Вспомогательные вещества", "Other ingredients"),
    "usage": ("Способ применения", "How to use"),
    "warnings": ("Предупреждения", "Warnings"),
    "storage": ("Хранение", "Storage"),
}
UNIT_MAX_CHARS = 400
# Короткие части («Jelatin», «Gliserin», «Su») — по одной на запрос: перестановку соседних коротких строк
# проверка сдвига не ловит (ревью PR #313: «Jelatin» ↔ «Gliserin» принимались).
SHORT_UNIT_WORDS = 3

LINE_SYSTEM_PROMPT = (
    "Ты переводчик этикеток биологически активных добавок (БАД). Переводи с турецкого на русский "
    "и английский компоненты состава и строки этикетки: способ применения, предупреждения, условия "
    "хранения. Каждый элемент переводи полностью и отдельно: не сокращай, не пересказывай, не "
    "объединяй и ничего не добавляй. Сохраняй каждое число, единицу, процент и код пищевой добавки "
    "(E 551). Русский — естественный язык этикетки: «Tavsiye edilen günlük porsiyonu aşmayın» = "
    "«Не превышайте рекомендуемую суточную порцию», «Çocukların ulaşamayacağı yerde saklayın» = "
    "«Хранить в недоступном для детей месте». Вещества — принятыми названиями: «kolekalsiferol» = "
    "холекальциферол / cholecalciferol, «hacim arttırıcı» = наполнитель / bulking agent, «topaklanmayı "
    "önleyici» = антислёживающий агент / anti-caking agent, «takviye edici gıda» = БАД / food supplement, «kıvam arttırıcı» = загуститель / thickener, «nem verici» = влагоудерживающий агент / humectant, «sertleştirici» = "
    "уплотнитель / firming agent. "
    "«tok karnına» = «после еды» / «after a meal», «aç karnına» = «натощак» / «on an empty stomach». "
    "«Takviye edici gıdalar normal beslenmenin yerine geçemez» = «БАДы не заменяют полноценное питание» / "
    "«Food supplements are not a substitute for a varied diet». Единицы в русском — по-русски: мг, мкг, г, мл, МЕ, КОЕ («10 ml» = «10 мл»), проценты — «0,26 %». Турецкие и латинские дубли в скобках не переноси: «Menthol (mentol)» = «ментол», «bir-üç (1-3)» = «1–3». «11 yaş ve üzeri yetişkinler» = «взрослым и детям от 11 лет». Числа пиши цифрами, как в источнике («Günde 1 "
    "tablet» = «1 таблетка в день»). Латинские названия бактерий и растений (Lactobacillus acidophilus) оставляй "
    "латиницей; других английских слов в русском переводе нет. Ответ — строго JSON."
)

# Подписи разделов на странице БАДа (``fold_tr``, без двоеточия). Подпись другого
# раздела («Ürün Adı», «Özet Bilgi») закрывает текущий блок.
_LABELS = {
    "composition": (
        "urun bilesimi", "urun bilesenleri", "icerik", "icerigi", "icindekiler", "diger icerikler",
        "bilesenler", "bilesimi",
    ),
    "usage": (
        "kullanim sekli", "kullanim onerisi", "onerilen kullanim", "tavsiye edilen kullanim",
        "gunluk kullanim dozu", "kullanim talimati", "kullanim",
    ),
    "warnings": ("uyarilar", "uyari", "onemli uyarilar", "dikkat", "alerjen uyarisi"),
    "storage": ("muhafaza kosullari", "saklama kosullari", "muhafaza", "saklama"),
}
_LABEL_KIND = {label: kind for kind, labels in _LABELS.items() for label in labels}
_LABEL_RE = re.compile(r"^([^:]{2,40}?)\s*:\s*(.*)$")

# Типовые фразы без подписи («Takviye edici gıdalar normal beslenmenin yerine geçemez.»).
_STANDARD_WARNING_RE = re.compile(
    r"asma(?:yin|yiniz)|yerine gec|ulasamayacag|hamile|emzir|doktor|hekim|alerj|"
    r"kullanilmamal|tuketilmemeli|onerilmez"
)
# Без подписи фраза — предупреждение, только если она что-то велит или запрещает: «Hamilelik … ihtiyaç duyulan
# vitaminleri içerir», «Doktorlar tarafından önerilen formül» — описание, а не предупреждение (ревью PR #313).
_DIRECTIVE_RE = re.compile(r"asma(?:yin|yiniz)|yerine gec|ulasamayacag|danis|dikkat|onerilmez|icerebilir")
# «serin» — словом: «Fosfotidilserin» — вещество, а не «прохладное место».
_STANDARD_STORAGE_RE = re.compile(r"\bserin\b|\bkuru yer|muhafaza ed|sakla(?:yin|yiniz)|°c|gunes isig")
# То же, что «биологически активная добавка, не является лекарственным средством» дисклеймера
# карточки (DISCLAIMER).
_DISCLAIMER_DUPLICATE_RE = re.compile(
    r"ilac degil|hastaliklarin onlenmesi|tedavi edilmesi amaciyla|takviyesidir|takviye edici gidadir"
)
# Срок годности и номер партии на упаковке — не предупреждение («Tavsiye Edilen Tüketim Tarihinden (TETT)
# önce tüketiniz», «Parti No … kutunun alt yüzündedir»).
_PACKAGE_DATA_RE = re.compile(r"\btett\b|tuketim tarih|son kullanma|parti no|seri no|lot no|uretim tarih")
# Вспомогательные вещества: список из одних них (SOLGAR «İçindekiler: Kapsül (…), topaklanmayı önleyici (…)»,
# действующее вещество — в таблице доз) подписывается не «Состав».
_EXCIPIENT_RE = re.compile(
    r"^(?:kapsul|kaplama|hacim art|dolgu|topaklan|stabiliz|emulgat|jellest|tatlandir|aroma|koruyucu|renklendir|"
    r"kivam|nem verici|parlatici|asitlik duzenley|antioksidan|sigir jelatin|balik jelatin|jelatin|gliserin|"
    r"silikon dioksit|magnezyum stearat|mikrokristalin|hidroksipropil)"
    # Оболочка таблетки (NUTRAXIN, пилот 3).
    r"|selul|polietilen|polivinil|metakrilat|polioksietilen|yag asitlerinin|\btalk\b|izomalt|pancar koku"
)


def _is_excipient(folded: str) -> bool:
    # Название — до скобки: «L-Askorbik Asit (Vitomin C, Hacim Artırıcı Mikrokristalin Selüloz, …» — витамин.
    # Код E не признак: «Kalsiyum karbonat (E170)» в БАДе с кальцием и «Vitamin E 400 IU» — действующие вещества.
    return bool(_EXCIPIENT_RE.search(folded.split("(")[0]))


# Строка таблицы состава, а не компонент: «270 mg», «mg», «%76,00», «Her 10 ml için».
# «640 μg RE», «12 mg α-TE», «17,5 mg NE» — греческая «μ» и эквиваленты витаминов тоже единицы.
_UNIT_RE = re.compile(r"(?<![^\W\d_])(?:mg|mcg|[µμ]g|g|gr|ml|iu|ui|ie|kob|cfu|kcal|kj|re|ne|α-te|te)(?![^\W\d_])")
_QUANTITY_ONLY_RE = re.compile(r"[\d\s.,%/x×()*-]*")
_PORTION_HEADER_RE = re.compile(r"\bicin$")  # «Her 10 ml için», «2 tablet için»
# «* Kafein içerir» после точки — отдельная сноска-фраза (NUTRAXIN QUICK-SLIM 7423, пилот 3 на проде).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ0-9«\"(*])")
# Предложение блока «способ применения» — о приёме: доза, частота, возраст, как принимать. Описание
# действия («Hücresel enerjisi artan cilt hücreleri…») и реклама («kolay kullanım avantajı») — нет.
_USAGE_RE = re.compile(
    r"gunde|gunluk|\bkez\b|defa|tablet|kapsul|sase|damla|\bml\b|olcek|yemek|ogun|kahvalti|\bsu\b|"
    r"alin|alma|tuket|kullan|calkala|karistir|erit|yutul|puskurt|cigne|\byas|yetiskin|cocuk|porsiyon|\bdoz"
)
# «Pratik sprey formu sayesinde … kolayca tüketebilirsiniz», «Dünya’nın en çok tercih edilen …» — реклама;
# «Aşağıdaki örnek beslenme tablosunu …» — ссылка на таблицу, которой в карточке нет. «Aşağıdaki durumlarda
# kullanmayınız: …» — противопоказание, «Tabloda belirtilen günlük dozu aşmayınız» — предупреждение, их не трогать.
_DOSE_LIMIT_RE = re.compile(r"\d+\s*(?:kapsul|tablet|sase|olcek|damla|ml|pastil|puf)\w*\s+fazla")


def _dose_table_actives(sections: dict) -> list[str]:
    """Вещества таблицы доз — только между её заголовком («Her 3 Tablette», «%BRD», «Etken Madde») и следующей
    подписью: «Kafein» / «80 mg» или «Kafein 150 mg» в одной строке (NUTRAXIN QUICK-SLIM 7423)."""
    names = []
    for text in sections.values():
        lines = [fold_tr(line).strip() for line in str(text or "").split("\n") if line.strip()]
        in_table = False
        for line, following in zip(lines, [*lines[1:], ""]):
            if re.search(r"^her\b|%\s*brd|etken madde|\bmiktar|\bicin$", line):
                in_table = True
                continue
            if ":" in line or len(line.split()) > 12:
                in_table = False
            if not in_table or not re.search(r"[a-z]{3}", line) or _TABLE_HEADER_RE.search(line):
                continue
            inline = re.fullmatch(r"([^,]{3,80}?)\s+\d[\d.,]*\s*(?:mg|mcg|[µμ]g|g|iu|kob|cfu)\b.*", line)
            if inline:
                names.append(inline.group(1))
            elif following and _QUANTITY_ONLY_RE.fullmatch(_UNIT_RE.sub("", following)) and re.search(r"\d", following):
                names.append(line)
    return list(dict.fromkeys(names))


_DOSE_TR_RE = re.compile(r"\bgunde\b|\bdefa\b|\bkez\b|\d+\s*(?:kapsul|tablet|sase|olcek|damla|ml\b|pastil|puf)")
_ADVERT_RE = re.compile(r"avantaj|sayesinde|tercih edilen|sertifikali|ornek\b.*\btablo")
# Заявления о пользе («Yorgunluk ve bitkinliğin azalmasına katkıda bulunur», «… Sağlık Beyanları Yönetmeliği'ne
# göre») — БАДу на карточке нельзя (пилот 4: попали в способ применения). «Tedavi gören kişiler doktoruna
# danışarak kullanmalıdır» — предупреждение, «tedavi» здесь не признак.
_TR_CLAIM_RE = re.compile(r"katkida bulun|destekle|yardimci ol|guclendir|iyilestir|faydali|beyanlari")
# Страховка после перевода: обещание пользы в готовом блоке — блок не показывается целиком (не по предложению:
# неполный блок не должен выглядеть полным).
_RU_BENEFIT_RE = re.compile(r"способству|поддерживает|укрепля|улучша|помогает", re.IGNORECASE)
# Обещание лечения или профилактики в способе применения и составе («При лечении простуды — 2 таблетки в день»,
# «Для защиты иммунитета …», «Для снижения холестерина …», ревью PR #313). Узкий список, не ``_CLAIM_RE``
# карточки: «экстракт лечебной ромашки» — состав, а «заболевания» в предупреждениях законны, поэтому к
# предупреждениям и хранению не применяется.
_TREATMENT_KINDS = ("composition", "excipients", "usage")
_RU_TREATMENT_RE = re.compile(
    r"(?<![а-яё])(?:лечени|лечит|вылеч|излеч|профилакт|сниж|защит|защищ|предотвра|избав|укрепл)|"
    r"(?:при|от|для)\s+(?:\w+\s+)?(?:простуд|болезн|заболеван|грипп|кашл|инфекц|холестерин|давлени)",
    re.IGNORECASE,
)
_EN_TREATMENT_RE = re.compile(
    # Целыми словами: «Lactobacillus reuteri Protectis» — штамм, а не «protect».
    r"\b(?:treat(?:s|ed|ing|ment)?|cures?|prevent(?:s|ion|ing|ive)?|protect(?:s|ion|ing)?|lowers?|lowering|"
    r"reduc(?:e|es|ing|tion)|fight(?:s|ing)?|against)\b|\bfor\s+(?:\w+\s+)?(?:colds?|flu|diseases?|infections?)\b",
    re.IGNORECASE,
)


def memory_text_claim(text: str) -> bool:
    """Абзац блока памяти («Способ применения: …») с обещанием лечения — для модерации описания."""
    titles = {title for kind in _TREATMENT_KINDS for title in BLOCK_TITLES[kind]}
    title = text.split(":", 1)[0]
    return title in titles and bool(_RU_TREATMENT_RE.search(text) or _EN_TREATMENT_RE.search(text))


# Хранение — только о хранении; «Şeker, tuz, nişasta içermez», «Vegan … uygundur» после подписи — нет.
_STORAGE_TOPIC_RE = re.compile(_STANDARD_STORAGE_RE.pattern + r"|derece|isig|isik|\bnem|sicaklik|dondur|buzdolab|ambalaj")
# «… gibi potansiyel alerjenleri içermez», «… kullanılmamıştır» — не предупреждение, модель пересказывает это в
# описании (пилот 05.11.2026: одна фраза дважды); «… içerebilir» остаётся.
_FREE_FROM_RE = re.compile(r"icermez|kullanilmamistir")
# Экранированные символы, которые источник отдаёт текстом: «1u2019er tablet», «(600 u00b5g)».
_ESCAPED_CHAR_RE = re.compile(r"u(2019|2018|00b5|00b0)")
# Штаммы бактерий латиницей («Lactobacillus acidophilus- LA-5®», «Bifidobacterium- BB-12®») не переводятся.
_LATIN_STRAIN_RE = re.compile(
    r"^(?:lactobacillus|bifidobacterium|streptococcus|lactococcus|saccharomyces|bacillus|enterococcus|"
    r"pediococcus|leuconostoc|[lbs]\.)\b"
)
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{4,}")
# Единица — после числа: штаммы «GR-1», «ML-7» латиницей законны (ревью #327).
_RU_LATIN_UNIT_RE = re.compile(r"\d\s*(?:mg|mcg|[µμ]g|ml|iu|gr|kcal|cfu)(?![A-Za-z])", re.IGNORECASE)


def _skip_sentence(folded: str) -> bool:
    return bool(_DISCLAIMER_DUPLICATE_RE.search(folded) or _PACKAGE_DATA_RE.search(folded))


# Переворот смысла, который не ловят проверки чисел и сдвига (ревью PR #313): запрет переведён разрешением,
# «натощак» и «после еды», «младше» и «старше» перепутаны. Источник — после ``fold_tr``.
# Запрет: «kullanmamalıdır», «aşmayınız», «tüketilmemelidir», «önerilmez», «uygun değildir», «geçemez».
_PROHIBITION_RE = re.compile(r"\w(?:mamali|memeli|mayin|meyin)\w*")  # «kullanmamalıdır», «ısıtmayınız»
_NEGATION_RE = re.compile(_PROHIBITION_RE.pattern + r"|\b(?!pekmez)\w+(?:maz|mez)(?:lar|ler)?\b|\bdegil|onerilmez")
# Запрет в переводе — «не» при глаголе, а не при деепричастии: «могут применять, не превышая дозу» — разрешение
# (ревью PR #313); так же «not exceeding».
_RU_PROHIBITION_WORDS_RE = re.compile(r"нельзя|запрещ|противопоказ|избега|недопуст", re.IGNORECASE)
_RU_NOT_RE = re.compile(r"(?<![а-яё])не\s+([а-яё]+)", re.IGNORECASE)
_EN_PROHIBITION_WORDS_RE = re.compile(r"\b(?:no|never|avoid|cannot)\b|n't", re.IGNORECASE)
_EN_NOT_RE = re.compile(r"\bnot\s+(\w+)", re.IGNORECASE)


def _negated(ru: str, en: str) -> bool:
    ru_ok = _RU_PROHIBITION_WORDS_RE.search(ru) or any(
        not (word.endswith("я") and not word.endswith("ся")) for word in _RU_NOT_RE.findall(ru)
    )
    en_ok = _EN_PROHIBITION_WORDS_RE.search(en) or any(not word.endswith("ing") for word in _EN_NOT_RE.findall(en))
    return bool(ru_ok and en_ok)


_EMPTY_STOMACH_RE = re.compile(r"\bac\b.*karn")  # «aç karnına», «aç ya da tok karnına»
_FULL_STOMACH_RE = re.compile(r"\btok karn")
_AGE_UNDER_RE = re.compile(r"\byas\w*\s+(?:alti|altinda|kucuk)")  # «12 yaş altı», «15 yaşından küçüklerde»
_AGE_OVER_RE = re.compile(r"\byas\w*\s+(?:ve\s+)?(?:ustu|uzeri|ustundeki|buyuk)")  # «11 yaş ve üzeri»
_RU_UNDER_RE = re.compile(r"младше|моложе|(?<![а-яё])до\s+\d|менее|меньше|не достиг", re.IGNORECASE)
_EN_UNDER_RE = re.compile(r"\b(?:under|below|younger|less than)\b", re.IGNORECASE)
_RU_OVER_RE = re.compile(r"старше|(?<![а-яё])от\s+\d|и более|\d\s*\+", re.IGNORECASE)
_EN_OVER_RE = re.compile(r"\b(?:over|older|above|and up|or more)\b|\d\s*\+", re.IGNORECASE)


def _meaning_problems(folded_source: str, ru: str, en: str) -> list[str]:
    problems = []
    # «1 yaş ve üzeri yetişkinlerin» — опечатка «11»; «Взрослым и детям от 1 года» опасно (VIAPECIA 7524, пилот 3).
    if re.search(r"(?<![\d,.])[1-3]\s*yas\w*\s+(?:ve\s+)?(?:uzeri|ustu)\s+yetiskin", folded_source):
        problems.append("age_suspicious")
    if _NEGATION_RE.search(folded_source) and not _negated(ru, en):
        problems.append("negation_lost")
    empty, full = _EMPTY_STOMACH_RE.search(folded_source), _FULL_STOMACH_RE.search(folded_source)
    # «aç ya da tok karnına» — и натощак, и после еды.
    if empty and not full and not ("натощак" in ru.lower() and "empty stomach" in en.lower()):
        problems.append("meal_timing_mistranslated")
    # «tok karnına» — после еды, а модель писала «натощак» (пилот 3, дважды).
    if full and not empty and ("натощак" in ru.lower() or "empty stomach" in en.lower()):
        problems.append("meal_timing_mistranslated")
    under, over = _AGE_UNDER_RE.search(folded_source), _AGE_OVER_RE.search(folded_source)
    if under and not over and not (_RU_UNDER_RE.search(ru) and _EN_UNDER_RE.search(en)):
        problems.append("age_mistranslated")
    if over and not under and not (_RU_OVER_RE.search(ru) and _EN_OVER_RE.search(en)):
        problems.append("age_mistranslated")
    return problems


def line_problems(source: str, ru: str, en: str) -> list[str]:
    """Причины не принимать перевод части сверх проверок абзацев лекарств."""
    problems = []
    # Вещество словаря переведено иначе: «Rezene» — «укроп», «Mine Çiçeği» — «мята» (пилот 05.11.2026).
    missing = supplement_glossary.missing_terms(source, ru, en)
    # «hidroksipropil metil selülaz», «mikrokristalin selülaz» — опечатка источника в «selüloz» (целлюлоза),
    # а не фермент целлюлаза.
    if re.search(r"(?:metil|kristalin|propil|karboksi)\w*\s*selulaz", fold_tr(source)):
        missing = [term for term in missing if term != "selulaz"]
    if missing:
        problems.append("supplement_ingredient_mistranslated")
    # Английское слово в русском переводе, которого нет в источнике: «Приём docosahexaenoic acid».
    folded_source = fold_tr(source)
    # «Valeriana off icinalis» в источнике — «officinalis» в переводе верен.
    if any(fold_tr(word) not in folded_source.replace(" ", "") for word in _LATIN_WORD_RE.findall(ru)):
        problems.append("ru_latin_not_in_source")
    # Турецкое слово в переводе («Мелалойка Ягы (Melaloyka Yağı)») и подсказка словаря целиком («прополис | propolis»).
    # Бренд «METİLMAX» из источника остаётся как есть.
    turkish_words = re.findall(r"\w*[ğışçöüĞİŞÇÖÜ]\w*", ru)
    # Латинская единица в русском: «1 мерная ёмкость mg/5ml», «по 10 ml» (пилот 06.11.2026, IMUPLUS).
    # Турецкое слово источника в скобках: «Ментол (mentol)», «Камфора (kafur)»; слово и оно же в скобках:
    # «Тимол (тимол)»; турецкий процент «%0.0002»; непереведённый обрывок «in lin» (пилот 2 на проде, 06.11.2026).
    source_words = set(re.findall(r"[a-z]+", folded_source))
    bracketed_source_word = any(word.lower() in source_words for word in re.findall(r"\(([a-zçğışöü]+)\)", ru))
    if (
        any(word not in source for word in turkish_words) or ("|" in ru + en and "|" not in source)
        or _RU_LATIN_UNIT_RE.search(ru) or bracketed_source_word
        or re.search(r"(?i)\b([^\W\d_]+) \(\1\)", ru) or re.search(r"%\s?\d", ru)
        # «in lin», «ADI»; коды «Q10», «B6» как есть — верно.
        or (ru.strip().lower() == source.strip().lower() and all(len(w) <= 3 and w.isalpha() for w in source.split()))
    ):
        problems.append("ru_untranslated")
    # Диапазон дважды: «bir-üç (1-3)» → «1–3 (1-3) капсулы» (SOLGAR 7256).
    # Только то же число: «D3 (1)» — сноска, не повтор (ревью #328).
    if any(
        re.sub(r"\s|[–-]", "-", a) == re.sub(r"\s|[–-]", "-", b)
        # «Омега-3 (3)» — число в названии вещества, не диапазон.
        for a, b in re.findall(r"(?<![\w-])(\d+(?:\s*[–-]\s*\d+)?)\s*\(\s*(\d+(?:\s*[–-]\s*\d+)?)\s*\)", ru)
    ):
        problems.append("number_repeated")
    return problems + _meaning_problems(folded_source, ru, en)


@dataclass
class SupplementBlocks:
    """Блоки раздела: {вид: [исходные части]} и переводы готовых блоков."""

    parts: dict[str, list[str]] = field(default_factory=dict)
    ru: dict[str, list[str]] = field(default_factory=dict)
    en: dict[str, list[str]] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)


def _without_unclosed_brackets(text: str) -> str:
    """Скобки без пары: «[» → «: », «(» → пробел; парные не трогаются."""
    stack, unclosed = [], set()
    for index, char in enumerate(text):
        if char in "([":
            stack.append(index)
        elif char in ")]" and stack and text[stack[-1]] == {")": "(", "]": "["}[char]:
            stack.pop()
    unclosed.update(stack)
    out = []
    for index, char in enumerate(text):
        if index in unclosed:
            replacement = ": " if char == "[" else " "
            while out and out[-1] == " ":
                out.pop()
            out.append(replacement)
        else:
            out.append(char)
    return re.sub(r"(: |\s)\s+", r"\1", "".join(out))


def _split_top_level(text: str) -> list[str]:
    """Список состава → компоненты: запятая или точка с запятой вне скобок."""
    # Незакрытая скобка источника («Multivitamin ve Mineral Karışımı(%3,77) [Vitamin C(…), …» без «]») склеивала
    # остаток списка в одну часть длиннее UNIT_MAX_CHARS (пилот 06.11.2026, HERBALAND 7156). Убираем только её —
    # парные скобки остаются, и запятые внутри «(…, 10 mg)» список не дробят (ревью #327).
    text = _without_unclosed_brackets(text)
    items, depth, current = [], 0, []
    for index, char in enumerate(text):
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        # «1,3 - 1,6 Beta Glukan», «%0,91»: запятая между цифрами — десятичная.
        decimal = char == "," and text[index - 1 : index].isdigit() and text[index + 1 : index + 2].isdigit()
        if char in ",;" and depth == 0 and not decimal:
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    result = []
    for item in items:
        # Сноска, приклеенная к компоненту: «Kolekalsiferol. Formülasyonda kaplama maddesi olarak kullanılan
        # bileşenin ticari markasıdır» (PHARMATON 7265) — компонент без сноски.
        # Только после целого слова, вне скобок и если хвост — предложение со сказуемым («… markasıdır»):
        # «Bifidobacterium (B. Lactis BB-12) …», «Vit. C …», «Ekstr. Ginkgo …» — сокращения, «… konsantresi. Kapsül
        # kabuğu bileşenleri: sığır jelatini» — состав, не сноска (ревью #328).
        sentence_tail = re.search(r"[^\W\d_]{4,}\.\s+(?=[A-ZÇĞİÖŞÜ])", item)
        if (
            sentence_tail and len(item[sentence_tail.end():].split()) >= 4
            and item[:sentence_tail.start()].count("(") == item[:sentence_tail.start()].count(")")
            and re.search(r"(?:d[iu]r|t[iu]r)\W*$", fold_tr(item[sentence_tail.end():]))
        ):
            item = item[:sentence_tail.end()].rstrip().rstrip(".")
        item = item.strip(" .*")
        folded = fold_tr(item)
        # «FEROGLOBİN … İçeren Sıvı Takviye Edici Gıda - 200 ml» — название товара, а не компонент.
        if re.search(r"[^\W\d_]{2}", item) and not (
            _QUANTITY_ONLY_RE.fullmatch(_UNIT_RE.sub("", folded)) or _PORTION_HEADER_RE.search(folded)
            or _DISCLAIMER_DUPLICATE_RE.search(folded)
            or "takviye edici gida" in folded
            # Заголовок, а не компонент: «Aktif Bileşenler», «Bileşen», «Ürün Detayları», «2 Kapsülde».
            or re.fullmatch(r"(?:(?:aktif|yardimci) )?bilesen(?:ler)?|urun detaylari|\d+ \w+(?:de|da|te|ta)", folded)
            # Сводка через тире «Propolis - Karamürver - Melaloyka Yağı -- Su» (POREGE 7533) — заголовок, не компонент.
            or "--" in item or item.count(" - ") >= 2
            # «Adı», «Miktarı», «Her 1 tablette», «Her kapsülde», «Günlük Doz2 kapsül», «%BRD» (пилот 2 на проде).
            or re.fullmatch(r"adi|miktari?|her\s+(?:\d+\s*)?\w+|gunluk ?doz.*|%?\s*brd\W*|rda", folded)
        ):
            result.append(item)
    return result


def _split_dose_and_prohibition(sentence: str) -> list[str]:
    """«Günde 1 kapsül yemekle alınız, doktorunuza danışmadan daha fazla kullanmayınız.» → доза и запрет отдельно:
    доза остаётся в способе применения, запрет уходит в предупреждения (ревью #329)."""
    folded = fold_tr(sentence)
    if "," not in sentence or not (_DOSE_TR_RE.search(folded) and _PROHIBITION_RE.search(folded)):
        return [sentence]
    # Десятичная запятая «2,5 ml», «1,5 ölçek» — не граница части фразы (ревью #329).
    clauses = [clause.strip() for clause in re.split(r"(?<!\d),|,(?!\d)", sentence) if clause.strip()]
    first_prohibition = next(i for i, clause in enumerate(clauses) if _PROHIBITION_RE.search(fold_tr(clause)))
    dose = ", ".join(clauses[:first_prohibition])
    if not first_prohibition or not _DOSE_TR_RE.search(fold_tr(dose)):
        return [sentence]
    prohibition = ", ".join(clauses[first_prohibition:])
    return [dose.rstrip(" .") + ".", prohibition[:1].upper() + prohibition[1:]]


def _table_row(sentence: str) -> bool:
    """Строка таблицы, а не фраза: без точки, слова с заглавной, без кратности приёма — «4-11 Yaş Arası 1,11 ve
    Üzeri Çiğnenebilir Tablet» (VELAVIT KIDS 7511, пилот 3 на проде); «… 2×1 Kapsül, … 1×1 Kapsül» — кратность есть."""
    words = [word for word in re.findall(r"[^\W\d_]+", sentence) if len(word) > 2]
    if re.search(r"[.!]$", sentence.strip()) or len(words) < 3:
        return False
    if re.search(r"\bgunde\b|\bdefa\b|\bkez\b|\d\s*[x×]\s*\d|yemek|ogun|kahvalti|tercihen|sabah|aksam", fold_tr(sentence)):
        return False
    return sum(word[0].isupper() for word in words) / len(words) >= 0.6


def _sentences(text: str) -> list[str]:
    # «*** Takviye edici gıdalar …» — сноска источника; без звёздочек фраза совпадает с той же без сноски.
    return [part.strip().lstrip("* ") for part in _SENTENCE_SPLIT_RE.split(text) if re.search(r"[^\W\d_]{2}", part)]


def _label_kind(label: str) -> Optional[str]:
    """Подпись с двоеточием → вид блока: точная из словаря или по началу
    («Kullanım şekli ve Günlük alım dozu», «Ürün İçeriği (1 Stik Saşe)»)."""
    if label in _LABEL_KIND:
        return _LABEL_KIND[label]
    if label.startswith("kullanim") or "gunluk alim" in label or "gunluk kullanim" in label:
        return "usage"
    if label.startswith("uyari"):
        return "warnings"
    if "saklama" in label or "muhafaza" in label:
        return "storage"
    if "bilesim" in label or label.startswith(("icerik", "icindekiler", "urun icerigi")):
        return "composition"
    return None


def _label(line: str) -> tuple[Optional[str], str, bool]:
    """Строка → (вид блока или None, текст после подписи, это подпись)."""
    bare = fold_tr(line).strip(" *:")
    # Подпись без двоеточия («Muhafaza Koşulları») — только из двух слов и больше:
    # «İçerik» без двоеточия — заголовок столбца таблицы состава.
    if bare in _LABEL_KIND and " " in bare:
        return _LABEL_KIND[bare], "", True
    match = _LABEL_RE.match(line)
    if not match:
        return None, line, False
    kind = _label_kind(fold_tr(match.group(1)).strip(" *"))
    if kind:
        return kind, match.group(2).strip(), True
    # Подпись другого раздела («Ürün Adı:», «Menşe Ülke: Kanada») — короткая, без точки внутри и без глагола:
    # «Aşağıdaki durumlarda kullanmayınız: kalp hastalığı.» — противопоказание; текст после подписи
    # проверяется на типовые фразы.
    folded_label = fold_tr(match.group(1))
    if (
        len(match.group(1).split()) <= 5 and "." not in match.group(1)
        and not _PROHIBITION_RE.search(folded_label) and not re.search(r"(?:iniz|unuz)$", folded_label)
    ):
        return None, match.group(2).strip(), True
    return None, line, False


# Заголовок таблицы доз или пищевой ценности после списка состава: «Etken Madde», «Miktar / 10ml»,
# «%BRD», «1 Kapsül İçeriği», «Her bitkisel kapsülde», «Besin Enerjisi» — список закончился.
_TABLE_HEADER_RE = re.compile(
    r"miktar|etken madde|brd\b|\brda\b|besin|enerji|icerigi|bilesen adi|supplement facts|"
    r"^her\b|\bicin$|^bilesenler$|^icindekiler$|^\d+ \w+(?:de|da|te|ta)$|"
    # Столбцы таблицы «Adı / Miktarı», «Günlük Doz 2 kapsül» (пилот 2 на проде, 06.11.2026: 7257, 7242).
    r"^adi$|^miktari$|gunluk ?doz"
)
_LOWER_START_RE = re.compile(r"^[a-zçğıöşü]")
# Строка таблицы доз со столбцами «на пастилку / в день»: «Ginger ( Zencefil ) 5 Mg 15 Mg» (пилот 3).
_DOSE_ROW_RE = re.compile(r"\d\s*(?:mg|mcg|[µμ]g|g|iu|ml)\s+[\d.,]+\s*(?:mg|mcg|[µμ]g|g|iu|ml)$")
# «Saw Palmetto Meyve Ekstresi ..... 170 mg» — компонент и доза: доза уходит, компонент остаётся.
_DOTTED_AMOUNT_RE = re.compile(r"\s*\.{3,}.*$")
# Строка таблицы, а не способ применения: «30 Tablet» после подписи «Kullanım Şekli» без двоеточия.
_FORM_WORD_RE = re.compile(r"\b(?:tablet|kapsul|sase|adet|pastil|damla|puf)\w*")
# Характеристики в конце страницы: «Form» / «Kapsül» / «İçerik» / «Bakır B Vitaminleri C Vitamini …» —
# метки фильтров каталога, а не состав.
_ATTRIBUTE_LABELS = ("form", "icerik")


def _without_attribute_table(lines: list[str]) -> list[str]:
    end = len(lines)
    while end >= 2 and fold_tr(lines[end - 2]).strip() in _ATTRIBUTE_LABELS:
        end -= 2
    labels = {fold_tr(line).strip() for line in lines[end::2]}
    return lines[:end] if "form" in labels else lines


def section_parts(sections: dict[str, str]) -> dict[str, list[str]]:
    """Разделы источника → {вид блока: части по порядку, без повторов}."""
    return _section_parts(sections)[0]


def _section_parts(sections: dict[str, str]) -> tuple[dict[str, list[str]], dict[str, str]]:
    """→ (части блоков, {скрытый блок: причина}): «too_long» — часть длиннее UNIT_MAX_CHARS, «prose_list» — состав
    фразой («… içerir», «A, C, E»)."""
    parts: dict[str, list[str]] = {kind: [] for kind in BLOCK_KINDS}
    hidden: dict[str, str] = {}
    for text in sections.values():
        current: Optional[str] = None
        list_seen = False  # в составе уже была строка-список «A, B, C»
        composition_start = 0  # с какого компонента начался состав текущей подписи
        filled = False  # у текущей подписи уже есть текст
        open_part: Optional[tuple[str, int]] = None  # предложение без точки в конце — его продолжение ниже
        lines = [
            line for line in (
                normalize_source_text(_ESCAPED_CHAR_RE.sub(lambda m: chr(int(m.group(1), 16)), raw))
                for raw in str(text or "").split("\n")
            ) if line
        ]
        for line in _without_attribute_table(lines):
            # Фраза, разрезанная переносом: «Tavsiye edilen» / «günlük alım dozunu aşmayınız.»
            # «Hamile ve emziren kadınlar,» / «Doktora danışmadan kullanmamalıdır.» — продолжение после запятой
            # с заглавной буквы (ревью PR #313: на карточке был обрывок «…женщины,.»).
            if open_part and (
                _LOWER_START_RE.match(line) or (parts[open_part[0]][open_part[1]].endswith(",") and not _label(line)[2])
            ):
                kind, index = open_part
                joined = [
                    sentence for sentence in _sentences(f"{parts[kind][index]} {line}")
                    if not _skip_sentence(fold_tr(sentence))
                ]
                parts[kind][index:index + 1] = joined
                last = index + len(joined) - 1
                open_part = (kind, last) if joined and not re.search(r"[.!?;:]$", parts[kind][last]) else None
                continue
            open_part = None
            kind, rest, is_label = _label(line)
            if is_label:
                current, list_seen, filled = kind, False, False
                composition_start = len(parts["composition"])
                if not rest:
                    continue
                line = rest
            elif current == "composition":
                # Строка-количество («640 μg RE») — это таблица доз, а не список: состав этой подписи не берётся.
                line = _DOTTED_AMOUNT_RE.sub("", line)
                folded_line = fold_tr(line)
                if _QUANTITY_ONLY_RE.fullmatch(_UNIT_RE.sub("", folded_line)) or _DOSE_ROW_RE.search(folded_line):
                    del parts["composition"][composition_start:]
                    current = None
                # «İçerik Bilgisi:» и сразу фразы этикетки (PHARMATON, пилот 3): состава под подписью нет.
                elif any(regex.search(folded_line) for regex in (
                    _STANDARD_WARNING_RE, _STANDARD_STORAGE_RE, _DISCLAIMER_DUPLICATE_RE
                )):
                    current = None
                elif _TABLE_HEADER_RE.search(fold_tr(line)) or (list_seen and len(_split_top_level(line)) < 2):
                    current = None
            # Короткая строка без точки после текста способа применения или предупреждений — уже
            # таблица или заголовок («Form», «Tablet», «Raf Ömrü Bilgisi»): блок закончился.
            elif current is not None and filled and len(line.split()) < 4 and not re.search(r"[.!]$", line):
                current = None
            filled = True
            if current == "composition":
                # Вторая копия состава по-английски с ошибками распознавания («… B12 vitamini). INGREDIENTS:
                # Hydtrolyzed fsh collagen …», ZADE VITAL 7357) — не берётся, состав на ней заканчивается.
                english = re.search(r"\bingredients\s*:", line, re.IGNORECASE)
                if english:
                    line = line[:english.start()]
                # Состав фразой: «Koenzim Q10, E, B3, B5, B12 … Vitaminleri, Biotin ve Selenyum içerir» (DOPPELHERZ
                # 7300) — «E», «B3» отдельными частями бессмысленны, а без них состав неполный.
                pieces = [piece.strip(" .*") for piece in re.split(r"[,;]", line)]
                if re.search(r"\bicerir\W*$", fold_tr(line)) or any(re.fullmatch(r"[A-Za-z]\d{0,2}", p) for p in pieces):
                    del parts["composition"][composition_start:]
                    hidden["composition"] = "prose_list"
                    current = None
                    continue
                items = _split_top_level(line)
                if english:
                    current = None
                list_seen = list_seen or len(items) > 1
                parts["composition"].extend(items)
                continue
            sentences = _sentences(line)
            if current == "usage":
                sentences = [part for sentence in sentences for part in _split_dose_and_prohibition(sentence)]
            for sentence in sentences:
                folded = fold_tr(sentence)
                if _skip_sentence(folded) or sentence.endswith("?") or _TR_CLAIM_RE.search(folded):
                    continue
                target = current
                if target is None:
                    if _STANDARD_STORAGE_RE.search(folded) and not re.search(r"ulasamayacag", folded):
                        target = "storage"
                    elif (_STANDARD_WARNING_RE.search(folded) and _DIRECTIVE_RE.search(folded)) or _PROHIBITION_RE.search(
                        folded
                    ):
                        target = "warnings"
                if _ADVERT_RE.search(folded):
                    continue
                # Предупреждение под подписью способа применения («Tavsiye edilen günlük dozu aşmayınız», «… doktorunuza
                # danışınız») — в предупреждения (NUTRAFARM 7273: предупреждения внутри «Способа применения»).
                # Фраза с дозой или кратностью остаётся в применении: «Doktorunuza danışarak günde 2 kapsül alınız»
                # (ревью #328: блок «Способ применения» пропадал).
                # «Günde 2 kapsülden fazla kullanmayınız» — доза в запрете, это предупреждение (ревью #328); «fazla» не
                # после дозы («daha fazla», «3 aydan fazla») запрет делает только вместе со своей частью фразы (#329).
                if target == "usage" and (not _DOSE_TR_RE.search(folded) or _DOSE_LIMIT_RE.search(folded)) and (
                    (_STANDARD_WARNING_RE.search(folded) and _DIRECTIVE_RE.search(folded)) or _PROHIBITION_RE.search(folded)
                ):
                    target = "warnings"
                if target == "usage" and (
                    not _USAGE_RE.search(folded) or _QUANTITY_ONLY_RE.fullmatch(_FORM_WORD_RE.sub("", folded))
                    or _table_row(sentence)
                ):
                    continue
                if target in ("warnings", "storage") and _FREE_FROM_RE.search(folded):
                    continue
                if target == "storage" and not _STORAGE_TOPIC_RE.search(folded):
                    # «Tavsiye edilen günlük porsiyonu aşmayın» под подписью хранения — предупреждение.
                    if not _STANDARD_WARNING_RE.search(folded):
                        continue
                    target = "warnings"
                if target:
                    parts[target].append(sentence)
                    open_part = None if re.search(r"[.!?;:]$", sentence) else (target, len(parts[target]) - 1)
    # «Ürün Bileşimi» из вспомогательных веществ и одного действующего, а остальные действующие — в таблице доз
    # («Her 3 Tablette: Yeşil Çay …», NUTRAXIN QUICK-SLIM 7423): такой «Состав» вводит в заблуждение — не показываем.
    # Состав с одним действующим веществом («L askorbik asit» + вспомогательные) — полный, его не трогаем.
    composition = parts["composition"]
    excipient_share = sum(_is_excipient(fold_tr(item)) for item in composition) / len(composition) if composition else 0
    if 0.7 <= excipient_share < 1:
        actives = _dose_table_actives(sections)
        listed = fold_tr(" ".join(composition))
        covered = [name for name in actives if any(word in listed for word in name.split() if len(word) >= 4)]
        if len(actives) >= 2 and len(covered) < len(actives) / 2:
            parts["composition"] = []
            hidden["composition"] = "partial_list"
    if parts["composition"] and all(_is_excipient(fold_tr(item)) for item in parts["composition"]):
        parts["excipients"], parts["composition"] = parts["composition"], []
    # Блок с частью длиннее UNIT_MAX_CHARS не показывается: без неё он неполный, а выглядел бы полным.
    hidden.update({kind: "too_long" for kind, items in parts.items() if any(len(item) > UNIT_MAX_CHARS for item in items)})
    return {
        kind: list(dict.fromkeys(items)) for kind, items in parts.items()
        if items and hidden.get(kind) != "too_long"
    }, hidden


LINE_PROBLEMS = (
    "supplement_ingredient_mistranslated", "ru_latin_not_in_source", "ru_untranslated", "number_repeated", "negation_lost",
    "meal_timing_mistranslated", "age_mistranslated",
)
# Не ошибка перевода, а подозрительный источник: повтор перевода не поможет, нужен человек.
SOURCE_PROBLEMS = ("age_suspicious",)


def _translate(units: list[str], llm) -> tuple[dict, dict, dict]:
    """Перевод частей моделью с подсказками словаря и проверками ``line_problems``."""
    # Только вещества: у описательных слов варианты через «/» («кора / кожура») модель переносила в перевод.
    hints = {
        # Первый вариант: «фолиевая кислота / фолат» модель переносила в перевод целиком (пилот 3).
        # «ru | en» строкой модель копировала в перевод («прополис | propolis», пилот 4).
        key.upper(): {"ru": supplement_glossary.GLOSSARY[key][0].split(" / ")[0],
                      "en": supplement_glossary.GLOSSARY[key][1].split(" / ")[0]}
        for unit in units
        for key in supplement_glossary.found_terms(unit)
        if supplement_glossary.GLOSSARY[key][2] == supplement_glossary.S
    }
    system_prompt = LINE_SYSTEM_PROMPT + (
        f"\nСловарь — переводи эти слова только так: {json.dumps(hints, ensure_ascii=False)}" if hints else ""
    )
    requests = [[unit] for unit in units if len(unit.split()) <= SHORT_UNIT_WORDS]
    longer = [unit for unit in units if len(unit.split()) > SHORT_UNIT_WORDS]
    if longer:
        requests.append(longer)
    accepted: dict[str, dict[str, str]] = {}
    rejected: dict[str, list[str]] = {}
    usage: dict[str, Any] = {"tokens": {}, "cost_usd": 0.0, "processing_time_ms": 0}
    for request in requests:
        request_accepted, request_rejected, request_usage = medicine_memory.translate_paragraphs(
            request, llm, system_prompt=system_prompt
        )
        accepted.update(request_accepted)
        rejected.update(request_rejected)
        medicine_memory._add_usage(usage, request_usage)
    for unit, values in list(accepted.items()):
        problems = line_problems(unit, values["ru"], values["en"])
        if problems:
            rejected[unit] = problems
            del accepted[unit]
    return accepted, rejected, usage


def _remember(accepted: dict[str, dict[str, str]], log, replace: frozenset = frozenset()) -> None:
    """Запись с логом карточки: отклонённый модератором лог снимает её из повторного использования.

    ``replace`` — части, чья автоматическая запись в памяти не прошла ``line_problems``: свежий перевод её заменяет.
    """
    remember(LINE_NAMESPACE, accepted, log=log)
    # Запись карточки, которую модератор не принял, уступает свежему переводу (как ``rules.memory.remember``).
    stale = AITranslationMemory.objects.filter(
        namespace=LINE_NAMESPACE,
        source_hash__in=[source_hash(normalize_source_text(unit)) for unit in accepted],
        source_log__isnull=False,
    ).exclude(
        Q(source_log__status__in=REUSABLE_LOG_STATUSES)
        & ~Q(source_hash__in=[source_hash(normalize_source_text(unit)) for unit in replace])
    )
    if log is not None:
        stale = stale.exclude(source_log=log)
    by_hash = {source_hash(normalize_source_text(unit)): values for unit, values in accepted.items()}
    for entry in stale:
        values = by_hash[entry.source_hash]
        entry.ru_text, entry.en_text, entry.source_log = values["ru"], values["en"], log
        entry.save(update_fields=["ru_text", "en_text", "source_log"])


# Оборванная фраза («Hamile ve emziren kadınlar,»): блок с ней не показывается, лучше без блока, чем неполный.
_FRAGMENT_RE = re.compile(r"(?:,|\b(?:ve|veya|ile|ya da))$")


def translate_blocks(sections: dict[str, str], llm, log=None) -> tuple[SupplementBlocks, dict[str, Any]]:
    """Части блоков — из памяти, новые — моделью; блок готов, если переведены все его части.

    → (блоки, usage запросов перевода). ``llm=None`` — только память. Из памяти берутся записи принятых
    карточек и ручные правки; ``log`` — лог карточки, с ним сохраняются новые переводы.
    """
    parts, hidden = _section_parts(sections)
    blocks = SupplementBlocks(parts=parts)
    units = list(dict.fromkeys(unit for items in blocks.parts.values() for unit in items))
    fragments = [unit for unit in units if _FRAGMENT_RE.search(fold_tr(unit))]
    units = [unit for unit in units if unit not in fragments]
    found = {unit: {"ru": unit, "en": unit} for unit in units if _LATIN_STRAIN_RE.match(fold_tr(unit))}
    if units:
        found.update(lookup(
            LINE_NAMESPACE, [unit for unit in units if unit not in found], log_statuses=REUSABLE_LOG_STATUSES
        ))
    # Готовые переводы проходят те же проверки, что и новые (ревью #327: «mg/5ml», «сафлор» из памяти прода
    # иначе снова попадали на карточки). Ручная правка (без лога) — источник правды, её не проверяем.
    bad_memory = {
        unit: problems for unit in found if not _LATIN_STRAIN_RE.match(fold_tr(unit))
        for problems in [line_problems(unit, found[unit]["ru"], found[unit]["en"])] if problems
    }
    if bad_memory:
        manual = set(AITranslationMemory.objects.filter(
            namespace=LINE_NAMESPACE, source_log__isnull=True,
            source_hash__in=[source_hash(normalize_source_text(unit)) for unit in bad_memory],
        ).values_list("source_hash", flat=True))
        bad_memory = {
            unit: problems for unit, problems in bad_memory.items()
            if source_hash(normalize_source_text(unit)) not in manual
        }
        for unit in bad_memory:
            del found[unit]
    cached = len(found)
    missing = [unit for unit in units if unit not in found]
    usage: dict[str, Any] = {"tokens": {}, "cost_usd": 0.0, "processing_time_ms": 0}
    rejected: dict[str, list[str]] = {}
    if missing and llm is not None:
        accepted, rejected, usage = _translate(missing, llm)
        # Отказ своих проверок — один повтор: в пилоте 05.11.2026 модель вернула английский вместо русского
        # сразу для 10 компонентов одного запроса.
        retry = [unit for unit, reasons in rejected.items() if set(reasons) & set(LINE_PROBLEMS)]
        if retry:
            accepted_again, rejected_again, usage_again = _translate(retry, llm)
            accepted.update(accepted_again)
            rejected = {unit: reasons for unit, reasons in {**rejected, **rejected_again}.items() if unit not in accepted}
            medicine_memory._add_usage(usage, usage_again)
        if accepted:
            _remember(accepted, log, replace=frozenset(bad_memory))
            found.update(accepted)
    claims = []
    for kind, items in blocks.parts.items():
        if any(
            item in found and (
                _RU_BENEFIT_RE.search(found[item]["ru"])
                or (kind in _TREATMENT_KINDS and _RU_TREATMENT_RE.search(found[item]["ru"]))
            )
            for item in items
        ):
            claims.append(kind)
            continue
        if all(item in found for item in items):
            blocks.ru[kind] = [found[item]["ru"] for item in items]
            blocks.en[kind] = [found[item]["en"] for item in items]
    blocks.stats = {
        "units": len(units),
        "cached": cached,
        "translated": len([unit for unit in missing if unit in found]),
        "rejected": {unit[:120]: reasons for unit, reasons in rejected.items()},
        "missing": len([unit for unit in units if unit not in found]),
        "fragments": [unit[:120] for unit in fragments],
        "memory_rejected": {unit[:120]: problems for unit, problems in bad_memory.items()},
        "too_long_blocks": [kind for kind, reason in hidden.items() if reason == "too_long"],
        "hidden_blocks": hidden,
        "claim_blocks": claims,
        "blocks": sorted(blocks.ru),
        "incomplete_blocks": sorted(set(blocks.parts) - set(blocks.ru)),
    }
    return blocks, usage
