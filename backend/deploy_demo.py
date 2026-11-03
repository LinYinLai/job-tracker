"""部署秋招助手演示实例到腾讯云 CVM（122.51.110.21）。

- 上传：backend 代码 + frontend + demo_cache/ + demo_data/(tasks.db/jobs.json/resumes.json)
- 绝不上传：data/、demo_mailbox.txt、cvm_pw.txt、settings.json、日志、本地工具脚本
- 服务器：/opt/jobtracker，systemd 服务 jobtracker-demo（端口 8011），nginx 监听 8001 反代
- 凭据：cvm_pw.txt（SSH/sudo）、demo_mailbox.txt（演示邮箱）、config.py（LLM key，子进程读取）
用法：python deploy_demo.py
"""
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import paramiko

HOST, USER = "122.51.110.21", "ubuntu"
BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent

CODE_FILES = ["app.py", "config.py", "db.py", "email_checker.py", "ai_assistant.py",
              "resume_store.py", "settings_store.py", "job_pool.py", "seed_demo.py"]
FRONTEND_FILES = ["index.html", "widget.html"]
DEMO_DATA_FILES = ["tasks.db", "jobs.json", "resumes.json"]  # 不含 settings.json


def load_secrets():
    pw = (BACKEND / "cvm_pw.txt").read_text(encoding="utf-8").splitlines()[0].strip()
    lines = [l.strip() for l in (BACKEND / "demo_mailbox.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    email_imap = lines[0]
    email_addr = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]+", lines[1]).group(0)
    email_pass = re.findall(r"[A-Za-z0-9]+", lines[2])[-1]
    llm_key = subprocess.run(
        [sys.executable, "-c", "import config; print(config.LLM['api_key'])"],
        cwd=BACKEND, capture_output=True, text=True).stdout.strip()
    assert pw and email_addr and email_pass and llm_key, "凭据读取失败"
    return pw, email_imap, email_addr, email_pass, llm_key


def make_tar():
    tar_path = Path(os.environ["TEMP"]) / "jt-demo.tar.gz"
    with tarfile.open(tar_path, "w:gz") as t:
        for f in CODE_FILES:
            if f == "config.py":
                # 上传脱敏版：剥掉 config.py 里历史遗留的硬编码凭据默认值
                import io
                text = (BACKEND / f).read_text(encoding="utf-8")
                text = re.sub(
                    r'os\.environ\.get\("(EMAIL_ADDR|EMAIL_PASS|LLM_API_KEY)",\s*"[^"]*"\)',
                    r'os.environ.get("\1", "")', text)
                data = text.encode("utf-8")
                info = tarfile.TarInfo(f"backend/{f}")
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
                print("config.py 已脱敏（硬编码凭据不随包上传）")
                continue
            t.add(BACKEND / f, arcname=f"backend/{f}")
        for f in FRONTEND_FILES:
            t.add(ROOT / "frontend" / f, arcname=f"frontend/{f}")
        for p in (BACKEND / "demo_cache").rglob("*"):
            if p.is_file():
                t.add(p, arcname=f"backend/demo_cache/{p.relative_to(BACKEND / 'demo_cache')}")
        for f in DEMO_DATA_FILES:
            t.add(ROOT / "demo_data" / f, arcname=f"demo_data/{f}")
    print(f"tar: {tar_path.stat().st_size // 1024} KB")
    return tar_path


UNIT = """[Unit]
Description=Job Tracker Demo (Flask)
After=network.target

[Service]
WorkingDirectory=/opt/jobtracker/backend
Environment=DEMO_MODE=1
Environment=PORT=8011
Environment=EMAIL_IMAP={email_imap}
Environment=EMAIL_ADDR={email_addr}
Environment=EMAIL_PASS={email_pass}
Environment=LLM_API_KEY={llm_key}
ExecStart=/usr/bin/python3 app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""

NGINX = """server {
    listen 8001;
    server_name _;
    location / {
        proxy_pass http://127.0.0.1:8011;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }
}
"""


def main():
    pw, email_imap, email_addr, email_pass, llm_key = load_secrets()
    tar_path = make_tar()

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=pw, timeout=20)
    print("ssh ok")

    sftp = c.open_sftp()
    sftp.put(str(tar_path), "/tmp/jt-demo.tar.gz")
    sftp.close()
    print("uploaded")

    unit = UNIT.format(email_imap=email_imap, email_addr=email_addr,
                       email_pass=email_pass, llm_key=llm_key)
    script = (
        "set -e; "
        "mkdir -p /opt/jobtracker && tar xzf /tmp/jt-demo.tar.gz -C /opt/jobtracker && rm /tmp/jt-demo.tar.gz; "
        "python3 -c 'import flask, openpyxl, requests' 2>/dev/null || (apt-get update -qq && apt-get install -y -qq python3-pip >/dev/null && pip3 install -q flask openpyxl requests); "
        "cat > /etc/systemd/system/jobtracker-demo.service <<'EOF'\n" + unit + "EOF\n"
        "cat > /etc/nginx/sites-available/jobtracker-demo <<'EOF'\n" + NGINX + "EOF\n"
        "ln -sf /etc/nginx/sites-available/jobtracker-demo /etc/nginx/sites-enabled/jobtracker-demo; "
        "nginx -t && systemctl reload nginx; "
        "systemctl daemon-reload; systemctl enable --now jobtracker-demo; systemctl restart jobtracker-demo; "
        "sleep 3; systemctl is-active jobtracker-demo; "
        "curl -s http://127.0.0.1:8011/api/settings; echo; "
        "curl -s -o /dev/null -w 'nginx8001:%{http_code}\n' http://127.0.0.1:8001/api/settings"
    )
    cmd = "echo '" + pw + "' | sudo -S bash -c " + json.dumps(script)
    _, out, err = c.exec_command(cmd, timeout=600)
    print(out.read().decode(errors="replace"))
    e = err.read().decode(errors="replace")
    if e.strip():
        print("STDERR:", e[-400:])
    c.close()


if __name__ == "__main__":
    main()
