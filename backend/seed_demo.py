"""演示数据种子脚本：生成 demo_data/ 下的虚构企业、岗位库、简历。

用法（在 backend/ 目录下）：
    DEMO_MODE=1 python seed_demo.py          # Windows cmd: set DEMO_MODE=1 && python seed_demo.py

只写 demo_data/，绝不触碰 data/ 真实数据。
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ["DEMO_MODE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import db  # noqa: E402
import job_pool  # noqa: E402
import resume_store  # noqa: E402

assert config.DEMO_MODE, "必须以 DEMO_MODE=1 运行"
assert config.DATA_DIR.name == "demo_data"

NOW = datetime.now()
WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def cn_date(d, suffix=""):
    return d.strftime("%Y年%m月%d日") + f"（{WEEKDAY_CN[d.weekday()]}）" + suffix



def days_ahead(n, hour=23, minute=59):
    d = NOW + timedelta(days=n)
    return d.strftime(f"%Y-%m-%d {hour:02d}:{minute:02d}")


# ---------------------------------------------------------------- 企业种子
# zone 说明：
#   todo_apply   待投递（stage=待投递）
#   todo_action  待推进（stage=测评/笔试/AI面试/一面/二面/终面/面试）
#   waiting      只投了简历（stage=等待, history=[已投递]）
#   waiting_adv  已推进（stage=等待, history 含测评/笔试/...）
#   done         已完成（stage=已拒绝）
#   email_demo   邮箱演示候选（stage=等待, history=[已投递]，等假邮件推进）
COMPANIES = [
    # ---- 待投递（8）----
    {"name": "青云证券", "position": "行业研究助理", "zone": "todo_apply",
     "deadline": days_ahead(1), "url": "https://example.com/qingyun", "note": "研究方向对口，优先投"},
    {"name": "巨石基金", "position": "投研管培生", "zone": "todo_apply",
     "deadline": days_ahead(2), "note": "需要准备行研作品"},
    {"name": "澄光智能", "position": "AI产品经理", "zone": "todo_apply", "portfolio": 1,
     "deadline": days_ahead(3), "note": "作品集链接放简历首页"},
    {"name": "远山信托", "position": "财富管理培训生", "zone": "todo_apply", "deadline": days_ahead(9)},
    {"name": "琥珀财富", "position": "机构销售助理", "zone": "todo_apply", "deadline": days_ahead(15)},
    {"name": "星舟科技", "position": "产品运营", "zone": "todo_apply", "portfolio": 1, "deadline": days_ahead(20)},
    {"name": "帆远期货", "position": "风险管理专员", "zone": "todo_apply"},
    {"name": "南屿银行", "position": "总行管培生", "zone": "todo_apply", "deadline": days_ahead(30)},

    # ---- 待推进（7）----
    {"name": "华澜证券", "position": "投资银行部实习生", "zone": "todo_action", "stage": "测评",
     "stage_time": days_ahead(2, 19, 0) + " 前完成"},
    {"name": "中澜基金", "position": "量化研究助理", "zone": "todo_action", "stage": "笔试",
     "stage_time": cn_date(NOW + timedelta(days=4), "上午9:30"),
     "stage_time_locked": 1, "note": "时间已和HR确认，勿改"},
    {"name": "澜镜科技", "position": "AI产品经理", "zone": "todo_action", "stage": "AI面试", "portfolio": 1,
     "stage_time": days_ahead(1, 23, 59) + " 前完成"},
    {"name": "恒信银行", "position": "金融科技岗", "zone": "todo_action", "stage": "一面",
     "stage_time": cn_date(NOW + timedelta(days=3), "下午14:00")},
    {"name": "瑞丰资本", "position": "PE投资分析师", "zone": "todo_action", "stage": "二面",
     "note": "一面反馈不错，重点准备项目深挖"},
    {"name": "启元创投", "position": "投资实习生", "zone": "todo_action", "stage": "终面",
     "stage_time": cn_date(NOW + timedelta(days=6), "上午10:00")},
    {"name": "潮汐量化", "position": "量化交易员", "zone": "todo_action", "stage": "面试"},

    # ---- 只投了简历（6）----
    {"name": "湾区理财", "position": "产品部管培生", "zone": "waiting"},
    {"name": "鹏程保险", "position": "精算助理", "zone": "waiting"},
    {"name": "梧桐创投", "position": "投资助理", "zone": "waiting", "note": "内推渠道，问问学姐进度"},
    {"name": "云杉数据", "position": "数据分析师", "zone": "waiting"},
    {"name": "红树资本", "position": "VC分析师", "zone": "waiting"},
    {"name": "白鹭银行", "position": "公司金融部", "zone": "waiting"},

    # ---- 已推进（等下一步，6）----
    {"name": "岭南通投", "position": "战略投资部", "zone": "waiting_adv", "history": ["已投递", "测评"]},
    {"name": "穗城金控", "position": "管培生", "zone": "waiting_adv", "history": ["已投递", "测评", "笔试"]},
    {"name": "深蓝资管", "position": "固收研究", "zone": "waiting_adv", "history": ["已投递", "笔试"]},
    {"name": "晨曦基金", "position": "渠道销售", "zone": "waiting_adv", "history": ["已投递", "测评", "AI面试"]},
    {"name": "砚山资本", "position": "并购分析师", "zone": "waiting_adv", "history": ["已投递", "笔试", "一面"]},
    {"name": "万泽信托", "position": "信托经理助理", "zone": "waiting_adv", "history": ["已投递", "测评"]},

    # ---- 已完成·已拒绝（5）----
    {"name": "拓疆证券", "position": "研究所助理", "zone": "done"},
    {"name": "海纳资管", "position": "产品经理", "zone": "done", "portfolio": 1},
    {"name": "启航银行", "position": "客户经理", "zone": "done"},
    {"name": "矩阵新元", "position": "算法工程师", "zone": "done"},
    {"name": "金穗期货", "position": "研究员", "zone": "done"},

    # ---- 邮箱演示候选（4）：初始都是「等待/只投了简历」，假邮件会把它们推进 ----
    {"name": "汇川证券", "position": "债券承做", "zone": "email_demo"},
    {"name": "天璇基金", "position": "行业研究员", "zone": "email_demo"},
    {"name": "光年智能", "position": "AI产品经理", "zone": "email_demo", "portfolio": 1},
    {"name": "德润银行", "position": "管培生", "zone": "email_demo"},
]

# 邮箱演示用的假通知（发进演示邮箱；企业名必须和上面完全一致）
# 预期效果：汇川证券→测评、天璇基金→笔试(带时间)、光年智能→AI面试(带截止时间)、德润银行→已拒绝
DEMO_EMAILS = [
    {
        "to_company": "汇川证券",
        "subject": "【汇川证券】2027校园招聘在线测评通知",
        "body": (
            "同学您好：\n\n感谢投递汇川证券2027届校园招聘「债券承做」岗位。\n"
            "现邀请您参加在线测评，请点击链接完成（约40分钟）：https://exam.example.com/hc\n"
            f"请在 {(NOW + timedelta(days=3)).strftime('%Y-%m-%d')} 23:59 前完成，逾期视为放弃。\n\n汇川证券人力资源部"
        ),
    },
    {
        "to_company": "天璇基金",
        "subject": "【天璇基金】笔试通知：行业研究员（2027校招）",
        "body": (
            "您好：\n\n恭喜您通过天璇基金简历筛选，现邀请您参加统一笔试。\n"
            f"笔试时间：{cn_date(NOW + timedelta(days=7), '上午9:30-11:30')}，线上进行。\n"
            f"请提前15分钟登录考试系统，并于 {(NOW + timedelta(days=3)).strftime('%Y-%m-%d')} 24:00 前点击链接确认参加。\n"
            "考试链接：https://exam.example.com/tx\n\n天璇基金招聘组"
        ),
    },
    {
        "to_company": "光年智能",
        "subject": "【光年智能】AI面试邀请 — AI产品经理",
        "body": (
            "同学你好：\n\n感谢你对光年智能「AI产品经理」岗位的关注。\n"
            "本轮为AI视频面试，共5道题，约20分钟，可自选时间完成。\n"
            f"请在 {(NOW + timedelta(days=2)).strftime('%Y-%m-%d')} 23:59 之前尽快完成面试：https://interview.example.com/gn\n"
            "建议使用电脑端 Chrome 浏览器。\n\n光年智能校招团队"
        ),
    },
    {
        "to_company": "德润银行",
        "subject": "【德润银行】2027校园招聘结果通知",
        "body": (
            "同学您好：\n\n感谢您对德润银行2027届校园招聘的关注与投入。\n"
            "经过综合评估，我们很遗憾地通知您，本次「管培生」岗位未能与您进一步匹配。\n"
            "您的简历已收入我行人才库，期待未来有机会再会。\n\n德润银行人力资源部"
        ),
    },
]

FAKE_RESUME = """林晓曼 · 2027届金融硕士

【教育背景】
某985高校 金融硕士（金融科技方向），2025.09 - 2027.06（预计）
某211高校 金融学本科，2021.09 - 2025.06

【实习经历】
某头部券商 · 研究所实习生（2025.06 - 2025.12）
- 协助覆盖银行与非银金融行业，参与撰写行业周报 12 期、公司深度报告 2 篇
- 搭建板块数据跟踪模板，将周度数据整理时间从 3 小时压缩到 40 分钟

某私募基金 · 投后管理实习生（2025.01 - 2025.05）
- 负责 6 个在管项目的季报数据归集与核对，发现并修正 3 处口径不一致问题
- 用 Python 脚本自动化税费返还表的归一化核对，单项目核对耗时下降约 70%

某互联网金融公司 · 数据运营实习生（2024.06 - 2024.12）
- 用 SQL 完成科目余额表与序时账的勾稽校验，定位差异分录 20+ 笔
- 参与用户分层运营项目，协助搭建转化漏斗看板

【项目经历】
秋招流程助手（独立开发，2026）
- 用 Flask + SQLite + DeepSeek API 搭建个人秋招管理工具，管理 70+ 家企业投递进度
- 实现邮箱通知自动识别（IMAP + LLM 三级分类）、8000 条岗位库筛选、AI 智能选岗

【技能】
- 数据分析：SQL（能独立完成多表关联查询与勾稽校验）、Python（pandas/脚本自动化）
- 办公：Excel 高阶函数、Wind、PPT
- 语言：英语六级 560
"""


def seed_companies():
    created = {}
    for spec in COMPANIES:
        c = db.create_company(spec["name"], spec.get("url", ""), spec.get("position", ""),
                              spec.get("deadline", ""))
        cid = c["id"]
        zone = spec["zone"]
        if zone == "todo_action":
            db.advance_company(cid)  # 待投递 → 等待，history=["已投递"]
            # 当前阶段不入 history（入 history 表示「已完成」，会被迁移逻辑回退成等待）
            conn = db._conn()
            conn.execute("UPDATE companies SET stage=?, stage_time=?, stage_time_locked=?, updated_at=? WHERE id=?",
                         (spec["stage"], spec.get("stage_time", ""),
                          1 if spec.get("stage_time_locked") else 0,
                          (NOW - timedelta(days=1)).isoformat(), cid))
            conn.commit()
            conn.close()
        elif zone == "waiting":
            db.advance_company(cid)
            # 等待天数做点区分
            days = 3 + (cid % 12)
            conn = db._conn()
            conn.execute("UPDATE companies SET updated_at=? WHERE id=?",
                         ((NOW - timedelta(days=days)).isoformat(), cid))
            conn.commit()
            conn.close()
        elif zone == "waiting_adv":
            db.advance_company(cid)
            conn = db._conn()
            conn.execute("UPDATE companies SET history=?, updated_at=? WHERE id=?",
                         (json.dumps(spec["history"], ensure_ascii=False),
                          (NOW - timedelta(days=2 + cid % 8)).isoformat(), cid))
            conn.commit()
            conn.close()
        elif zone == "done":
            db.advance_company(cid)
            db.set_stage(cid, "已拒绝")
        elif zone == "email_demo":
            db.advance_company(cid)
        if spec.get("note"):
            db.update_company(cid, note=spec["note"])
        if spec.get("portfolio"):
            db.set_portfolio(cid, True)
        if zone == "todo_action" and spec.get("stage_time"):
            db.set_stage_time(cid, spec["stage_time"])
            if spec.get("stage_time_locked"):
                db.update_company(cid, stage_time_locked=1)
        created[spec["name"]] = cid
    return created


def seed_jobs():
    """复用真实岗位库（公开招聘信息），剥掉个人标注。"""
    src = config.BASE_DIR / "data" / "jobs.json"
    if not src.exists():
        print("  [jobs] 未找到 data/jobs.json，跳过岗位库种子")
        return 0
    rows = json.loads(src.read_text(encoding="utf-8"))
    for i, r in enumerate(rows):
        r["id"] = i
        r["mark"] = ""
        r["note"] = ""
        r.pop("unsuitable", None)
    job_pool.save(rows)
    return len(rows)


def seed_resume():
    resume_store.save([{"name": "金融/AI产品", "content": FAKE_RESUME}])


def write_email_guide():
    """把要发进演示邮箱的假邮件写成指南 + mailto 不便，直接输出 JSON 供发送脚本使用。"""
    out = config.BASE_DIR / "backend" / "demo_emails.json"
    payload = []
    for e in DEMO_EMAILS:
        body = e["body"]
        for en, cn in [("Monday", "周一"), ("Tuesday", "周二"), ("Wednesday", "周三"),
                       ("Thursday", "周四"), ("Friday", "周五"), ("Saturday", "周六"), ("Sunday", "周日")]:
            body = body.replace(en, cn)
        payload.append({"subject": e["subject"], "body": body, "company": e["to_company"]})
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main():
    if config.DATA_DIR.exists() and (config.DATA_DIR / "tasks.db").exists():
        print("demo_data/tasks.db 已存在，将删除重建。")
        (config.DATA_DIR / "tasks.db").unlink()
    db.init_db()
    created = seed_companies()
    n_jobs = seed_jobs()
    seed_resume()
    guide = write_email_guide()

    zones = {}
    for c in db.list_companies():
        zones[c["stage"]] = zones.get(c["stage"], 0) + 1
    print(f"[seed] 企业 {len(created)} 家，阶段分布：{zones}")
    print(f"[seed] 岗位库 {n_jobs} 条（标注已清空）")
    print(f"[seed] 简历 1 份（虚构：林晓曼）")
    print(f"[seed] 演示邮件清单 → {guide}（共 {len(DEMO_EMAILS)} 封，需发进演示邮箱）")


if __name__ == "__main__":
    main()
