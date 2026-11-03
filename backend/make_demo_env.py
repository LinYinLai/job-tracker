"""把 demo.env（LLM key + 演示邮箱凭据）写入服务器 /opt/jobtracker/demo.env 并重启服务。

★ 这个脚本由你自己运行（涉及密钥写入服务器）：
    python make_demo_env.py
密钥来源：demo_mailbox.txt、config.py（子进程读取），只写入服务器 demo.env，不打印、不留在项目其他文件里。
"""
import re
import subprocess
import sys
from pathlib import Path

import paramiko

HOST, USER = "119.28.16.198", "root"  # 香港轻量；旧机 122.51.110.21 ubuntu
BACKEND = Path(__file__).resolve().parent


def main():
    pw = (BACKEND / "cvm_pw.txt").read_text(encoding="utf-8").splitlines()[0].strip()
    lines = [l.strip() for l in (BACKEND / "demo_mailbox.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    imap = lines[0]
    addr = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]+", lines[1]).group(0)
    code = re.findall(r"[A-Za-z0-9]+", lines[2])[-1]
    key = subprocess.run(
        [sys.executable, "-c", "import config; print(config.LLM['api_key'])"],
        cwd=BACKEND, capture_output=True, text=True).stdout.strip()
    assert addr and code and key, "凭据读取失败"

    env_text = f"EMAIL_IMAP={imap}\nEMAIL_ADDR={addr}\nEMAIL_PASS={code}\nLLM_API_KEY={key}\n"

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=pw, timeout=20)
    sftp = c.open_sftp()
    with sftp.open("/tmp/demo.env", "w") as f:
        f.write(env_text)
    sftp.close()
    import json
    script = ("mv /tmp/demo.env /opt/jobtracker/demo.env && chmod 600 /opt/jobtracker/demo.env && "
              "systemctl restart jobtracker-demo && sleep 3 && systemctl is-active jobtracker-demo && "
              "curl -s -o /dev/null -w 'app:%{http_code}\\n' http://127.0.0.1:8011/api/settings && "
              "curl -s -o /dev/null -w 'nginx:%{http_code}\\n' http://127.0.0.1:8001/api/settings")
    _, out, err = c.exec_command("bash -c " + json.dumps(script), timeout=120)
    print(out.read().decode(errors="replace"))
    e = err.read().decode(errors="replace")
    if e.strip():
        print("STDERR:", e[-300:])
    c.close()
    print("demo.env 已写入并重启服务")


if __name__ == "__main__":
    main()
