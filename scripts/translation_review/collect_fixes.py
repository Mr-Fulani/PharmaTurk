"""Сбор ответов Batches API → части для скептика и итоговые исправления с автопроверками (TD-025).
В прод ничего не пишет.

python3 -I collect_fixes.py flagged <chunks.jsonl[.gz]> <review_results.jsonl>... > flagged.jsonl
python3 -I collect_fixes.py fixes <chunks.jsonl[.gz]> <groups.json> <alignment.json> <memory.jsonl.gz> <out_dir> \
        --review <review_results.jsonl>... --verify <verify_results.jsonl>... [--fragment <fragment_results.jsonl>...]
python3 -I collect_fixes.py fragments <fixes.jsonl> > fragments.jsonl   # правки обрывков → арбитру, по 20

Правка абзаца, чей турецкий текст кончается без знака препинания (заголовок или обрывок из PDF), после
арбитра (batch_review.py submit fragment) остаётся, только если он выбрал новую версию или написал свою.

Проверки правки — как collect_run.py 23.10: номер из своей части; {BRAND} сохранён; paragraph_problems
не даёт новых замечаний; словарь памяти не считает новый перевод хуже старого; нет нового многоточия;
правка меняет текст; правка не кончается оборванным словом, которого нет в словаре памяти (обрывок
PDF «St John's Wort (depresyo» Haiku переводит как «Зверобой (депресси», пилот 25.10). Стоимость — по usage ответов, цены Haiku 5.5 в Batches API (половина обычной).
"""
import gzip, json, os, re, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pp_local import paragraph_problems  # noqa: E402

PRICE_IN, PRICE_OUT = 0.10 / 2 / 1e6, 0.50 / 2 / 1e6  # $ за токен, Batches API
WORD = re.compile(r"[^\W\d_]{3,}")
ELLIPSIS = re.compile(r"\.\.\.|…")


def read_chunks(path):
    op = gzip.open if path.endswith('.gz') else open
    with op(path, 'rt', encoding='utf-8') as f:
        return {(o := json.loads(line))['k']: o['items'] for line in f if line.strip()}


def read_results(paths, stats, usage):
    """Ответы по файлам: [{k: объект ответа}] — у каждого прохода проверки свой файл."""
    res = []
    for p in paths:
        out = {}
        res.append(out)
        for line in open(p, encoding='utf-8'):
            r = json.loads(line)
            k = int(r['id'].split('-', 1)[1])
            if r['type'] != 'succeeded':
                stats[f"{r['id'][0]}_{r['type']}"] += 1
                continue
            for key, v in r['usage'].items():
                usage[key] += v
            if r['stop'] != 'end_turn':
                stats[f"{r['id'][0]}_stop_{r['stop']}"] += 1
                continue
            try:
                out[k] = json.loads(r['text'])
            except ValueError:
                stats[f"{r['id'][0]}_bad_json"] += 1
    return res


def merged_issues(passes, k, items):
    """Замечания всех проходов по части k: {i: [замечание, ...]}; чужие номера отбрасываются."""
    issues, bad = {}, 0
    for rev in passes:
        for iss in (rev.get(k) or {}).get('issues', []):
            if iss['i'] in items:
                issues.setdefault(iss['i'], []).append(iss)
            else:
                bad += 1
    return issues, bad


def is_fragment(tr):
    return bool(re.search(r"[^\W\d_]$", tr.strip()))


def fragments(argv):
    rows = [json.loads(line) for line in open(argv[0], encoding='utf-8')]
    rows = [r for r in rows if is_fragment(r['tr'])]
    for k in range(0, len(rows), 20):
        items = [{'i': r['id'], 'tr': r['tr'], 'problem': r['problem'], 'ru_old': r['ru_old'], 'en_old': r['en_old'],
                  'ru_new': r['ru_new'], 'en_new': r['en_new']} for r in rows[k:k + 20]]
        sys.stdout.write(json.dumps({'k': k // 20, 'items': items}, ensure_ascii=False) + '\n')
    print('fragments', len(rows), file=sys.stderr)


def cost(usage):
    inp = usage['input'] + usage['cache_write'] * 1.25 + usage['cache_read'] * 0.1
    return round(inp * PRICE_IN + usage['output'] * PRICE_OUT, 4)


def flagged(argv):
    chunks = read_chunks(argv[0])
    stats, usage = Counter(), Counter()
    passes = read_results(argv[1:], stats, usage)
    for k in sorted(set().union(*passes)):
        items = {it['i']: it for it in chunks[k]}
        issues, bad = merged_issues(passes, k, items)
        stats['review_bad_id'] += bad
        if issues:
            sys.stdout.write(json.dumps({'k': k, 'items': [items[i] for i in issues],
                                         'issues': [x for xs in issues.values() for x in xs]}, ensure_ascii=False) + '\n')
        stats['chunks'] += 1
        stats['passes_missing'] += sum(1 for rev in passes if k not in rev)
        stats['flagged'] += len(issues)
    print(json.dumps({**stats, 'usage': usage, 'cost_usd': cost(usage)}), file=sys.stderr)


def fixes(argv):
    chunks_path, groups_path, al_path, mem_path, out_dir = argv[:5]
    rest = argv[5:]
    rev_paths = rest[rest.index('--review') + 1:rest.index('--verify')]
    ver_end = rest.index('--fragment') if '--fragment' in rest else len(rest)
    ver_paths = rest[rest.index('--verify') + 1:ver_end]
    frag_paths = rest[ver_end + 1:]
    os.makedirs(out_dir, exist_ok=True)
    chunks = read_chunks(chunks_path)
    groups = json.load(open(groups_path))
    A = json.load(open(al_path))

    def best_p(lang, t):
        return max([p for _, _, p in A[lang].get(t) or []] or [0])

    def term_score(tr, ru, en):
        T = {w[:5] for w in WORD.findall(tr.replace('{BRAND}', ' ').replace('I', 'ı').replace('İ', 'i').lower())}
        s = 0.0
        for lang, text in (('ru', ru), ('en', en)):
            X = {w[:6] for w in WORD.findall(text.replace('{BRAND}', ' ').lower().replace('ё', 'е'))}
            for t in T:
                top = A[lang].get(t)
                if not top or A['tr_df'].get(t, 0) < 5 or best_p(lang, t) < 0.5:
                    continue
                cands = [r for r, d, p in top if d >= 0.2 or p >= 0.3]
                if not any(any(x[:(4 if len(r) <= 5 else 5)] == r[:(4 if len(r) <= 5 else 5)] for x in X) for r in cands):
                    s += best_p(lang, t)
        return s

    vocab = {'ru': set(), 'en': set()}
    with gzip.open(mem_path, 'rt', encoding='utf-8') as f:
        for line in f:
            o = json.loads(line)
            for lang in ('ru', 'en'):
                vocab[lang].update(w.lower() for w in WORD.findall(o[lang] or ''))

    def cut_word(lang, new, old):
        last = WORD.findall(new[-40:])
        if not last or not re.search(r"[^\W\d_]$", new.strip()):
            return False
        w = last[-1].lower()
        return w not in vocab[lang] and w not in {x.lower() for x in WORD.findall(old)}

    stats, u_rev, u_ver, u_frag = Counter(), Counter(), Counter(), Counter()
    frag = {}
    for res in read_results(frag_paths, stats, u_frag):
        for obj in res.values():
            frag.update({d['i']: d for d in obj['items']})
    passes = read_results(rev_paths, stats, u_rev)
    verifies = {}
    for res in read_results(ver_paths, stats, u_ver):
        verifies.update(res)  # повторная отправка части скептику заменяет прежний ответ
    out_fixes, rejected = [], []
    for k in sorted(set().union(*passes)):
        items = {it['i']: it for it in chunks[k]}
        stats['chunks'] += 1
        stats['items'] += len(items)
        flagged_ = {i: xs[0] for i, xs in merged_issues(passes, k, items)[0].items()}
        stats['flagged'] += len(flagged_)
        if flagged_ and k not in verifies:
            stats['chunks_without_verify'] += 1
            continue
        seen_v = set()
        for v in (verifies.get(k) or {}).get('items', []):
            if v['i'] not in flagged_ or v['i'] in seen_v:
                stats['verify_bad_id'] += 1
                continue
            seen_v.add(v['i'])
            if not v['real']:
                stats['refuted'] += 1
                continue
            it, iss = items[v['i']], flagged_[v['i']]
            ru_new = (v['ru_final'] or '').strip() or it['ru']
            en_new = (v['en_final'] or '').strip() or it['en']
            sev = v['severity'] if v['severity'] != 'none' else iss['severity']
            row = {'id': it['i'], 'chunk': k, 'severity': sev, 'category': iss['category'], 'problem': iss['problem'],
                   'reason': v['reason'], 'fix_was_wrong': v['fix_was_wrong'], 'tr': it['tr'], 'hint': it.get('hint', ''),
                   'ru_old': it['ru'], 'ru_new': ru_new, 'en_old': it['en'], 'en_new': en_new,
                   'variants': groups.get(str(it['i']), [it['i']])}
            why = []
            if frag_paths and is_fragment(it['tr']):
                d = frag.get(it['i'])
                row['fragment'] = d['choice'] if d else None
                if not d:
                    why.append('fragment_unjudged')
                elif d['choice'] == 'old':
                    why.append('fragment_keep_old')
                elif d['choice'] == 'merged':
                    ru_new = (d['ru_final'] or '').strip() or ru_new
                    en_new = (d['en_final'] or '').strip() or en_new
                    row['ru_new'], row['en_new'] = ru_new, en_new
            if ru_new == it['ru'] and en_new == it['en']:
                why.append('no_change')
            if '{BRAND}' in it['tr'] and ('{BRAND}' not in ru_new or '{BRAND}' not in en_new):
                why.append('brand_token_missing')
            if not ELLIPSIS.search(it['tr']) and any(ELLIPSIS.search(n) and not ELLIPSIS.search(o)
                                                     for n, o in ((ru_new, it['ru']), (en_new, it['en']))):
                why.append('ellipsis_added')
            if any(cut_word(lang, n, o) for lang, n, o in (('ru', ru_new, it['ru']), ('en', en_new, it['en'])) if n != o):
                why.append('cut_word')
            new_pp = set(paragraph_problems(it['tr'], ru_new, en_new)) - set(paragraph_problems(it['tr'], it['ru'], it['en']))
            if new_pp:
                why.append('paragraph_problems:' + ','.join(sorted(new_pp)))
            if term_score(it['tr'], ru_new, en_new) > term_score(it['tr'], it['ru'], it['en']) + 0.5:
                why.append('dictionary_worse')
            if why:
                row['rejected'] = why
                rejected.append(row)
                stats['rejected'] += 1
            else:
                out_fixes.append(row)
                stats['fix_' + sev] += 1
    for name, rows in (('fixes.jsonl', out_fixes), ('rejected.jsonl', rejected)):
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    summary = {**stats, 'fixes': len(out_fixes), 'variants_covered': sum(len(r['variants']) for r in out_fixes),
               'rejected_by': Counter(w.split(':')[0] for r in rejected for w in r['rejected']),
               'categories': Counter(r['category'] for r in out_fixes),
               'fragment_choice': Counter(r.get('fragment') for r in out_fixes + rejected if 'fragment' in r),
               'usage_review': u_rev, 'usage_verify': u_ver, 'usage_fragment': u_frag,
               'cost_usd': {'review': cost(u_rev), 'verify': cost(u_ver), 'fragment': cost(u_frag),
                            'total': round(cost(u_rev) + cost(u_ver) + cost(u_frag), 4)}}
    json.dump(summary, open(os.path.join(out_dir, 'stats.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    {'flagged': flagged, 'fixes': fixes, 'fragments': fragments}[sys.argv[1]](sys.argv[2:])
