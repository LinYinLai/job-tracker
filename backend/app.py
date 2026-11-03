import sys
import os
import io
import json
import re
import time
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, str(Path(__file__).resolve().parent))

from flask import Flask, jsonify, request, send_from_directory, send_file

import openpyxl

import config
import db
import email_checker
import ai_assistant
import resume_store
import settings_store
import job_pool

app = Flask(__name__, static_folder=str(config.BASE_DIR / "frontend"), static_url_path="")
db.init_db()

DEMO = config.DEMO_MODE

# 演示模式限流：邮箱检测会真实连演示邮箱 + 调 DeepSeek，防止访客刷额度/刷爆邮箱
_LAST_CHECK_EMAIL = 0.0
CHECK_EMAIL_COOLDOWN = 30  # 秒


def demo_blocked():
    """演示模式下禁止的写操作统一返回 403。"""
    return jsonify({"error": "演示模式，该功能已关闭（本地版可用）"}), 403

# 阶段 → 区
ZONES = {
    "待投递": "todo_apply",
    "测评": "todo_action",
    "笔试": "todo_action",
    "AI面试": "todo_action",
    "一面": "todo_action",
    "二面": "todo_action",
    "终面": "todo_action",
    "面试": "todo_action",
    "等待": "waiting",
    "已拒绝": "done",
}


ADVANCED_STAGES = {"测评", "笔试", "AI面试", "一面", "二面", "终面", "面试"}

ZONE_KEYS = {"todo_apply", "todo_action", "waiting", "waiting_advanced", "done"}


def with_zone(c):
    d = dict(c)
    stage = d["stage"]
    try:
        history = json.loads(d.get("history") or "[]")
    except Exception:
        history = []
    d["history"] = history
    if stage == "等待":
        d["zone"] = "waiting_advanced" if any(s in ADVANCED_STAGES for s in history) else "waiting"
    else:
        d["zone"] = ZONES.get(stage, "waiting")
    if (d.get("zone_override") or "").strip():
        d["zone"] = d["zone_override"].strip()
    d["wait_days"] = None
    if stage == "等待" and d.get("updated_at"):
        try:
            updated = datetime.fromisoformat(d["updated_at"])
            d["wait_days"] = round((datetime.now() - updated).total_seconds() / 86400, 1)
        except Exception:
            pass
    return d


def parse_excel(file_storage):
    """解析 Excel，只取 3 列：企业名称 / 岗位 / 投递网址。返回 [{name, position, url}]。"""
    wb = openpyxl.load_workbook(io.BytesIO(file_storage.read()), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    name_col = position_col = url_col = None
    for i, h in enumerate(header):
        if name_col is None and any(k in h for k in ["公司名称", "企业名称", "单位名称", "名称", "name", "Name"]):
            name_col = i
        elif position_col is None and any(k in h for k in ["岗位", "职位", "position", "Position", "job", "Job"]):
            position_col = i
        elif url_col is None and any(k in h for k in ["网址", "链接", "url", "URL", "link", "Link", "http"]):
            url_col = i
    if name_col is None:
        name_col, position_col, url_col = 0, 1, 2
    if position_col is None:
        position_col = 1
    if url_col is None:
        url_col = 2

    def cell(row, idx):
        if idx is not None and idx < len(row) and row[idx] is not None:
            v = str(row[idx]).strip()
            return "" if v.lower() in ("none", "null") else v
        return ""

    companies = []
    for row in rows[1:]:
        if not row:
            continue
        name = cell(row, name_col)
        if not name:
            continue
        companies.append({"name": name, "position": cell(row, position_col), "url": cell(row, url_col)})
    return companies


@app.get("/api/companies")
def list_companies():
    return jsonify([with_zone(c) for c in db.list_companies()])


@app.get("/api/companies/<int:cid>")
def get_company(cid):
    c = db.get_company(cid)
    if not c:
        return jsonify({"error": "not found"}), 404
    return jsonify(with_zone(c))


@app.post("/api/companies")
def create_company():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    url = (data.get("url") or "").strip()
    position = (data.get("position") or "").strip()
    deadline = (data.get("deadline") or "").strip()
    if not name:
        return jsonify({"error": "缺少企业名称"}), 400
    return jsonify(with_zone(db.create_company(name, url, position, deadline)))


@app.post("/api/companies/<int:cid>/advance")
def advance(cid):
    c = db.get_company(cid)
    if not c:
        return jsonify({"error": "not found"}), 404
    db.advance_company(cid)
    return jsonify(with_zone(db.get_company(cid)))


@app.post("/api/companies/<int:cid>/reject")
def reject(cid):
    c = db.get_company(cid)
    if not c:
        return jsonify({"error": "not found"}), 404
    db.set_stage(cid, "已拒绝")
    return jsonify(with_zone(db.get_company(cid)))


@app.post("/api/companies/<int:cid>/stage")
def set_stage(cid):
    stage = request.get_json().get("stage")
    c = db.get_company(cid)
    if not c:
        return jsonify({"error": "not found"}), 404
    db.set_stage(cid, stage)
    return jsonify(with_zone(db.get_company(cid)))


@app.post("/api/companies/<int:cid>/update")
def update_company(cid):
    data = request.get_json()
    url = (data.get("url") or "").strip()
    position = (data.get("position") or "").strip()
    jd = (data.get("jd") or "").strip()
    note = (data.get("note") or "").strip()
    deadline = (data.get("deadline") or "").strip()
    stage_time = (data.get("stage_time") or "").strip()
    stage_time_locked = 1 if data.get("stage_time_locked") else 0
    name = (data.get("name") or "").strip() or None
    c = db.get_company(cid)
    if not c:
        return jsonify({"error": "not found"}), 404
    db.update_company(cid, url=url, position=position, jd=jd, name=name, note=note, deadline=deadline, stage_time=stage_time, stage_time_locked=stage_time_locked)
    return jsonify(with_zone(db.get_company(cid)))


@app.delete("/api/companies/<int:cid>")
def delete(cid):
    db.delete_company(cid)
    return jsonify({"ok": True})


@app.post("/api/companies/<int:cid>/zone")
def set_company_zone(cid):
    zone = ((request.get_json(silent=True) or {}).get("zone") or "").strip()
    if zone and zone not in ZONE_KEYS:
        return jsonify({"error": "无效的区域"}), 400
    return jsonify(with_zone(db.set_zone(cid, zone)))


@app.post("/api/check-email")
def check_email():
    if DEMO:
        global _LAST_CHECK_EMAIL
        now = time.time()
        elapsed = now - _LAST_CHECK_EMAIL
        if elapsed < CHECK_EMAIL_COOLDOWN:
            wait = int(CHECK_EMAIL_COOLDOWN - elapsed) + 1
            return jsonify({"updated": [], "last_check": settings_store.get_last_email_check(),
                            "throttled": True, "message": f"演示模式限流，请 {wait} 秒后再试"}), 429
        _LAST_CHECK_EMAIL = now
    updated = email_checker.poll_and_update()
    return jsonify({"updated": updated, "last_check": settings_store.get_last_email_check()})


@app.post("/api/companies/<int:cid>/prep")
def interview_prep(cid):
    c = db.get_company(cid)
    if not c:
        return jsonify({"error": "not found"}), 404
    prep = ai_assistant.generate_interview_prep(c["name"], c["position"], c.get("jd", ""))
    return jsonify({"prep": prep})


@app.post("/api/weekly-report")
def weekly_report():
    return jsonify(ai_assistant.generate_weekly_report(db.list_companies()))


@app.post("/api/jobs/upload")
def upload_jobs():
    if DEMO:
        return demo_blocked()
    if "file" not in request.files:
        return jsonify({"error": "没有上传文件"}), 400
    try:
        rows = job_pool.parse_excel(request.files["file"])
    except Exception as e:
        return jsonify({"error": f"解析失败：{e}"}), 400
    total = len(rows)
    rows = job_pool.filter_expired(rows)
    merge = (request.form.get("merge") or "1") != "0"
    if merge:
        job_pool.merge_and_save(rows)
    else:
        job_pool.save(rows)
    return jsonify({"count": len(rows), "skipped": total - len(rows)})


@app.get("/api/jobs")
def list_jobs():
    rows = job_pool.load()
    jobs = job_pool.filter_jobs(rows, request.args)
    total = len(jobs)
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    limit = max(1, min(limit, job_pool.LIMIT))
    page = jobs[offset:offset + limit]
    return jsonify({
        "total": total,
        "count": len(rows),
        "jobs": page,
        "has_more": offset + limit < total,
        "meta": job_pool.meta(rows),
    })


@app.post("/api/jobs/mark")
def mark_job():
    data = request.get_json()
    if data.get("id") is None:
        return jsonify({"error": "缺少 id"}), 400
    job_pool.mark_job(int(data["id"]), data.get("mark", ""), data.get("note", ""))
    return jsonify({"ok": True})


@app.post("/api/recommend")
def recommend():
    data = request.get_json()
    requirement = (data.get("requirement") or "").strip()
    resumes = resume_store.load()
    resume = resumes[0]["content"] if resumes else ""
    return jsonify(ai_assistant.recommend_jobs(resume, requirement))


@app.post("/api/portfolio-classify")
def portfolio_classify():
    companies = db.list_companies()
    ids = set(ai_assistant.classify_portfolio_batch(companies))
    for c in companies:
        db.set_portfolio(c["id"], c["id"] in ids)
    return jsonify({"count": len(ids)})


@app.get("/api/prompts")
def get_prompts():
    return jsonify({
        "interview_prep": settings_store.get_prompt("interview_prep_prompt", ai_assistant.DEFAULT_INTERVIEW_PREP_PROMPT),
        "weekly_summary": settings_store.get_prompt("weekly_summary_prompt", ai_assistant.DEFAULT_WEEKLY_SUMMARY_PROMPT),
        "interview_prep_default": ai_assistant.DEFAULT_INTERVIEW_PREP_PROMPT,
        "weekly_summary_default": ai_assistant.DEFAULT_WEEKLY_SUMMARY_PROMPT,
    })


@app.post("/api/prompts")
def save_prompts():
    if DEMO:
        return demo_blocked()
    data = request.get_json()
    for key in ["interview_prep_prompt", "weekly_summary_prompt"]:
        if data.get(key) is not None:
            settings_store.save_prompt(key, (data.get(key) or "").rstrip())
    return jsonify({"ok": True})


@app.get("/api/settings")
def get_settings():
    if DEMO:
        # 演示模式：不回传任何 key，只告诉前端这是演示实例
        return jsonify({
            "demo": True,
            "llm_base_url": "",
            "llm_model": "",
            "llm_api_key": "",
            "search_base_url": "",
            "search_api_key": "",
        })
    s = settings_store.load()
    return jsonify({
        "llm_base_url": s.get("llm_base_url") or config.LLM["base_url"],
        "llm_model": s.get("llm_model") or config.LLM["model"],
        "llm_api_key": s.get("llm_api_key") or config.LLM["api_key"],
        "search_base_url": s.get("search_base_url") or config.SEARCH["base_url"],
        "search_api_key": s.get("search_api_key") or config.SEARCH["api_key"],
    })


@app.post("/api/settings")
def save_settings():
    if DEMO:
        return demo_blocked()
    data = request.get_json()
    s = settings_store.load()
    for k in ["llm_base_url", "llm_model", "llm_api_key", "search_base_url", "search_api_key"]:
        if data.get(k) is not None:
            s[k] = (data.get(k) or "").strip()
    settings_store.save(s)
    return jsonify({"ok": True})


@app.get("/api/emails")
def get_emails():
    if DEMO:
        # 演示模式：不回传邮箱凭据，只显示是否已配置
        return jsonify({"emails": [{"imap_server": "", "address": "演示邮箱（已内置）", "password": ""}]
                        if settings_store.get_emails() else []})
    return jsonify({"emails": settings_store.get_emails()})


@app.post("/api/emails")
def save_email():
    if DEMO:
        return demo_blocked()
    data = request.get_json()
    address = (data.get("address") or "").strip()
    imap_server = (data.get("imap_server") or "").strip()
    password = (data.get("password") or "").strip()
    if not address or not password:
        return jsonify({"error": "缺少邮箱地址或授权码"}), 400
    emails = settings_store.get_emails()
    for e in emails:
        if e["address"] == address:
            e["imap_server"] = imap_server
            e["password"] = password
            break
    else:
        emails.append({"imap_server": imap_server, "address": address, "password": password})
    settings_store.save_emails(emails)
    return jsonify({"ok": True})


@app.delete("/api/emails/<address>")
def delete_email(address):
    if DEMO:
        return demo_blocked()
    settings_store.save_emails([e for e in settings_store.get_emails() if e["address"] != address])
    return jsonify({"ok": True})


@app.get("/api/resumes")
def list_resumes():
    resumes = resume_store.load()
    for r in resumes:
        r["has_file"] = (config.DATA_DIR / "resumes" / f"{r['name']}.pdf").exists()
    return jsonify({"resumes": resumes})


@app.post("/api/resumes")
def save_resume():
    if DEMO:
        return demo_blocked()
    data = request.get_json()
    name = (data.get("name") or "").strip()
    content = (data.get("content") or "")[:30000]
    if not name:
        return jsonify({"error": "缺少岗位方向"}), 400
    resumes = resume_store.load()
    for r in resumes:
        if r["name"] == name:
            r["content"] = content
            break
    else:
        resumes.append({"name": name, "content": content})
    resume_store.save(resumes)
    return jsonify({"ok": True})


@app.delete("/api/resumes/<name>")
def delete_resume(name):
    if DEMO:
        return demo_blocked()
    resume_store.save([r for r in resume_store.load() if r["name"] != name])
    return jsonify({"ok": True})


@app.post("/api/resumes/upload")
def upload_resume_pdf():
    if DEMO:
        return demo_blocked()
    if "file" not in request.files:
        return jsonify({"error": "没有文件"}), 400
    name = (request.form.get("name") or "").strip()
    if not name:
        return jsonify({"error": "缺少岗位方向"}), 400
    file = request.files["file"]
    data = file.read()
    # 只保存文件，不解析
    resume_dir = config.DATA_DIR / "resumes"
    resume_dir.mkdir(parents=True, exist_ok=True)
    (resume_dir / f"{name}.pdf").write_bytes(data)
    # 确保有对应记录（content 保留原样，新记录 content 为空）
    resumes = resume_store.load()
    if not any(r["name"] == name for r in resumes):
        resumes.append({"name": name, "content": ""})
        resume_store.save(resumes)
    return jsonify({"ok": True})


@app.get("/api/resumes/<name>/file")
def get_resume_file(name):
    pdf_path = config.DATA_DIR / "resumes" / f"{name}.pdf"
    if not pdf_path.exists():
        return jsonify({"error": "没有 PDF 文件"}), 404
    return send_file(pdf_path, mimetype="application/pdf")


@app.post("/api/import")
def import_companies():
    if "file" not in request.files:
        return jsonify({"error": "没有上传文件"}), 400
    try:
        companies = parse_excel(request.files["file"])
    except Exception as e:
        return jsonify({"error": f"解析失败：{e}"}), 400
    existing = {c["name"] for c in db.list_companies()}
    created = []
    for c in companies:
        if c["name"] in existing:
            continue  # 去重
        t = db.create_company(c["name"], c["url"], c["position"])
        created.append(with_zone(t))
        existing.add(c["name"])
    return jsonify({"count": len(created), "companies": created})


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/widget")
def widget():
    return send_from_directory(app.static_folder, "widget.html")


@app.get("/api/widget")
def widget_data():
    companies = [with_zone(c) for c in db.list_companies()]
    counts = {"todo_apply": 0, "todo_action": 0, "waiting": 0, "done": 0}
    urgent = []
    today = date.today()
    for c in companies:
        counts[c["zone"]] = counts.get(c["zone"], 0) + 1
        if c["zone"] == "todo_apply":
            dl = (c.get("deadline") or "").strip()
            m = re.search(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}", dl)
            if not m:
                continue
            try:
                dd = date.fromisoformat(m.group(0).replace("/", "-"))
            except ValueError:
                continue
            days = (dd - today).days
            if 0 <= days <= 3:
                urgent.append({"name": c["name"], "deadline": dl, "days": days})
    urgent.sort(key=lambda x: x["days"])
    return jsonify({"counts": counts, "urgent": urgent})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8001"))
    app.run(host="127.0.0.1", port=port, debug=not DEMO)
