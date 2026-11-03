"""多份简历存储：data/resumes.json，列表 [{name, content}]。"""
import json
import config


def _path():
    return config.DATA_DIR / "resumes.json"


def load():
    p = _path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save(resumes):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(resumes, ensure_ascii=False), encoding="utf-8")
