"""部署秋招助手演示实例到云服务器——无密钥部分。

上传代码+数据+配置模板；服务器上的 demo.env（含 LLM key、邮箱授权码）
由用户自己运行 make_demo_env.py 写入，本脚本不接触任何密钥。
用法：python deploy_demo2.py [host] [user]   （默认香港轻量 root@119.28.16.198；旧机 122.51.110.21 ubuntu）
"""
import os
import re
import sys
import tarfile
import tempfile
from pathlib import Path

import paramiko

HOST = sys.argv[1] if len(sys.argv) > 1 else "119.28.16.198"
USER = sys.argv[2] if len(sys.argv) > 2 else "root"
BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent

CODE_FILES = ["app.py", "config.py", "db.py", "email_checker.py", "ai_assistant.py",
              "resume_store.py", "settings_store.py", "job_pool.py", "seed_demo.py"]
FRONTEND_FILES = ["index.html", "widget.html"]
DEMO_DATA_FILES = ["tasks.db", "jobs.json", "resumes.json"]  # 不含 settings.json


def make_tar():
    tar_path = Path(tempfile.gettempdir()) / "jt-demo.tar.gz"
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
                print("config.py 已脱敏")
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
EnvironmentFile=/opt/jobtracker/demo.env
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
    pw = (BACKEND / "cvm_pw.txt").read_text(encoding="utf-8").splitlines()[0].strip()
    tar_path = make_tar()

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=pw, timeout=20)
    print("ssh ok")

    sftp = c.open_sftp()
    sftp.put(str(tar_path), "/tmp/jt-demo.tar.gz")
    with sftp.open("/tmp/jobtracker-demo.service", "w") as f:
        f.write(UNIT)
    with sftp.open("/tmp/jobtracker-demo.nginx", "w") as f:
        f.write(NGINX)
    sftp.close()
    print("uploaded")

    script = (
        "set -e; "
        "mkdir -p /opt/jobtracker && tar xzf /tmp/jt-demo.tar.gz -C /opt/jobtracker && rm /tmp/jt-demo.tar.gz; "
        # pip 依赖（dnf 系和 apt 系都兼容）
        "if ! python3 -c 'import flask, openpyxl, requests' 2>/dev/null; then "
        "  python3 -m pip --version >/dev/null 2>&1 || { command -v dnf >/dev/null && dnf install -y -q python3-pip || { apt-get update -qq && apt-get install -y -qq python3-pip >/dev/null; }; }; "
        "  python3 -m pip install -q flask openpyxl requests; "
        "fi; "
        "command -v nginx >/dev/null || { command -v dnf >/dev/null && dnf install -y -q nginx || { apt-get update -qq && apt-get install -y -qq nginx >/dev/null; }; }; "
        "mv /tmp/jobtracker-demo.service /etc/systemd/system/jobtracker-demo.service; "
        # Ubuntu 用 sites-available；OpenCloudOS/CentOS 用 conf.d
        "if [ -d /etc/nginx/sites-available ]; then "
        "  mv /tmp/jobtracker-demo.nginx /etc/nginx/sites-available/jobtracker-demo; "
        "  ln -sf /etc/nginx/sites-available/jobtracker-demo /etc/nginx/sites-enabled/jobtracker-demo; "
        "else "
        "  mv /tmp/jobtracker-demo.nginx /etc/nginx/conf.d/jobtracker-demo.conf; "
        "fi; "
        "systemctl enable nginx >/dev/null 2>&1; "
        "nginx -t && { systemctl reload nginx 2>/dev/null || systemctl restart nginx; }; "
        "systemctl daemon-reload; systemctl enable jobtracker-demo >/dev/null; "
        "touch /opt/jobtracker/demo.env && chmod 600 /opt/jobtracker/demo.env; "
        "echo SETUP_DONE"
    )
    import json
    if USER == "root":
        cmd = "bash -c " + json.dumps(script)
    else:
        cmd = "echo '" + pw + "' | sudo -S bash -c " + json.dumps(script)
    _, out, err = c.exec_command(cmd, timeout=600)
    print(out.read().decode(errors="replace"))
    e = err.read().decode(errors="replace")
    if e.strip():
        print("STDERR:", e[-400:])
    c.close()


if __name__ == "__main__":
    main()
