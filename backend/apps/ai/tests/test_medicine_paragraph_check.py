"""Сдвинутые переводы абзацев инструкций: правила без LLM и аудит памяти.

Примеры — записи памяти medicine_paragraph с прода (20.10.2026).
"""

import json
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import F

from apps.ai.management.commands.medicine_paragraph_audit import SUSPECT_NAMESPACE
from apps.ai.models import AITranslationMemory
from apps.ai.services.medicine_fact_check import doses_match
from apps.ai.services.medicine_memory import (
    PARAGRAPH_NAMESPACE,
    check_paragraph_payload,
    paragraph_problems,
    section_paragraph_problems,
)
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


# Верные переводы из части №3 пакета (22.10.2026), которые правила отклоняли.
PART3_FALSE_REJECTS = [
    pytest.param(
        '600-1500 I.U./gün',
        '600-1500 МЕ/день',
        '600-1500 I.U./day',
        id='I.U. = МЕ = IU',
    ),
    pytest.param(
        "* Gerektiğinde 1.000 I.U.'ye kadar çıkılabilir.",
        '* При необходимости можно увеличить до 1000 МЕ.',
        '* If necessary, it can be increased up to 1,000 I.U.',
        id='1.000 I.U. = 1000 МЕ = 1,000 I.U.',
    ),
    pytest.param(
        "Başlangıç dozu nemli inhalasyon yoluyla 2,5'mg'dır. Doz 5 mg'a kadar çıkarılabilir. Tedavi günde 4 kez tekrarlanabilir.",
        'Начальная доза при ингаляции составляет 2,5 мг. Дозу можно увеличить до 5 мг. Лечение можно повторять 4 раза в день.',
        'The starting dose via inhalation is 2.5 mg. The dose can be increased up to 5 mg. Treatment can be repeated 4 times a day.',
        id="2,5'mg — апостроф между числом и единицей",
    ),
    pytest.param(
        "{BRAND} her ml'sinde 23 mg'dan daha az sodyum ihtiva eder. Sodyuma bağlı herhangi bir olumsuz etki beklenmez.",
        '{BRAND} содержит менее 23 мг натрия на 1 мл. Ожидается, что негативных эффектов, связанных с натрием, не будет.',
        '{BRAND} contains less than 23 mg of sodium per ml. No adverse effects related to sodium are expected.',
        id='«на 1 мл» — знаменатель, а не доза',
    ),
    pytest.param(
        '{BRAND}, 20 gramlık tüplerde sunulan beyaz renkli bir kremdir.',
        '{BRAND} — это белый крем, который поставляется в тюбиках по 20 граммов.',
        '{BRAND} is a white cream available in 20-gram tubes.',
        id='20 gramlık = 20 граммов = 20-gram',
    ),
    pytest.param(
        '{BRAND} 1 g merhemde 1 miligram triamsinolon asetonid içeren, 5 gramlık alüminyum tüplerde kullanıma sunulmaktadır.',
        '{BRAND} выпускается в алюминиевых тюбиках по 5 граммов, содержащих 1 миллиграмм триамцинолона ацетонида в 1 грамме мази.',
        '{BRAND} is available in 5-gram aluminum tubes containing 1 milligram of triamcinolone acetonide in 1 gram of ointment.',
        id='1 miligram = 1 мг, «в 1 г мази» — знаменатель',
    ),
    pytest.param(
        "2. aydan sonra, aşı sonrası ateş görülen bebeklere 2,5 ml (yarım ölçek)'lik bir doz uygundur.. İki ayın altındaki bebeklerde kullanılmamalıdır.",
        'После 2-го месяца для детей с температурой после вакцинации рекомендуется доза 2,5 мл (половина мерной ложки). Не следует использовать у детей младше двух месяцев.',
        'After the 2nd month, a dose of 2.5 ml (half a scoop) is recommended for infants with fever after vaccination. It should not be used in infants under two months.',
        id='«2. aydan sonra» — «после 2-го месяца», а не раздел 2',
    ),
    pytest.param(
        '6Amoksisilin/klavulanik asit alan hastalarda protrombin zamanında uzama nadiren bildirilmiştir. Antikoagülanlar ile birlikte reçete edildiğinde uygun şekilde izlenmesi gereklidir. İstenilen antikoagülasyon düzeyini sürdürebilmek için oral antikoagülan dozunda ayarlama yapılması gerekebilir.',
        'У пациентов, принимающих {BRAND}, редко сообщалось о продлении протромбинового времени. При назначении вместе с антикоагулянтами необходимо соответствующее наблюдение. Для поддержания желаемого уровня антикоагуляции может потребоваться корректировка дозы перорального антикоагулянта.',
        'In patients receiving {BRAND}, prolongation of prothrombin time has been rarely reported. When prescribed together with anticoagulants, appropriate monitoring is required. Dose adjustment of oral anticoagulants may be necessary to maintain the desired level of anticoagulation.',
        id='сноска «6Amoksisilin»',
    ),
    pytest.param(
        'Kasılma, nöbet ya da çırpınma8 (konvülsiyon) (yüksek dozda AUGMENTİN ES alan hastalarda veya böbrek sorunları olan hastalarda görülebilir)',
        'Судороги, припадки или подергивания (конвульсии) могут наблюдаться у пациентов, принимающих высокие дозы AUGMENTIN ES или имеющих проблемы с почками.',
        'Convulsions, seizures, or twitching (convulsions) may be observed in patients receiving high doses of AUGMENTIN ES or those with kidney issues.',
        id='сноска «çırpınma8»',
    ),
    pytest.param(
        "Hamileliğinizin ilk veya son 3 aylık döneminde iseniz {BRAND}'i kullanmayınız.",
        'Если вы находитесь на первом или последнем триместре беременности, не используйте {BRAND}.',
        'If you are in the first or last trimester of pregnancy, do not use {BRAND}.',
        id='«3 aylık dönem» = «триместр»',
    ),
    pytest.param(
        'Yetmiş beş yaşın üzerinde iseniz ve size STEMI olarak adlandırılan tipte bir miyokard infarktüsü (STEMI) teşhisi konulursa tedavinin başlangıcında size damar içine tek seferde ilaç verilmesi önerilmemektedir.',
        'Если вам больше 75 лет и вам поставлен диагноз инфаркта миокарда типа STEMI, вам не рекомендуется вводить препарат внутривенно в начале лечения.',
        'If you are over 75 years old and diagnosed with a type of myocardial infarction called STEMI, it is not recommended to administer the drug intravenously at the beginning of treatment.',
        id='«Yetmiş beş yaş» = 75',
    ),
    pytest.param(
        'Ondört yaş ve üzeri ergenler ve erişkinlerde kireçlenme (osteoartrit), eklemlerde ağrı ve şekil bozukluğu (romatoid artrit) ve sırt, boyun ve göğüs kafesi eklemlerinde sertleşme ile seyreden ağrılı ilerleyici romatizma (ankilozan spondilit) belirti ve bulgularının tedavisi ile akut guta bağlı eklem iltihabı (akut gut artrit), akut kas-iskelet sistemi ağrıları, ameliyattan sonraki ağrı (postoperatif ağrı) ve ağrılı adet görme (dismenore) tedavisinde endikedir.',
        'Показан для лечения симптомов и признаков остеоартрита, боли в суставах и деформации (ревматоидный артрит), а также болезненной прогрессирующей ревматической болезни с жесткостью в суставах спины, шеи и грудной клетки (анкилозирующий спондилит), острого артрита, связанного с подагрой (острый подагрический артрит), острых болей в опорно-двигательном аппарате, послеоперационной боли и болезненных менструаций (дисменорея) у подростков старше 14 лет и взрослых.',
        'Indicated for the treatment of symptoms and signs of osteoarthritis, joint pain and deformity (rheumatoid arthritis), and painful progressive rheumatism with stiffness in the joints of the back, neck, and chest (ankylosing spondylitis), acute gout-related joint inflammation (acute gout arthritis), acute musculoskeletal pain, postoperative pain, and painful menstruation (dysmenorrhea) in adolescents over 14 years and adults.',
        id='«Ondört yaş» = 14',
    ),
    pytest.param(
        "30 kg'dan hafif çocuklarda önerilen toplam dozaj 2,3 veya 4 doza bölünmüş olarak (her 12, 8 veya 6 saatte bir) 50 mg/kg/gün'dür. 30 kg ve üstündeki çocuklar için günlük doz yetişkin dozuyla aynıdır (her 12 saatte 375-750 mg).",
        'Рекомендуемая общая доза для детей весом менее 30 кг составляет 50 мг/кг/день, разделенная на 2, 3 или 4 дозы (каждые 12, 8 или 6 часов). Для детей весом 30 кг и более суточная доза такая же, как у взрослых (375-750 мг каждые 12 часов).',
        'The recommended total dosage for children weighing less than 30 kg is 50 mg/kg/day, divided into 2, 3, or 4 doses (every 12, 8, or 6 hours). For children weighing 30 kg and above, the daily dose is the same as the adult dose (375-750 mg every 12 hours).',
        id='«2,3 veya 4 doza» — перечисление',
    ),
    pytest.param(
        'İdrar söktürücü ilaçlar (diüretikler)',
        'Диуретики (мочегонные препараты)',
        'Diuretics',
        id='короткий абзац: «Diuretics»',
    ),
    pytest.param(
        'Doktorunuz tarafından başka bir şekilde tavsiye edilmediği takdirde',
        'Если врач не назначил иначе',
        'Unless otherwise advised by your doctor',
        id='короткий абзац: «Если врач не назначил иначе»',
    ),
    pytest.param(
        "5. MADDECASSOL'ÜN SAKLANMASI",
        '5. ХРАНЕНИЕ {BRAND}',
        '5. STORAGE OF {BRAND}',
        id='модель сама заменила бренд меткой',
    ),
    pytest.param(
        'www.titck.gov.tr/" sitesinde',
        'на сайте www.titck.gov.tr/',
        'at www.titck.gov.tr/',
        id='адрес сайта не переводится',
    ),
    pytest.param(
        'Kullanma Talimatında yer alan veya almayan herhangi bir yan etki meydana gelmesi durumunda hekiminiz, eczacınız veya hemşireniz ile konuşunuz. Ayrıca karşılaştığınız yan etkileri www.titck.gov.tr adresinde yer alan "İlaç Yan Etki Bildirimi" ikonuna tıklayarak ya da 0 800 314 00 08 numaralı yan etki bildirim hattını arayarak Türkiye Farmakovijilans Merkezi (TÜFAM)\'ne bildiriniz. Meydana gelen yan etkileri bildirerek kullanmakta olduğunuz ilacın güvenliliği hakkında daha fazla bilgi edinilmesine katkı sağlamış olacaksınız..',
        'Если возникнут какие-либо побочные эффекты, указанные или не указанные в инструкции по применению, поговорите с вашим врачом, фармацевтом или медсестрой. Также сообщите о возникших побочных эффектах, нажав на иконку "Сообщение о побочных эффектах" на сайте www.titck.gov.tr или позвонив на горячую линию по сообщениям о побочных эффектах по номеру 0 800 314 00 08 в Турецкий центр фармаконадзора (ТÜFAM). Сообщая о возникших побочных эффектах, вы способствуете получению дополнительной информации о безопасности используемого вами препарата.',
        'If any side effects occur, whether listed or not in the instructions for use, talk to your doctor, pharmacist, or nurse. Also report the side effects you encounter by clicking on the "Drug Side Effect Reporting" icon on the website www.titck.gov.tr or by calling the side effect reporting hotline at 0 800 314 00 08 to the Turkish Pharmacovigilance Center (TÜFAM). By reporting the side effects that occur, you will contribute to obtaining more information about the safety of the medication you are using.',
        id='аббревиатура «ТÜFAM» с кириллической «Т»',
    ),
    pytest.param(
        'Geçmişteki veya mevcut bacaklarda (derin ven trombozu) ya da akciğerde (akciğer embolisi) damarda kanın pıhtılaşması (tromboz),',
        'Тромбоз в венах ног (глубокий венозный тромбоз) или легких (легочная эмболия) в прошлом или в настоящее время.',
        'History or current thrombosis in the legs (deep vein thrombosis) or in the lungs (pulmonary embolism).',
        id='«derin ven» — «глубокий», не «кожа»; «тромбоз» — про кровь',
    ),
    pytest.param(
        'HİV (insan immün yetmezlik virüsü ) ilaçları (nevirapin, efavirenz, ritonavir ve nelfinavir gibi),',
        'Препараты для лечения ВИЧ (такие как невирапин, эфавиренз, ритонавир и нельфинавир).',
        'HIV (human immunodeficiency virus) medications (such as nevirapine, efavirenz, ritonavir, and nelfinavir).',
        id='«ВИЧ» = вирус иммунодефицита',
    ),
    pytest.param(
        'Açık alev, yanan sigara veya bazı cihazların (örneğin saç kurutma makineleri) yakınında kullanılmamalıdır.',
        'Не следует использовать вблизи открытого огня, горящей сигареты или некоторых устройств (например, фенов).',
        'Should not be used near open flames, burning cigarettes, or certain devices (e.g., hair dryers).',
        id='«saç kurutma makineleri» — фены, не управление машинами',
    ),
    pytest.param(
        'Uykululuk hali, hafif sersemlikten derin uykuya kadar değişen sedasyon',
        'Сонливость, варьирующая от легкой затуманенности до глубокого сна.',
        'Drowsiness ranging from mild dizziness to deep sleep.',
        id='«derin uyku» — «глубокий сон»',
    ),
]


@pytest.mark.parametrize("source, ru, en", PART3_FALSE_REJECTS)
def test_correct_translation_from_part3_passes_paragraph_rules(source, ru, en):
    assert paragraph_problems(source, ru, en) == []


# Настоящий брак из той же части — отклоняется по-прежнему.
@pytest.mark.parametrize("source, ru, en, problem", [
    pytest.param(
        '12 yaşından büyük çocuklarda ve yetişkinlerde günde 3-4 kez 1-2 ölçek kullanılır.',
        'У детей старше 12 лет и взрослых используется по 1-2 мерной ложке 3-4 раза в день.',
        '12 yaşından büyük çocuklarda ve yetişkinlerde günde 3-4 kez 1-2 ölçek kullanılır.',
        'concept_mismatch',
        id='EN остался турецким',
    ),
    pytest.param(
        '{BRAND} selektif beta',
        '{BRAND} является членом группы препаратов, называемых селективными бета-адренергическими рецепторными агонистами.',
        '{BRAND} is a member of a group of drugs called selective beta-adrenergic receptor agonists.',
        'length_mismatch',
        id='обрывок, модель досочинила фразу',
    ),
    pytest.param(
        'Emzirme sırasında {BRAND} kullanılabilir.. D3 vitamini anne sütüne geçer. Emzirilen çocuğa ilave D vitamini alımı bu durumda göz önünde bulundurulmalıdır.',
        'Во время грудного вскармливания {BRAND} может быть использован. Витамин D проникает в грудное молоко. В этом случае следует учитывать дополнительный прием витамина D для грудного ребенка.',
        '{BRAND} can be used during breastfeeding. Vitamin D passes into breast milk. Additional vitamin D intake for the breastfed child should be considered in this case.',
        'number_mismatch',
        id='«D3 vitamini» → «витамин D»',
    ),
])
def test_real_defect_from_part3_is_still_rejected(source, ru, en, problem):
    assert problem in paragraph_problems(source, ru, en)


def test_doses_match_unit_spellings_separators_and_per_unit_denominator():
    assert doses_match("600-1500 I.U./gün", "600-1500 МЕ/день") and doses_match("4000I.U./gün", "4000 IU/day")
    assert doses_match("Gerektiğinde 1.000 I.U.'ye kadar", "до 1000 МЕ") and doses_match("1 000 I.U'yu aşan", "over 1,000 IU")
    assert doses_match("Başlangıç dozu 2,5'mg'dır.", "Начальная доза 2,5 мг.")
    assert doses_match("her ml'sinde 23 mg", "23 мг на 1 мл")
    assert doses_match("1 g merhemde 1 miligram", "1 мг в 1 г мази") and doses_match("100 mikrog/mL", "100 мкг/мл")
    assert doses_match("200 mikrogram ivermektin", "200 микрограммов ивермектина на 1 кг массы тела")
    assert not doses_match("1.000 I.U.", "100 МЕ")
    assert not doses_match("her ml'sinde 23 mg", "32 мг на 1 мл")
    assert not doses_match("200 mikrogram", "20 микрограммов")
    assert not doses_match("günde 2 g", "2 мг в день")


def test_lost_step_number_is_restored_not_rejected():
    source = "3. Kalan suyu (1/3) şişe üzerindeki sulandırma çizgisine kadar doldurunuz ve şişeyi yeniden çalkalayınız."
    ru = "Долейте оставшуюся воду (1/3) до линии разведения на флаконе и снова встряхните флакон."
    en = "Fill the remaining water (1/3) up to the dilution line on the bottle and shake the bottle again."

    accepted, rejected = check_paragraph_payload({"1": source}, {"1": {"ru": ru, "en": en}})

    assert rejected == {}
    assert accepted[source] == {"ru": f"3. {ru}", "en": f"3. {en}"}
    # Другое число в начале перевода — не пропуск номера, а расхождение.
    _, rejected = check_paragraph_payload({"1": source}, {"1": {"ru": f"4. {ru}", "en": f"4. {en}"}})
    assert "heading_mismatch" in rejected[source]
    # Ссылка на раздел: номер в переводе есть, ставить его ещё раз в начало не нужно.
    reference = "3. Bölüm"
    accepted, _ = check_paragraph_payload({"1": reference}, {"1": {"ru": "См. раздел 3", "en": "See section 3"}})
    assert reference not in accepted


def test_numbers_in_words_lists_and_footnotes_are_not_a_mismatch():
    assert item_problems(
        "Hamileliğinizin ilk veya son 3 aylık döneminde iseniz",
        "Если вы находитесь в первом или последнем триместре беременности",
        "If you are in the first or last trimester of pregnancy",
    ) == []
    assert item_problems("Toplam doz 2,3 veya 4 doza bölünür.", "Общая доза делится на 2, 3 или 4 приёма.",
                         "The total dose is divided into 2, 3 or 4 doses.") == []
    assert "number_mismatch" in item_problems("Toplam doz 2,3 veya 4 doza bölünür.", "Общая доза делится на 2 или 4 приёма.",
                                              "The total dose is divided into 2 or 4 doses.")
    footnote = "6Amoksisilin alan hastalarda protrombin zamanında uzama nadiren bildirilmiştir."
    assert item_problems(footnote, "У пациентов, принимающих амоксициллин, редко сообщалось об удлинении протромбинового времени.",
                         "Prolonged prothrombin time has rarely been reported in patients taking amoxicillin.") == []
    assert item_problems(footnote, "6 У пациентов, принимающих амоксициллин, редко сообщалось об удлинении протромбинового времени.",
                         "6 Prolonged prothrombin time has rarely been reported in patients taking amoxicillin.") == []


def test_glued_units_numbers_and_footnotes_inside_words_are_not_a_mismatch():
    # Пробел потерян исходником на границе тега.
    assert doses_match("sulandırıldığında 70 mLve 100 mL süspansiyon", "после разведения 70 мл и 100 мл суспензии")
    assert doses_match("PREDNOL-L20mginek sütü proteinleri içermektedir.", "PREDNOL-L 20 мг содержит белки молока.")
    assert doses_match("Önerilen doz VORELBAN15mg'dır.", "Рекомендуемая доза — VORELBAN 15 мг.")
    # «2x5 mg» — множитель, «1 gün» — не «1 g ün».
    assert doses_match("10 mg (2x5mg)", "10 мг (2x5 мг)") and doses_match("1 gün", "1 день")
    assert not doses_match("sulandırıldığında 70 mLve 100 mL süspansiyon", "после разведения 7 мл и 100 мл суспензии")
    assert item_problems(
        "Yüksek tansiyonda kullanılan anjiyotensin IIantagonistleri",
        "Антагонисты ангиотензина II, применяемые при высоком давлении",
        "Angiotensin II antagonists used for high blood pressure",
    ) == []
    assert item_problems(
        "{BRAND}'i ne kadar sür8eyle kullanacağınız konusunda sorularınız varsa, doktorunuza danışınız.",
        "Если у вас есть вопросы о том, как долго применять {BRAND}, проконсультируйтесь с врачом.",
        "If you have questions about how long to use {BRAND}, consult your doctor.",
    ) == []


SHIFTED_REQUESTS = json.loads((Path(__file__).parent / "fixtures" / "medicine_paragraph_shifts.json").read_text())
# Запросы частей 3–5, где переводы на месте, а сдвиг находился из-за словаря понятий.
ALIGNED_REQUESTS = json.loads((Path(__file__).parent / "fixtures" / "medicine_paragraph_aligned.json").read_text())


@pytest.mark.parametrize("request_", ALIGNED_REQUESTS, ids=[item["request"].split(",")[0] for item in ALIGNED_REQUESTS])
def test_aligned_requests_from_parts_3_to_5_are_not_shifted(request_):
    _, rejected = check_paragraph_payload(request_["items"], request_["answer"])

    assert not any("shifted" in problems for problems in rejected.values())


@pytest.mark.parametrize("request_", SHIFTED_REQUESTS, ids=[item["request"].split(",")[0] for item in SHIFTED_REQUESTS])
def test_real_shifted_requests_from_parts_1_to_3_are_rejected_whole(request_):
    accepted, rejected = check_paragraph_payload(request_["items"], request_["answer"])

    assert accepted == {}
    assert all("shifted" in problems for problems in rejected.values())


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


def test_answer_without_some_paragraph_rejects_whole_request():
    items = {str(index): source for index, source in enumerate(SOURCES, 1)}
    # Модель закончила ответ на ключ раньше — пропустила абзац (так в 86 % сдвигов 20.10).
    payload = {str(index): {"ru": ru, "en": en} for index, (_, ru, en) in enumerate(VISCOTEARS[:-1], 1)}

    accepted, rejected = check_paragraph_payload(items, payload)

    assert accepted == {}
    assert all("shifted" in rejected[source] for source in SOURCES)
    _, failed = check_paragraph_payload(items, {})  # пустой ответ — сбой запроса, а не сдвиг
    assert not any("shifted" in problems for problems in failed.values())


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


def _section(rows):
    return "\n".join(rows)


def test_section_check_passes_correct_translation_and_finds_shifted_paragraphs():
    ru, en = [row[1] for row in VISCOTEARS], [row[2] for row in VISCOTEARS]
    assert section_paragraph_problems(_section(SOURCES), _section(ru), _section(en)) == []

    # Лог до 21.10: модель пропустила абзац 6, дальше у каждого — перевод следующего.
    shifted_ru, shifted_en = _shifted_from(5)
    shifted_ru[-1], shifted_en[-1] = "Обратитесь к врачу.", "Consult your doctor."
    findings = section_paragraph_problems(_section(SOURCES), _section(shifted_ru), _section(shifted_en))

    assert {item["number"] for item in findings} >= {6, 7, 8, 9, 10}
    assert all("shifted" in item["problems"] for item in findings if 6 <= item["number"] <= 9)
    assert findings[0]["source"] in SOURCES and findings[0]["ru"] in shifted_ru


def test_section_check_aligns_both_paragraph_splits_and_reports_unaligned_section():
    # До 21.10 «®» и «'u …» после бренда были отдельными абзацами, теперь — один абзац.
    source = "EPORON\n®\n'u kullanmadan önce doktorunuza danışınız."
    old_ru = "EPORON\n®\n'u — перед применением проконсультируйтесь с врачом."
    old_en = "EPORON\n®\n'u — consult your doctor before use."
    new_ru = "Перед применением EPORON проконсультируйтесь с врачом."
    new_en = "Consult your doctor before using EPORON."

    assert section_paragraph_problems(source, new_ru, new_en, brand="EPORON") == []
    assert all(item["number"] for item in section_paragraph_problems(source, old_ru, old_en, brand="EPORON"))
    assert section_paragraph_problems(source, "Одна строка\nвторая\nтретья\nчетвёртая", new_en) == [
        {"number": 0, "problems": ["paragraph_count_mismatch"], "source": "", "ru": "", "en": ""}
    ]


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
