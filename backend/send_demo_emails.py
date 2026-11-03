"""把 demo_emails.json 里的假通知发进演示邮箱（SMTP 自发自收）。

用法（在 backend/ 目录下）：
    python send_demo_emails.py <smtp服务器> <演示邮箱地址> <授权码>
例：
    python send_demo_emails.py smtp.qq.com demo@qq.com abcdefgh12345678

发完后，demo 实例里点 📬 检测邮箱即可看到四家企业被自动推进：
  汇川证券→测评 / 天璇基金→笔试(带时间) / 光年智能→AI面试(带截止时间) / 德润银行→已拒绝
"""
import json
import smtplib
import sys
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return
    host, addr, pw = sys.argv[1], sys.argv[2], sys.argv[3]
    mails = json.loads((Path(__file__).resolve().parent / "demo_emails.json").read_text(encoding="utf-8"))
    smtp = smtplib.SMTP_SSL(host, 465, timeout=30)
    smtp.login(addr, pw)
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
    print(f"完成，共 {len(mails)} 封 → {addr}（可能有几秒延迟才出现在收件箱）")


if __name__ == "__main__":
    main()
