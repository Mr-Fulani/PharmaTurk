"""Непроверенные записи памяти абзацев → части по 40 для проверки Haiku (TD-025). Только чтение.

python3 -I prepare_chunks.py <memory.jsonl.gz> <alignment.json> <seen_ids.json> <new667.json> <out_dir>

memory.jsonl.gz — выгрузка памяти (export_memory.py); alignment.json — словарь терминов памяти
(glossary/scripts/build_alignment.py); seen_ids.json — id, уже проверенные Haiku 23.10 (части и группы
run1–run5 и пилот 4); new667.json — абзацы, переведённые Haiku со скептиком 24.10 (по тексту исходника).
Варианты одного абзаца из PDF (canon) проверяются одним представителем: больше hits, меньше id.
Группа, где хоть одна запись уже проверена, пропускается. Части идут по убыванию подозрительности
(как rank_memory.py); подсказка кода — какой термин без обычного перевода.
Пишет out_dir/chunks.jsonl.gz (строка = {"k", "items": [{i, tr, ru, en, hint}]}) и groups.json.
"""
import gzip, json, os, re, sys, unicodedata
from collections import Counter, defaultdict

mem_path, al_path, seen_path, new667_path, out_dir = sys.argv[1:6]
os.makedirs(out_dir, exist_ok=True)
A = json.load(open(al_path))
WORD = re.compile(r"[^\W\d_]{3,}")


def tr_low(text):
    return text.replace('{BRAND}', ' ').replace('I', 'ı').replace('İ', 'i').lower()


def x_low(text):
    return text.replace('{BRAND}', ' ').lower().replace('ё', 'е')


def canon(s):
    """Один ключ для вариантов исходника из PDF: апострофы, OCR-цифры, пробелы, хвостовая пунктуация."""
    s = unicodedata.normalize('NFKC', s)
    s = re.sub(r"\s*['’`´ʼ]\s*", "'", s)
    s = re.sub(r"(?<=\d)[oO](?=\d)|(?<=\d)[oO]\b|\b[oO](?=\d)", "0", s)
    s = re.sub(r"(?<=\d)[lI](?=\d)|\b[lI](?=\d)", "1", s)
    s = re.sub(r"\s+", " ", s).strip(" .;,")
    return s


records, empty = [], 0
forms = {'ru': defaultdict(Counter), 'en': defaultdict(Counter)}
with gzip.open(mem_path, 'rt', encoding='utf-8') as f:
    for line in f:
        o = json.loads(line)
        if o['ns'] != 'medicine_paragraph':
            continue
        if not o['ru'] or not o['en']:
            empty += 1
            continue
        records.append(o)
        for lang in ('ru', 'en'):
            for w in WORD.findall(x_low(o[lang])):
                forms[lang][w[:6]][w] += 1

seen = set(json.load(open(seen_path)))
new667_tr = {x['tr'] for x in json.load(open(new667_path))}
seen |= {o['id'] for o in records if o['tr'] in new667_tr}
seen_canon = {canon(o['tr']) for o in records if o['id'] in seen}


def best_p(lang, t):
    return max([p for _, _, p in A[lang].get(t) or []] or [0])


def has(cands, stems):
    return any(any(s[:(4 if len(r) <= 5 else 5)] == r[:(4 if len(r) <= 5 else 5)] for s in stems) for r in cands)


def analyse(o, min_p=0.5, min_df=5):
    T = {}
    for w in WORD.findall(tr_low(o['tr'])):
        T.setdefault(w[:5], w)
    eligible = [t for t in T if A['tr_df'].get(t, 0) >= min_df and best_p('ru', t) >= min_p]
    score, hints = 0.0, []
    for lang in ('ru', 'en'):
        X = {w[:6] for w in WORD.findall(x_low(o[lang]))}
        for t in T:
            top = A[lang].get(t)
            if not top or A['tr_df'].get(t, 0) < min_df or best_p(lang, t) < min_p:
                continue
            cands = [r for r, dice, p in top if dice >= 0.2 or p >= 0.3]
            if not has(cands, X):
                score += best_p(lang, t)
                expected = [forms[lang][r].most_common(1)[0][0] for r in cands[:2] if forms[lang][r]]
                hints.append({'lang': lang, 'tr_word': T[t], 'expected': expected})
    return score / (1 + 0.15 * len(eligible)), hints


def hint_text(hints):
    parts = []
    for h in hints[:4]:
        exp = ' / '.join(h['expected']) or '?'
        parts.append(f"{h['lang'].upper()} lacks the usual translation of '{h['tr_word']}' (usually: {exp})")
    return '; '.join(parts)


groups = defaultdict(list)
for o in records:
    if o['id'] in seen:
        continue
    c = canon(o['tr'])
    if c in seen_canon:
        continue
    groups[c].append(o)
reps = []
for members in groups.values():
    rep = sorted(members, key=lambda o: (-o['hits'], o['id']))[0]
    score, hints = analyse(rep)
    reps.append((score, rep, hints, [m['id'] for m in members]))
reps.sort(key=lambda x: (-x[0], x[1]['id']))

k = 0
with gzip.open(os.path.join(out_dir, 'chunks.jsonl.gz'), 'wt', encoding='utf-8') as out:
    for start in range(0, len(reps), 40):
        items = [{'i': rep['id'], 'tr': rep['tr'], 'ru': rep['ru'], 'en': rep['en'], 'hint': hint_text(hints)}
                 for _, rep, hints, _ in reps[start:start + 40]]
        out.write(json.dumps({'k': k, 'items': items}, ensure_ascii=False) + '\n')
        k += 1
json.dump({str(rep['id']): ids for _, rep, _, ids in reps if len(ids) > 1},
          open(os.path.join(out_dir, 'groups.json'), 'w'), ensure_ascii=False)
stats = {'paragraph_records': len(records), 'empty_translation': empty, 'already_checked': len(seen),
         'unchecked_records': sum(len(ids) for *_, ids in reps), 'representatives': len(reps), 'chunks': k,
         'with_hint': sum(1 for _, _, h, _ in reps if h)}
json.dump(stats, open(os.path.join(out_dir, 'stats.json'), 'w'))
print(stats)
