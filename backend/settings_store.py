"""AI 配置存储：data/settings.json（LLM key，搜索与 LLM 共用）。"""
import json
import config


def _path():
    return config.DATA_DIR / "settings.json"


def load():
    p = _path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save(data):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def get_llm_key():
    # 演示模式：不认 config 内置 key，只认 demo_data/settings.json 或环境变量
    if config.DEMO_MODE:
        return load().get("llm_api_key") or config.os.environ.get("LLM_API_KEY", "")
    return load().get("llm_api_key") or config.LLM["api_key"]


def get_llm_base_url():
    return load().get("llm_base_url") or config.LLM["base_url"]


def get_llm_model():
    return load().get("llm_model") or config.LLM["model"]


def get_search_base_url():
    return load().get("search_base_url") or config.SEARCH["base_url"]


def get_search_key():
    return load().get("search_api_key") or config.SEARCH["api_key"] or get_llm_key()


def get_prompt(key, default):
    return load().get(key) or default


def save_prompt(key, value):
    data = load()
    data[key] = value
    save(data)


def get_emails():
    emails = load().get("emails", [])
    if config.DEMO_MODE:
        # 演示模式：只认 demo_data/settings.json 里显式配置的邮箱 + 环境变量
        if not emails:
            addr = config.os.environ.get("EMAIL_ADDR", "")
            pw = config.os.environ.get("EMAIL_PASS", "")
            if addr and pw:
                return [{"imap_server": config.os.environ.get("EMAIL_IMAP", "imap.qq.com"),
                         "address": addr, "password": pw}]
        return emails
    if not emails and config.EMAIL.get("address") and config.EMAIL.get("password"):
        return [{
            "imap_server": config.EMAIL["imap_server"],
            "address": config.EMAIL["address"],
            "password": config.EMAIL["password"],
        }]
    return emails


def save_emails(emails):
    data = load()
    data["emails"] = emails
    save(data)


def get_last_email_check():
    return load().get("last_email_check_at", "")


def set_last_email_check(ts):
    data = load()
    data["last_email_check_at"] = ts
    save(data)
