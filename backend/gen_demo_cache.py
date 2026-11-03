"""生成演示模式的 AI 预置缓存（用真实 key 跑一次，结果写进 backend/demo_cache/）。

用法（在 backend/ 目录下，不要设 DEMO_MODE）：
    python gen_demo_cache.py

注意：本脚本以「真实模式」运行（用真实 LLM key 调 API），
但读取的企业/简历全部来自 demo_data/（虚构数据），不涉及真实投递记录。
"""
import json
import sqlite3
import sys
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent))
assert not __import__("os").environ.get("DEMO_MODE"), "不要在 DEMO_MODE 下运行本脚本"

import ai_assistant  # noqa: E402
import config  # noqa: E402

DEMO_DB = config.BASE_DIR / "demo_data" / "tasks.db"
CACHE = Path(__file__).resolve().parent / "demo_cache"

# 为这些企业预生成面试准备包；_default 作为任意企业的兜底展示
PREP_TARGETS = {
    "澜镜科技": "AI产品经理",
    "恒信银行": "金融科技岗",
    "瑞丰资本": "PE投资分析师",
    "_default": "投研管培生",
}


def demo_companies():
    conn = sqlite3.connect(DEMO_DB)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM companies").fetchall()]
    conn.close()
    return rows


def fake_resume():
    p = config.BASE_DIR / "demo_data" / "resumes.json"
    return json.loads(p.read_text(encoding="utf-8"))[0]["content"]


def gen_weekly(companies):
    print("[cache] 周报分类中（搜索+AI，约 1-2 分钟）…")
    report = ai_assistant.generate_weekly_report(companies)
    (CACHE / "weekly_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  -> weekly_report.json（{report['total']} 家）")


def gen_recommend(resume):
    print("[cache] 智能选岗中…")
    rec = ai_assistant.recommend_jobs(resume, "")
    (CACHE / "recommend.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  -> recommend.json（金融 {len(rec['finance'])} / AI {len(rec['ai'])} / 热门 {len(rec['hot'])}）")


def gen_preps(resume):
    (CACHE / "interview_prep").mkdir(parents=True, exist_ok=True)
    template = ai_assistant.DEFAULT_INTERVIEW_PREP_PROMPT
    for name, pos in PREP_TARGETS.items():
        print(f"[cache] 面试准备：{name}（{pos}）…")
        prompt = Template(template).safe_substitute(
            resume=resume[:2000], name=name if name != "_default" else "巨石基金",
            pos=pos, jd="（未填写）")
        text = ai_assistant._deepseek(prompt, timeout=120)
        (CACHE / "interview_prep" / f"{name}.txt").write_text(text, encoding="utf-8")
        print(f"  -> interview_prep/{name}.txt（{len(text)} 字）")


def gen_portfolio(companies):
    print("[cache] 作品集岗位识别中…")
    ids = set(ai_assistant.classify_portfolio_batch(companies))
    names = [c["name"] for c in companies if c["id"] in ids]
    (CACHE / "portfolio.json").write_text(
        json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  -> portfolio.json（{len(names)} 家：{'、'.join(names)}）")


def main():
    if not DEMO_DB.exists():
        print("demo_data/tasks.db 不存在，先运行 seed_demo.py")
        return
    CACHE.mkdir(exist_ok=True)
    companies = demo_companies()
    resume = fake_resume()
    gen_weekly(companies)
    gen_recommend(resume)
    gen_preps(resume)
    gen_portfolio(companies)
    print("[cache] 全部完成 →", CACHE)


if __name__ == "__main__":
    main()
