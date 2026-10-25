"""paragraph_problems из backend без Django: заглушка для translation_memory."""
import os, re, sys, types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'backend'))
tm = types.ModuleType('apps.ai.services.translation_memory')
tm.normalize_source_text = lambda t: re.sub(r"\s+", " ", str(t or "")).strip()
tm.lookup = tm.remember = tm.source_hash = None
sys.modules['apps.ai.services.translation_memory'] = tm
from apps.ai.services.medicine_memory import paragraph_problems  # noqa: E402,F401
