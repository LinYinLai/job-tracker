"""岗位库：上传秋招汇总 Excel，解析并按条件筛选。"""
import io
import json
import re
from collections import Counter
from datetime import date, timedelta

import config

SPAM = "婉清学姐冲冲冲的店唯一正版"
LIMIT = 500  # 单次最多返回条数


def _path():
    return config.DATA_DIR / "jobs.json"


def save(rows):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(rows):
        r["id"] = i
        r.setdefault("mark", "")
        r.setdefault("note", "")
    _path().write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def load():
    p = _path()
    if p.exists():
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
        for r in rows:
            if r.get("unsuitable") and not r.get("mark"):
                r["mark"] = "unsuitable"
            r.pop("unsuitable", None)
            r.setdefault("mark", "")
            r.setdefault("note", "")
        return rows
    return []


def _clean(s):
    if s is None:
        return ""
    s = str(s).strip()
    if SPAM in s:
        s = s.replace(SPAM, "").replace("，", ",")
    s = re.sub(r"[,，\s]+$", "", s).strip()
    return s


def parse_excel(file_storage):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_storage.read()), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    idx = {name: header.index(name) for name in header}

    company_col = None
    for k in ["公司名称", "企业名称", "单位名称", "公司", "名称"]:
        if k in idx:
            company_col = idx[k]
            break
    if company_col is None:
        raise ValueError("未找到公司名称列，表头为：「" + "、".join(h for h in header[:12] if h) + "」，请确认上传的是秋招汇总表")

    def cell(row, name):
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else None

    out = []
    for row in rows[1:]:
        if not row:
            continue
        company = _clean(row[company_col] if company_col < len(row) else None)
        if not company:
            continue
        out.append({
            "company": company,
            "updated": str(cell(row, "更新时间") or "").strip(),
            "nature": _clean(cell(row, "企业性质")),
            "industry": _clean(cell(row, "行业分类")),
            "position": _clean(cell(row, "招聘岗位")),
            "location": _clean(cell(row, "工作地点")),
            "deadline": _clean(cell(row, "截止时间")),
            "year": _clean(cell(row, "届次")),
            "education": _clean(cell(row, "学历要求")),
            "batch": _clean(cell(row, "批次")),
            "source": _clean(cell(row, "公告来源")),
            "source_url": _clean(cell(row, "公告链接")),
            "apply_url": _clean(cell(row, "投递链接")),
            "major": _clean(cell(row, "专业要求")),
            "exam": _clean(cell(row, "是否笔试")),
        })
    if not out:
        raise ValueError("解析到 0 条岗位，表头为：「" + "、".join(h for h in header[:12] if h) + "」，可能表头不匹配或数据在其它工作表")
    return out


def _deadline_key(r):
    d = r.get("deadline", "")
    if "尽快" in d:
        return (0, "")
    m = re.search(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}", d)
    if m:
        return (1, m.group(0))
    return (2, d)


def filter_expired(rows, grace_days=0):
    """过滤掉已截止的岗位（截止日期早于「今天 - grace_days」）。无日期/「尽快投递」保留。"""
    cutoff = date.today() - timedelta(days=grace_days)
    out = []
    for r in rows:
        d = (r.get("deadline") or "").strip()
        m = re.search(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}", d)
        if not m:
            out.append(r)
            continue
        try:
            dd = date.fromisoformat(m.group(0).replace("/", "-"))
        except ValueError:
            out.append(r)
            continue
        if dd < cutoff:
            continue
        out.append(r)
    return out


def _freq(values):
    c = Counter(v for v in values if v)
    return [k for k, _ in c.most_common()]


def meta(rows):
    natures = _freq(r["nature"] for r in rows)
    industries = _freq(r["industry"].split(",")[0].strip() for r in rows if r["industry"])
    return {
        "natures": natures,
        "industries": industries,
        "years": ["2027届", "2026届", "2028届"],
        "educations": ["硕士", "本科", "博士"],
        "batches": ["秋招", "实习", "春招", "社招"],
    }


def filter_jobs(rows, p):
    q = (p.get("q") or "").strip()
    location = (p.get("location") or "").strip()
    locations = [x for x in re.split(r"[,，、\s]+", location) if x]
    industry = (p.get("industry") or "").strip()
    nature = (p.get("nature") or "").strip()
    year = (p.get("year") or "").strip()
    education = (p.get("education") or "").strip()
    batch = (p.get("batch") or "").strip()
    mark = (p.get("mark") or "").strip()

    result = []
    for r in rows:
        m = r.get("mark", "")
        if mark:
            if m != mark:
                continue
        elif m:
            continue
        if q:
            hay = " ".join([r["company"], r["position"], r["major"], r["industry"]])
            if q not in hay:
                continue
        if locations and not any(loc in r["location"] for loc in locations):
            continue
        if industry and industry not in r["industry"]:
            continue
        if nature and nature != r["nature"]:
            continue
        if year and year not in r["year"]:
            continue
        if education and education not in r["education"]:
            continue
        if batch and batch not in r["batch"]:
            continue
        result.append(r)
    sort = (p.get("sort") or "deadline").strip()
    order = (p.get("order") or "asc").strip()
    reverse = order == "desc"
    if sort == "updated":
        result.sort(key=lambda r: r.get("updated", ""), reverse=reverse)
    elif sort == "company":
        result.sort(key=lambda r: r.get("company", ""), reverse=reverse)
    else:
        result.sort(key=_deadline_key, reverse=reverse)
    return result


def mark_job(job_id, mark="", note=""):
    """设置岗位标记：''=无 / 'unsuitable'=不合适 / 'consider'=待考虑。"""
    rows = load()
    for r in rows:
        if r.get("id") == job_id:
            r["mark"] = mark or ""
            r["note"] = note or ""
            break
    save(rows)
    return True


def _job_key(r):
    return (r.get("company", "").strip(), r.get("position", "").strip())


def merge_and_save(new_rows):
    """上传时合并：按「公司+岗位」匹配旧数据，保留标记与备注。"""
    marks = {_job_key(r): (r.get("mark", ""), r.get("note", "")) for r in load() if r.get("mark")}
    for r in new_rows:
        mark, note = marks.get(_job_key(r), ("", ""))
        r["mark"] = mark
        r["note"] = note
    save(new_rows)
    return len(new_rows)
