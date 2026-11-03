import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env():
    """从 backend/.env 读取本地密钥到环境变量（不覆盖已有值）。.env 不入 git。"""
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_env()

# 演示模式：DEMO_MODE=1 时启用——数据目录隔离到 demo_data/，
# 本文件内置的默认凭据在演示模式下不生效（见 settings_store 的兜底逻辑），
# AI 接口走预生成缓存（ai_assistant 的 _demo_read）。
DEMO_MODE = os.environ.get("DEMO_MODE") == "1"
DATA_DIR = BASE_DIR / ("demo_data" if DEMO_MODE else "data")
DB_PATH = DATA_DIR / "tasks.db"

# 邮箱检测（IMAP，用于自动识别秋招进度）
# 值从环境变量读取，本地填在 backend/.env（见 _load_env），不再写死在代码里
EMAIL = {
    "imap_server": os.environ.get("EMAIL_IMAP", "imap.qq.com"),  # 如 imap.qq.com
    "address": os.environ.get("EMAIL_ADDR", ""),      # 邮箱地址
    "password": os.environ.get("EMAIL_PASS", ""),     # 授权码（不是登录密码）
}

# AI 分析邮件内容判断阶段（DeepSeek，和投后项目用同一个 key）
LLM = {
    "base_url": os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
    "api_key": os.environ.get("LLM_API_KEY", ""),   # 填你的 DeepSeek key（放 backend/.env，不入 git）
    "model": os.environ.get("LLM_MODEL", "deepseek-flash"),
}

# 搜索（默认 DeepSeek 原生 Search；切换到不支持搜索的模型时，可单独配搜索 key）
SEARCH = {
    "base_url": os.environ.get("SEARCH_BASE_URL", "https://api.deepseek.com/v1/tools/search"),
    "api_key": os.environ.get("SEARCH_API_KEY", ""),   # 留空则复用 LLM 的 key
}
