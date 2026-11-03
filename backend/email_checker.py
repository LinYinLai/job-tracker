"""秋招邮件检测：企业名称匹配 + 关键词预筛 + AI(DeepSeek)分析正文判断阶段。"""
import imaplib
import email
import json
import re
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta

import requests
import config
import db
import settings_store

REJECT_KEYWORDS = ["遗憾", "未通过", "不合适", "感谢您的关注", "感谢你的关注", "暂不考虑", "未能通过", "抱歉", "婉拒"]

# 调剂/转岗类邮件：不是拒绝，也不推进阶段（真正的笔试/面试会另发通知）。
# 这类邮件常含「未通过/遗憾」，但指的是没通过原岗位、被调剂到别的岗位，不能判「已拒绝」。
TRANSFER_KEYWORDS = ["调剂", "岗位调整", "调岗", "转岗", "岗位变更", "重新安排"]


def _is_transfer(subject, body=""):
    """判断是否调剂/转岗类邮件。"""
    hay = subject + " " + (body or "")
    return any(k in hay for k in TRANSFER_KEYWORDS)

STAGE_KEYWORDS = [
    ("终面", ["终面", "三面", "hr面", "HR面", "最终轮"]),
    ("二面", ["二面", "复试"]),
    ("一面", ["一面", "初试", "初面"]),
    ("AI面试", ["AI面试", "AI面", "ai面试", "视频面试", "录制面试"]),
    ("笔试", ["笔试", "在线笔试", "在线考试", "考试", "专业知识测试"]),
    ("测评", ["测评", "在线测评", "性格测评", "认知测评", "潜力测评", "在线评估"]),
    ("面试", ["面试"]),
]

# 需要解析时间的阶段（考试/面试/测评有具体时间或截止时间）
SCHEDULED_STAGES = ["终面", "二面", "一面", "AI面试", "笔试", "测评", "面试"]


def _connect(account):
    if not account.get("imap_server") or not account.get("address") or not account.get("password"):
        raise RuntimeError("邮箱配置不完整")
    mail = imaplib.IMAP4_SSL(account["imap_server"])
    mail.login(account["address"], account["password"])
    # 163 等邮箱要求登录后先发 ID（RFC 2971），否则 SELECT 报 "Unsafe Login"
    try:
        mail.xatom('ID', '("name" "jobtracker" "version" "1.0.0" "vendor" "jobtracker")')
    except Exception:
        pass
    return mail


def _decode(s):
    parts = decode_header(s or "")
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="ignore"))
            except (LookupError, ValueError):
                out.append(text.decode("utf-8", errors="ignore"))
        else:
            out.append(text)
    return "".join(out)


def _extract_text(msg):
    """提取邮件正文纯文本（multipart 递归，text/plain 优先，text/html 兜底去标签）。"""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                try:
                    return part.get_payload(decode=True).decode(charset, errors="ignore")
                except Exception:
                    pass
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                charset = part.get_content_charset() or "utf-8"
                try:
                    html = part.get_payload(decode=True).decode(charset, errors="ignore")
                    return re.sub(r"<[^>]+>", " ", html)
                except Exception:
                    pass
        return ""
    charset = msg.get_content_charset() or "utf-8"
    try:
        return msg.get_payload(decode=True).decode(charset, errors="ignore")
    except Exception:
        return ""


def _fetch_headers(mail, folder, limit=800, since_date=None):
    """返回 [{seq, folder, subject, sender}]，最新在前；提供 since_date 时只取该日期之后的邮件。"""
    try:
        status, _ = mail.select(folder)
    except Exception:
        return []
    if status != "OK":
        return []  # 文件夹不存在（如 163 没有名为 Junk 的目录）时 select 返回 NO 而不抛异常
    if since_date:
        status, data = mail.search(None, f'SINCE "{since_date}"')
    else:
        status, data = mail.search(None, "ALL")
    if status != "OK" or not data[0]:
        return []
    ids = [i.decode() for i in data[0].split()]
    if not since_date:
        ids = ids[-limit:]
    results = []
    for j in range(0, len(ids), 100):
        chunk = ids[j:j + 100]
        typ, fetched = mail.fetch(",".join(chunk), "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
        if typ != "OK":
            continue
        for item in fetched:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            seq = item[0].split()[0].decode()
            try:
                msg = email.message_from_bytes(item[1])
            except Exception:
                continue
            results.append({
                "seq": seq,
                "folder": folder,
                "subject": _decode(msg.get("Subject", "")),
                "sender": _decode(msg.get("From", "")),
            })
    results.reverse()  # 最新（序号）在前
    return results


def _fetch_body(mail, folder, seq):
    """取指定序号邮件的正文纯文本。"""
    try:
        mail.select(folder)
        typ, data = mail.fetch(seq, "(BODY.PEEK[])")
        if typ != "OK":
            return ""
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2:
                try:
                    msg = email.message_from_bytes(item[1])
                    return _extract_text(msg)
                except Exception:
                    pass
    except Exception:
        pass
    return ""


def detect_stage(subject):
    """关键词预筛（仅主题，快、免费）。返回 stage 或 None。"""
    for kw in REJECT_KEYWORDS:
        if kw in subject:
            return "已拒绝"
    for stage, kws in STAGE_KEYWORDS:
        for kw in kws:
            if kw in subject:
                return stage
    return None


def ai_detect_stage(subject, body):
    """AI 分析主题+正文判断阶段。返回 stage 或 None。"""
    key = settings_store.get_llm_key()
    if not key:
        return None
    prompt = (
        "你是秋招进度分析助手。根据邮件主题和正文，判断这封邮件代表招聘流程的哪个阶段。\n"
        "只回复一个词（从下面选），不要解释：\n"
        "测评 / 笔试 / AI面试 / 面试 / 拒绝 / 无\n"
        "说明：拒绝=拒信/感谢信/终止流程/未通过；无=非阶段相关（广告、回执、无关通知）。\n\n"
        f"主题：{subject}\n"
        f"正文（前 600 字）：{body[:600]}"
    )
    try:
        resp = requests.post(
            f"{settings_store.get_llm_base_url().rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": settings_store.get_llm_model(), "messages": [{"role": "user", "content": prompt}], "temperature": 0},
            timeout=30,
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [AI] 分析失败：{e}")
        return None
    if "拒绝" in answer:
        return "已拒绝"
    for stage in ["测评", "笔试", "AI面试", "面试"]:
        if stage in answer:
            return stage
    return None


def ai_detect_time(subject, body):
    """用 AI 解析邮件里的考试/面试/测评具体时间或截止时间。"""
    key = settings_store.get_llm_key()
    if not key:
        return ""
    prompt = (
        "你是秋招时间解析助手。从下面这封邮件里，提取考试/面试/测评的「具体时间」或「截止时间」。\n"
        "要求：\n"
        "1. 有具体时间（如笔试/面试开始时间），输出类似「2026年10月31日（周六）上午9:30」。\n"
        "2. 是截止时间（如需在某个时间前完成测评/面试），输出类似「2026-10-08 23:59 前完成」。\n"
        "3. 只回复这一句话，不要任何解释。\n"
        "4. 邮件里没有明确时间，就回复「无」。\n\n"
        f"主题：{subject}\n"
        f"正文（前 1000 字）：{body[:1000]}"
    )
    try:
        resp = requests.post(
            f"{settings_store.get_llm_base_url().rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": settings_store.get_llm_model(), "messages": [{"role": "user", "content": prompt}], "temperature": 0},
            timeout=30,
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [AI] 时间解析失败：{e}")
        return ""
    if answer in ("无", "无。", "无时间", "无明确时间", "无明确时间。"):
        return ""
    return answer


RECRUITMENT_KEYWORDS = ["招聘", "校招", "校园", "测评", "笔试", "面试", "简历", "应聘", "offer", "Offer", "OFFER", "录用", "人才", "遗憾", "未通过", "不合适"]

# 简称匹配：邮件常省略公司全称里的法律后缀/行业词，如「国任财产保险股份有限公司」→邮件写「国任保险」
LEGAL_SUFFIXES = ["股份有限公司", "有限责任公司", "有限公司", "集团股份有限公司", "集团有限公司", "股份", "集团", "公司"]
TYPE_WORDS = ["财产", "人寿", "保险", "银行", "证券", "基金", "资产管理", "资管", "信托", "期货",
              "融资租赁", "租赁", "科技", "技术", "软件", "数据", "电子", "网络", "信息", "传媒",
              "能源", "汽车", "金融", "理财", "财富", "养老", "健康"]
GENERIC_SHORT = {"中国", "国家", "中央", "国际", "全国", "中华",
                 "深圳", "北京", "上海", "广州", "广东", "江苏", "浙江", "四川", "重庆", "天津",
                 "香港", "澳门", "台湾", "山东", "河南", "河北", "湖南", "湖北", "福建", "安徽",
                 "江西", "辽宁", "吉林", "黑龙江", "陕西", "山西", "云南", "贵州", "广西", "海南",
                 "甘肃", "青海", "宁夏", "新疆", "西藏", "内蒙古"}


def _name_variants(name):
    """生成公司名的匹配候选：全称、去法律后缀、再去掉单个行业词（如 财产/保险）。"""
    base = name
    for s in LEGAL_SUFFIXES:
        if base.endswith(s):
            base = base[: -len(s)]
            break
    out = {name, base}
    for w in TYPE_WORDS:
        if w in base:
            v = base.replace(w, "", 1)
            if len(v) >= 2:
                out.add(v)
    return out


def _build_matcher(companies):
    """返回 matches(name, hay) 判定函数。2 字候选只在全局唯一且非通用词时才启用，避免误配。"""
    variants = {}
    short_count = {}
    for c in companies:
        name = c["name"]
        vs = sorted(_name_variants(name), key=len, reverse=True)
        variants[name] = vs
        for v in vs:
            if len(v) == 2:
                short_count[v] = short_count.get(v, 0) + 1

    def matches(name, hay):
        for v in variants.get(name, ()):
            if v in GENERIC_SHORT:
                continue
            if len(v) >= 3 or short_count.get(v, 0) == 1:
                if v in hay:
                    return True
        return False

    return matches


def _fetch_account_emails(account, since_date=None):
    mail = _connect(account)
    try:
        emails = []
        # Junk 是 QQ 的叫法；163 垃圾箱是改良 UTF-7 编码名（select 失败会自动跳过）
        for folder in ["INBOX", "Junk", "&V4NXPpCuTvY-"]:
            emails += _fetch_headers(mail, folder, since_date=since_date)
        for e in emails:
            if any(k in e["subject"] for k in RECRUITMENT_KEYWORDS):
                e["body"] = _fetch_body(mail, e["folder"], e["seq"])
            else:
                e["body"] = ""
        return emails
    finally:
        mail.logout()


def _since_date_from(last):
    if not last:
        return None
    try:
        dt = datetime.fromisoformat(last)
        return (dt - timedelta(days=1)).strftime("%d-%b-%Y")
    except Exception:
        return None


def poll_and_update():
    """检测所有邮箱，更新各企业阶段。返回 [{id, name, stage}]。"""
    since_date = _since_date_from(settings_store.get_last_email_check())
    emails = []
    for account in settings_store.get_emails():
        try:
            emails += _fetch_account_emails(account, since_date=since_date)
        except Exception as e:
            print(f"[email] 检测 {account.get('address', '')} 失败：{e}")
    updated = []
    companies = db.list_companies()
    matches = _build_matcher(companies)
    for c in companies:
        if c["stage"] == "待投递":
            continue  # 还没投递，邮件不推进
        matched_list = []
        for e in emails:  # 最新在前，收集所有匹配该企业的邮件
            hay = e["subject"] + " " + e["sender"] + " " + e["body"]
            if matches(c["name"], hay):
                matched_list.append(e)
        if not matched_list:
            continue
        # 优先：找能通过关键词判定阶段的邮件（最新优先，跳过验证码等无关邮件）
        matched = None
        stage = None
        for e in matched_list:
            if _is_transfer(e["subject"], e["body"]):
                continue  # 调剂/转岗：不是拒绝也不推进，等后续笔试/面试通知
            s = detect_stage(e["subject"])
            if s is None:
                for kw in REJECT_KEYWORDS:
                    if kw in e["body"]:
                        s = "已拒绝"
                        break
            if s is not None:
                matched = e
                stage = s
                break
        # 兜底：都没有关键词命中，用最新一封做 AI 判断
        if matched is None:
            matched = matched_list[0]
            stage = ai_detect_stage(matched["subject"], matched["body"])
        if not stage:
            continue
        if stage == "已拒绝":
            # 拒绝是终态，总是应用
            if stage != c["stage"]:
                db.set_stage(c["id"], stage)
                if not c.get("stage_time_locked"):
                    db.set_stage_time(c["id"], "")
                updated.append({"id": c["id"], "name": c["name"], "stage": stage})
                print(f"[email] {c['name']} → {stage}（{matched['subject']}）")
            continue
        # 里程碑：已完成的（在历史里）跳过，防止回退
        history = json.loads(c.get("history") or "[]")
        if stage in history:
            continue
        if stage != c["stage"]:
            db.set_stage(c["id"], stage)
            if not c.get("stage_time_locked"):
                if stage in SCHEDULED_STAGES:
                    time_text = ai_detect_time(matched["subject"], matched["body"])
                    db.set_stage_time(c["id"], time_text)
                    if time_text:
                        db.set_stage_time_locked(c["id"], 1)  # 更新后默认订住
                else:
                    db.set_stage_time(c["id"], "")
            updated.append({"id": c["id"], "name": c["name"], "stage": stage})
            print(f"[email] {c['name']} → {stage}（{matched['subject']}）")
        elif stage in SCHEDULED_STAGES and not c.get("stage_time_locked"):
            # 阶段没变但未订住：取消订住后重新检测时，重新解析并更新时间，更新后订住
            time_text = ai_detect_time(matched["subject"], matched["body"])
            db.set_stage_time(c["id"], time_text)
            if time_text:
                db.set_stage_time_locked(c["id"], 1)
            updated.append({"id": c["id"], "name": c["name"], "stage": stage, "time": time_text})
            print(f"[email] {c['name']} 刷新时间：{time_text or '无'}（{matched['subject']}）")
    settings_store.set_last_email_check(datetime.now().isoformat())
    return updated
