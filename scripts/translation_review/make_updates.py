"""fixes.jsonl → файл записи для прода: представитель + варианты того же абзаца с их текущими текстами.

python3 -I make_updates.py <memory.jsonl.gz> <fixes.jsonl> <out.json>
Вариантам хвостовая пунктуация перевода подгоняется под их собственный исходник.
"""
import gzip, json, re, sys
mem_path, fixes_path, out_path = sys.argv[1:4]
fixes = [json.loads(l) for l in open(fixes_path, encoding='utf-8')]
need = {i for f in fixes for i in f['variants']} | {f['id'] for f in fixes}
mem = {}
with gzip.open(mem_path, 'rt', encoding='utf-8') as fh:
    for line in fh:
        o = json.loads(line)
        if o['id'] in need:
            mem[o['id']] = o
TAIL = re.compile(r'[\s.,;:]*$')

def tail(s):
    # хвост целиком: «..» и «.» — разные (вариант с одной точкой не должен получить «..»)
    return re.search(r'[.,;:]*\s*$', s).group(0).strip()

def retail(text, src_rep, src_var):
    if tail(src_rep) == tail(src_var):
        return text
    return TAIL.sub('', text) + tail(src_var)

out = []
for f in fixes:
    rep = mem[f['id']]
    for vid in sorted(set(f['variants']) | {f['id']}):
        v = mem[vid]
        ru = f['ru_new'] if vid == f['id'] else retail(f['ru_new'], rep['tr'], v['tr'])
        en = f['en_new'] if vid == f['id'] else retail(f['en_new'], rep['tr'], v['tr'])
        if ru == v['ru'] and en == v['en']:
            continue
        out.append({'id': vid, 'rep': f['id'], 'severity': f['severity'], 'src': v['tr'],
                    'ru_old': v['ru'], 'en_old': v['en'], 'ru_new': ru, 'en_new': en})
json.dump(out, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False)
print('updates', len(out), 'representatives', len(fixes), 'variants', len(out) - len({u['rep'] for u in out}))
