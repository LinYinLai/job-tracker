"""本地完整链路验证：起 demo 实例（带演示邮箱 + 真实 LLM key）→ 点检测邮箱 → 打印四家演示企业的推进结果。

凭据来源：demo_mailbox.txt（演示邮箱）、data/settings.json（真实 key，仅进程内环境变量，不落盘）。
用法：python verify_demo_email.py
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent


def load_demo_mailbox():
    lines = [l.strip() for l in (BACKEND / "demo_mailbox.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    addr = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]+", lines[1]).group(0)
    code = re.findall(r"[A-Za-z0-9]+", lines[2])[-1]
    imap = lines[0].strip()
    return imap, addr, code


def real_llm_key():
    """从真实配置拿 LLM key（子进程非 DEMO 模式读 config 默认值，密钥不进日志）。"""
    out = subprocess.run(
        [sys.executable, "-c", "import config; print(config.LLM['api_key'])"],
        cwd=BACKEND, capture_output=True, text=True)
    return out.stdout.strip()


def main():
    imap, addr, code = load_demo_mailbox()
    env = dict(os.environ,
               DEMO_MODE="1", PORT="8002",
               EMAIL_IMAP=imap, EMAIL_ADDR=addr, EMAIL_PASS=code,
               LLM_API_KEY=real_llm_key())
    log = open(BACKEND / "demo_run.log", "w", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "app.py"], cwd=BACKEND, env=env,
                         stdout=log, stderr=subprocess.STDOUT)
    print(f"demo 实例已启动 (pid {p.pid})，端口 8002")
    time.sleep(4)
    try:
        req = urllib.request.Request("http://127.0.0.1:8002/api/check-email", method="POST")
        r = json.load(urllib.request.urlopen(req, timeout=180))
        print("检测邮箱结果：")
        print(json.dumps(r, ensure_ascii=False, indent=1))
        comps = json.load(urllib.request.urlopen("http://127.0.0.1:8002/api/companies"))
        print("\n四家演示企业状态：")
        for c in comps:
            if c["name"] in ("汇川证券", "天璇基金", "光年智能", "德润银行"):
                print(f"  {c['name']} | {c['stage']} | {c['zone']} | time: {c['stage_time'] or '(空)'}")
    finally:
        p.terminate()
        print("\ndemo 实例已关闭")


if __name__ == "__main__":
    main()
