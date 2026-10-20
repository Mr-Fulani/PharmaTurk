# Временный локальный скрипт (не коммитится): шаблонные названия через проверки валидатора.
import json, sys, collections, django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from apps.ai.services.medicine_title import build_medicine_title
from apps.ai.services import semantic_validator as sv
c = collections.Counter(); ex = collections.defaultdict(list)
for line in open(sys.argv[1]):
    pid, name, raw = json.loads(line)
    t = build_medicine_title(name)
    if not t:
        continue
    c['шаблон'] += 1
    reason = None
    for loc in ('ru', 'en'):
        title = t[loc]
        p = sv._medicine_title_problem(title, name)
        if p: reason = p; break
        if sv._title_has_turkish_words(title) or (loc == 'ru' and sv._medicine_ru_title_untranslated(title, name)):
            reason = 'title_untranslated'; break
        if loc == 'ru':
            orig = sv._medicine_identity_tokens(name)
            if orig and not orig.issubset(sv._medicine_identity_tokens(title)):
                reason = 'title_identity_lost:' + ','.join(sorted(orig - sv._medicine_identity_tokens(title))); break
    if reason:
        key = reason.split(':')[0]
        c[key] += 1
        if len(ex[key]) < 40: ex[key].append((name, t['ru'], reason))
print(dict(c))
for k, v in ex.items():
    print('==', k)
    for x in v: print('  ', x)
