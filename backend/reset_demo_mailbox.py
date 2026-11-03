"""清空演示邮箱里旧的演示邮件（按企业名匹配主题），并重发 demo_emails.json 里的最新版本。

用法：python reset_demo_mailbox.py
凭据从 demo_mailbox.txt 读取（脚本内无明文）。
"""
import json
import re
import smtplib
import sys
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

import imaplib

BACKEND = Path(__file__).resolve().parent
COMPANIES = ["汇川证券", "天璇基金", "光年智能", "德润银行"]


def load_demo_mailbox():
    lines = [l.strip() for l in (BACKEND / "demo_mailbox.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    addr = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]+", lines[1]).group(0)
    code = re.findall(r"[A-Za-z0-9]+", lines[2])[-1]
    return lines[0].strip(), addr, code


def main():
    imap_host, addr, code = load_demo_mailbox()
    smtp_host = imap_host.replace("imap.", "smtp.")

    # 1. IMAP 删除旧演示邮件
    mail = imaplib.IMAP4_SSL(imap_host)
    mail.login(addr, code)
    mail.xatom('ID', '("name" "jobtracker" "version" "1.0.0" "vendor" "jobtracker")')
    deleted = 0
    for folder in ["INBOX", "Junk", "&V4NXPpCuTvY-"]:
        status, _ = mail.select(folder)
        if status != "OK":
            continue
        for kw in COMPANIES:
            # 163 支持 UTF-8 搜索需先开 ENABLE UTF8=ACCEPT，退而求其次：全量取主题匹配
            pass
        st, data = mail.search(None, "ALL")
        if st != "OK" or not data[0]:
            continue
        for seq in data[0].split():
            typ, fetched = mail.fetch(seq, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
            if typ != "OK":
                continue
            for item in fetched:
                if not isinstance(item, tuple):
                    continue
                import email as email_mod
                from email.header import decode_header
                msg = email_mod.message_from_bytes(item[1])
                subj = "".join(
                    (t.decode(enc or "utf-8", errors="ignore") if isinstance(t, bytes) else t)
                    for t, enc in decode_header(msg.get("Subject", "")))
                if any(c in subj for c in COMPANIES):
                    mail.store(seq, "+FLAGS", "\\Deleted")
                    deleted += 1
        mail.expunge()
    mail.logout()
    print(f"[clean] 删除旧演示邮件 {deleted} 封")

    # 2. 重发最新 demo_emails.json
    mails = json.loads((BACKEND / "demo_emails.json").read_text(encoding="utf-8"))
    smtp = smtplib.SMTP_SSL(smtp_host, 465, timeout=30)
    smtp.login(addr, code)
    try:
        for m in mails:
            msg = MIMEText(m["body"], "plain", "utf-8")
            msg["Subject"] = Header(m["subject"], "utf-8")
            msg["From"] = formataddr((str(Header(f"{m['company']}校招", "utf-8")), addr))
            msg["To"] = addr
            smtp.sendmail(addr, [addr], msg.as_string())
            print(f"[sent] {m['subject']}")
    finally:
        smtp.quit()
    print(f"完成，共 {len(mails)} 封")


if __name__ == "__main__":
    main()
