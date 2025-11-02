import json
from pathlib import Path

_cache = {}

def load_lang(lang: str, base_path: Path) -> dict:
    if lang in _cache:
        return _cache[lang]
    path = base_path / f"{lang}.json"
    if path.exists():
        _cache[lang] = json.loads(path.read_text(encoding="utf-8"))
    else:
        _cache[lang] = {}
    return _cache[lang]
