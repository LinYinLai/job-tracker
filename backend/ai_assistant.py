"""AI 功能：面试准备包 + 秋招进度周报。"""
import json
import re
from pathlib import Path
from string import Template
import requests
import config
import resume_store
import settings_store
import job_pool

DEMO_CACHE_DIR = Path(__file__).resolve().parent / "demo_cache"


def _demo_read_json(name):
    """演示模式：读预生成的 AI 结果缓存（JSON）。非演示模式或缓存不存在返回 None。"""
    if not config.DEMO_MODE:
        return None
    p = DEMO_CACHE_DIR / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _demo_read_text(name):
    """演示模式：读预生成的 AI 结果缓存（纯文本）。"""
    if not config.DEMO_MODE:
        return None
    p = DEMO_CACHE_DIR / name
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None


def _deepseek_search(query, count=5):
    """Search 接口（默认 DeepSeek，key 可单独配置，留空则复用 LLM key）。"""
    key = settings_store.get_search_key()
    if not key:
        raise RuntimeError("未配置搜索 API Key")
    resp = requests.post(
        settings_store.get_search_base_url(),
        headers={"Authorization": f"Bearer {key}"},
        json={"query": query, "count": count, "need_content": False},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def _deepseek(prompt, timeout=60):
    key = settings_store.get_llm_key()
    if not key:
        raise RuntimeError("未配置 LLM_API_KEY")
    base_url = settings_store.get_llm_base_url()
    model = settings_store.get_llm_model()
    resp = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


DEFAULT_INTERVIEW_PREP_PROMPT = (
    "你是专业的秋招面试辅导教练。请根据我的简历，帮我生成一份面试准备材料。\n\n"
    "【我的简历】\n$resume\n\n"
    "【应聘公司与岗位】\n公司：$name\n岗位：$pos\nJD：$jd\n\n"
    "请严格按照以下框架生成，整体用 markdown 输出。\n\n"
    "【总要求】\n"
    "- 所有需要口述的完整回答，控制在约 100 秒（约 250-300 字），用自然、口语化的表达，"
    "像面对面说话一样，不要书面化、不要像念稿、不要堆砌形容词。\n"
    "- 经历类回答一律用 STAR 法则（情境-任务-行动-结果），结果尽量量化。\n"
    "- 只根据我的真实简历来写经历，不要编造。\n\n"
    "# 第一部分\n\n"
    "## 1. 自我介绍\n"
    "根据我的简历写一段完整、自然的自我介绍（约 100 秒），作为每次面试都固定使用的版本。\n\n"
    "## 2. 对该公司的了解？为什么选择这个岗位？\n"
    "这一题只给【准备提示词】，不要替我写完整答案。请列出：\n"
    "- 我需要提前了解该公司的哪些要点（主营业务、近期动态、企业文化/价值观、行业地位）\n"
    "- 回答「为什么选这个岗位」的框架（从我的背景如何自然衔接到这个岗位）\n\n"
    "## 3. 你在这个岗位上的优势？\n"
    "这一题只给【准备提示词】，不要替我写完整答案。请：\n"
    "- 根据 JD 提炼出这个岗位最看重的 2-3 项能力\n"
    "- 分别提示我可以从简历里匹配哪段经历来支撑\n\n"
    "# 第二部分：宝洁八大问\n\n"
    "针对下面 8 个问题，每个都用我简历里的真实经历，写一个完整、口语化的 STAR 回答（约 100 秒）；"
    "并在每个回答之后，单独列出「面试官可能追问的 3 个问题」。\n"
    "1. 请举例说明你如何制定了一个高目标，并为之努力最终实现它。\n"
    "2. 请举例说明你如何领导一个团队完成一项任务。\n"
    "3. 请举例说明你如何搜集信息、分析问题，并做出决策。\n"
    "4. 请举例说明你如何说服他人接受你的观点或方案。\n"
    "5. 请举例说明你如何与他人合作，共同完成一个目标。\n"
    "6. 请举例说明你如何创造性地解决了一个问题。\n"
    "7. 请举例说明你如何快速学习一项新知识或技能，并应用到实践中。\n"
    "8. 请举例说明你如何在压力下完成任务。\n\n"
    "# 第三部分：反问面试官\n\n"
    "准备 3 个有深度、能体现你认真思考的反问问题"
    "（关于岗位成长路径、团队协作方式、业务方向、入职后的期待等），直接列出即可，不要解释。"
)


def generate_interview_prep(name, position, jd=""):
    """生成某公司的面试准备包（三部分框架：基础问答 + 宝洁八大问 + 反问）。"""
    if config.DEMO_MODE:
        cached = _demo_read_text(f"interview_prep/{name}.txt") or _demo_read_text("interview_prep/_default.txt")
        if cached is not None:
            return cached
    pos = position or name
    resume = _resume_for(pos)
    jd_text = (jd or "").strip()
    template = settings_store.get_prompt("interview_prep_prompt", DEFAULT_INTERVIEW_PREP_PROMPT)
    prompt = Template(template).safe_substitute(
        resume=resume[:2000],
        name=name,
        pos=pos,
        jd=jd_text[:1000] if jd_text else "（未填写）",
    )
    return _deepseek(prompt)


def _resume_for(position):
    """按岗位方向匹配简历，无匹配则返回第一份。"""
    resumes = resume_store.load()
    if not resumes:
        return ""
    for r in resumes:
        if position and (r["name"] in position or position in r["name"]):
            return r["content"]
    return resumes[0]["content"]


NATURE_RULES = [
    ("银行", ["银行"]),
    ("券商", ["证券"]),
    ("保险", ["保险"]),
    ("基金/资管/PE-VC", ["基金", "资管", "信托", "理财", "财富", "资本", "创投", "私募", "股权投资"]),
    ("国企", ["燃气", "建筑", "石油", "石化", "电力", "华油", "中铁", "中建", "中交", "中化", "国家电网", "中国移动", "中国联通", "中国电信", "船舶", "航空", "核电", "国家开发", "期货", "交易所"]),
    ("互联网/科技", ["腾讯", "字节", "美团", "京东", "阿里", "百度", "网易", "滴滴", "快手", "拼多多", "小红书", "哔哩", "Shopee", "科技", "信息", "软件", "数据", "智能", "网络"]),
]

# 大厂名单（依据：行业头部/龙头，员工通常 >1 万人）
BIG_COMPANY = [
    # 国有大行 + 政策性银行
    "工商银行", "建设银行", "农业银行", "中国银行", "交通银行", "邮储银行", "国家开发银行", "进出口银行", "农业发展银行",
    # 股份制大行
    "招商银行", "浦发银行", "中信银行", "民生银行", "兴业银行", "光大银行", "平安银行", "华夏银行", "广发银行", "浙商银行",
    # 头部券商
    "中信证券", "中信建投", "国泰君安", "华泰证券", "广发证券", "招商证券", "中金", "海通", "申万宏源", "国信证券", "国泰海通", "东方财富", "银河证券", "兴业证券",
    # 头部公募基金
    "易方达", "华夏基金", "南方基金", "广发基金", "嘉实", "中欧基金", "汇添富", "富国", "博时", "招商基金", "天弘", "工银瑞信", "建信基金",
    # 头部保险
    "中国人寿", "中国人保", "中国平安", "中国太保", "新华保险", "泰康",
    # 互联网巨头
    "腾讯", "阿里", "字节", "美团", "京东", "百度", "网易", "拼多多", "快手", "滴滴", "华为", "小米", "小红书", "哔哩", "蚂蚁",
    # 大型国企/央企
    "中国石油", "中国石化", "国家电网", "中国建筑", "中铁", "中交", "中国移动", "中国联通", "中国电信", "中海油", "招商局", "华润", "保利",
    # 头部 PE/VC
    "高瓴", "红杉", "IDG", "经纬", "深创投", "达晨", "启明", "真格", "鼎晖", "华兴",
]

STARTUP = ["初创", "创业", "天使"]


def classify_nature(name):
    for nature, kws in NATURE_RULES:
        if any(k in name for k in kws):
            return nature
    return "其他"


def classify_scale(name):
    if any(k in name for k in STARTUP):
        return "初创"
    if any(k in name for k in BIG_COMPANY):
        return "大厂"
    return "中厂"


TECH_KEYWORDS = ["技术", "研发", "算法", "数据", "AI", "人工智能", "量化", "工程师", "开发", "编程", "代码", "软件", "机器学习", "金融科技", "系统", "网络", "模型", "IT", "测试", "运维"]
JD_TECH_KEYWORDS = ["编程", "Python", "SQL", "算法", "机器学习", "开发", "代码", "数据分析", "模型", "深度学习", "大数据"]


def classify_tech(position, jd):
    """判断岗位是否有技术要求（岗位名 + JD 关键词）。返回 '技术岗' / '非技术岗'。"""
    p = (position or "").strip()
    if any(k in p for k in TECH_KEYWORDS):
        return "技术岗"
    if jd and any(k in jd for k in JD_TECH_KEYWORDS):
        return "技术岗"
    return "非技术岗"


# 金融机构性质（这些性质的公司不可能是"初创"）
FINANCIAL_NATURES = {"银行", "券商", "基金/资管/PE-VC", "保险", "国企"}


NATURE_ALIASES = {
    "银行": "银行", "券商": "券商", "证券": "券商", "保险": "保险",
    "基金": "基金/资管/PE-VC", "基金资管": "基金/资管/PE-VC", "基金/资管": "基金/资管/PE-VC",
    "资管": "基金/资管/PE-VC", "PE-VC": "基金/资管/PE-VC", "PE/VC": "基金/资管/PE-VC", "私募": "基金/资管/PE-VC",
    "国企": "国企", "国有": "国企",
    "互联网": "互联网/科技", "互联网/科技": "互联网/科技", "科技": "互联网/科技",
    "其他": "其他",
}

SCALE_ALIASES = {
    "大厂": "大厂", "大型": "大厂",
    "中厂": "中厂", "中型": "中厂",
    "初创": "初创", "创业": "初创", "小型": "初创",
}


def normalize_nature(n):
    return NATURE_ALIASES.get(n, "其他")


def normalize_scale(s):
    return SCALE_ALIASES.get(s, "中厂")


def classify_all(companies):
    """对全部企业分类，返回 {name: {nature, scale, tech, position}}。"""
    result = {}
    ambiguous = []  # 性质含糊（关键词归"其他"）→ 搜索 + AI
    scale_uncertain = []  # 规模默认"中厂" → AI 批量判断
    for c in companies:
        name = c["name"]
        position = (c.get("position") or "").strip()
        n = classify_nature(name)
        s = classify_scale(name)
        tech = classify_tech(position, c.get("jd", ""))
        result[name] = {"nature": n, "scale": s, "tech": tech, "position": position}
        if n == "其他":
            ambiguous.append(name)
        elif s == "中厂":
            scale_uncertain.append(name)
    if ambiguous:
        ai = ai_classify_batch(ambiguous)
        for name in ambiguous:
            cls = ai.get(name) or {}
            result[name]["nature"] = normalize_nature(cls.get("nature") or "其他")
            result[name]["scale"] = normalize_scale(cls.get("scale") or "中厂")
    if scale_uncertain:
        sm = ai_classify_scale_batch(scale_uncertain)
        for name in scale_uncertain:
            result[name]["scale"] = normalize_scale(sm.get(name) or "中厂")
    # 修正：金融机构（银行/券商/基金/保险/国企等）不可能是"初创"
    for cls in result.values():
        if cls["nature"] in FINANCIAL_NATURES and cls["scale"] == "初创":
            cls["scale"] = "中厂"
    return result


def generate_weekly_report(companies):
    """生成秋招周报结构化数据（含每类下的公司名单）。"""
    cached = _demo_read_json("weekly_report.json")
    if cached is not None:
        return cached
    classification = classify_all(companies)
    nature_counts = {}
    scale_counts = {}
    tech_counts = {}
    nature_detail = {}
    scale_detail = {}
    tech_detail = {}
    for name, cls in classification.items():
        n = cls["nature"]
        s = cls["scale"]
        t = cls.get("tech", "非技术岗")
        pos = cls.get("position", "")
        label = f"{name}（{pos}）" if pos else name
        nature_counts[n] = nature_counts.get(n, 0) + 1
        scale_counts[s] = scale_counts.get(s, 0) + 1
        tech_counts[t] = tech_counts.get(t, 0) + 1
        nature_detail.setdefault(n, []).append(label)
        scale_detail.setdefault(s, []).append(label)
        tech_detail.setdefault(t, []).append(label)
    stage_counts = {"待投递": 0, "进行中": 0, "等待": 0, "已拒绝": 0}
    for c in companies:
        st = c["stage"]
        if st == "待投递":
            stage_counts["待投递"] += 1
        elif st == "已拒绝":
            stage_counts["已拒绝"] += 1
        elif st == "等待":
            stage_counts["等待"] += 1
        else:
            stage_counts["进行中"] += 1
    summary = _generate_summary(nature_counts, scale_counts, tech_counts, stage_counts, len(companies))
    return {
        "total": len(companies),
        "nature": nature_counts,
        "scale": scale_counts,
        "tech": tech_counts,
        "nature_detail": nature_detail,
        "scale_detail": scale_detail,
        "tech_detail": tech_detail,
        "stage": stage_counts,
        "summary": summary,
    }


def ai_classify_scale_batch(names):
    """对一批名字做规模判断（DeepSeek 搜索 + DeepSeek 批量判断，保证准确）。"""
    lines = []
    for n in names:
        info = ""
        try:
            rs = _deepseek_search(f"{n} 公司 规模 员工人数 成立时间")
            info = "；".join((r.get("summary") or r.get("title") or "")[:200] for r in rs[:3])
        except Exception:
            pass
        lines.append(f"- {n}：{info}")
    prompt = (
        "判断下面每家公司的规模，只回复大厂/中厂/初创。\n"
        "判断依据（普遍认知）：\n"
        "- 大厂：行业头部/龙头，员工通常 1 万人以上（国有大行、头部券商、头部公募、互联网巨头、大型央企）\n"
        "- 中厂：中等规模，员工约 1000-1 万人，有一定知名度\n"
        "- 初创：成立时间短、规模小，员工通常几百人以内\n\n"
        + "\n".join(lines) +
        '\n\n只返回 JSON 对象，格式：{"公司名":"大厂/中厂/初创", ...}，不要其他内容。'
    )
    answer = _deepseek(prompt)
    try:
        m = re.search(r"\{.*\}", answer, re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}


def ai_classify_batch(names):
    """对一批含糊的企业名做 AI 分类（DeepSeek 搜索 + DeepSeek 批量判断）。"""
    lines = []
    for n in names:
        info = ""
        try:
            rs = _deepseek_search(f"{n} 公司 简介")
            info = "；".join((r.get("summary") or r.get("title") or "")[:200] for r in rs[:3])
        except Exception:
            pass
        lines.append(f"- {n}：{info}")
    prompt = (
        "你是企业信息分析助手。根据下面的公司名和搜索到的简介，判断每家公司的两个属性：\n"
        "1. nature（企业性质）：银行/券商/保险/基金资管/PE-VC/国企/互联网/科技/其他\n"
        "2. scale（规模）：大厂/中厂/初创\n\n"
        + "\n".join(lines) +
        '\n\n只返回 JSON 对象，格式：{"公司名":{"nature":"...","scale":"..."}, ...}，不要其他内容。'
    )
    answer = _deepseek(prompt)
    try:
        m = re.search(r"\{.*\}", answer, re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}


DEFAULT_WEEKLY_SUMMARY_PROMPT = (
    "你是秋招进度分析助手。根据下面数据，用3-4句话给出简洁的复盘建议。"
    "纯文本输出，不要markdown符号、不要列表符号、不要标题。\n"
    "共 $total 家。企业性质分布：$nature_counts。规模分布：$scale_counts。"
    "岗位技术分布：$tech_counts。阶段分布：$stage_counts。"
)


def _generate_summary(nature_counts, scale_counts, tech_counts, stage_counts, total):
    try:
        template = settings_store.get_prompt("weekly_summary_prompt", DEFAULT_WEEKLY_SUMMARY_PROMPT)
        prompt = Template(template).safe_substitute(
            total=str(total),
            nature_counts=str(nature_counts),
            scale_counts=str(scale_counts),
            tech_counts=str(tech_counts),
            stage_counts=str(stage_counts),
        )
        return _deepseek(prompt).strip()
    except Exception:
        return ""


FINANCE_KW = ["金融", "投资", "基金", "证券", "银行", "研究", "分析", "投研", "固收", "量化", "交易", "风险", "信用", "资管", "理财", "财富", "保险", "信托", "期货", "投行", "研究员", "PE", "VC", "策略", "资产", "并购", "融资", "资本"]
AI_KW = ["AI", "人工智能", "算法", "大模型", "机器学习", "深度学习", "智能", "模型", "AIGC", "生成式", "提示词", "智能体", "数据科学", "NLP", "计算机视觉", "AI产品", "AI应用"]
HOT_KW = ["新能源", "储能", "光伏", "芯片", "半导体", "集成电路", "自动驾驶", "具身智能", "机器人", "低空经济", "无人机", "跨境电商", "出海", "直播", "短视频", "新媒体", "游戏", "大健康", "生物医药", "双碳", "智能硬件", "消费电子", "智能汽车", "元宇宙"]


def _kw_score(job, kws):
    hay = " ".join([job.get("position", ""), job.get("industry", ""), job.get("major", ""), job.get("nature", "")])
    return sum(1 for k in kws if k in hay)


def recommend_jobs(resume, requirement=""):
    """智能选岗：按简历+要求，从岗位库推荐，分成金融/AI/热门新兴三类。"""
    cached = _demo_read_json("recommend.json")
    if cached is not None:
        return cached
    jobs = job_pool.load()
    pool = [j for j in jobs
            if not j.get("unsuitable")
            and "2027届" in j.get("year", "")
            and "硕士" in j.get("education", "")]
    if not pool:
        return {"finance": [], "ai": [], "hot": []}

    finance = sorted(pool, key=lambda j: -_kw_score(j, FINANCE_KW))[:80]
    ai = sorted(pool, key=lambda j: -_kw_score(j, AI_KW))[:80]
    hot = sorted(pool, key=lambda j: -_kw_score(j, HOT_KW))[:80]
    seen = set()
    candidates = []
    for j in finance + ai + hot:
        key = (j["company"], j["position"])
        if key not in seen:
            seen.add(key)
            candidates.append(j)
    candidates = candidates[:220]

    lines = []
    for i, j in enumerate(candidates):
        loc = (j.get("location") or "").split(",")[0]
        ind = (j.get("industry") or "").split(",")[0]
        lines.append(f"{i}|{j['company']}|{(j.get('position') or '')[:40]}|{ind}|{j.get('nature', '')}|{loc}")

    prompt = (
        "你是智能选岗助手。根据我的简历和求职要求，从候选岗位里推荐，分成三类：\n\n"
        f"【我的简历】\n{resume[:2000]}\n\n"
        f"【求职要求】\n{requirement or '（未指定，默认按简历：金融/投资 + AI 产品方向）'}\n\n"
        "【候选岗位】每行：编号|公司|岗位|行业|性质|地点\n"
        + "\n".join(lines) +
        "\n\n【输出要求】只返回一个 JSON 对象，不要任何其他文字，格式：\n"
        '{"finance":[{"id":编号,"reason":"一句话理由"}],"ai":[...],"hot":[...]}\n'
        "finance=金融相关岗位（基金/资管/银行/证券/保险/PE·VC/投资/研究等，8-15 个）；"
        "ai=AI 相关岗位（AI 产品经理、算法、大模型、机器学习、AIGC 等，8-15 个）；"
        "hot=热门或新兴岗位（新能源、芯片半导体、机器人、跨境电商、直播新媒体等，8-15 个）。"
        "三类不重复，reason 用中文一句话说明为什么适合我。"
    )
    answer = _deepseek(prompt, timeout=120)
    m = re.search(r"\{.*\}", answer, re.S)
    data = json.loads(m.group(0)) if m else {}

    def to_jobs(items):
        out = []
        for it in items:
            try:
                idx = int(it.get("id"))
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx >= len(candidates):
                continue
            out.append({**candidates[idx], "reason": it.get("reason", "")})
        return out

    return {
        "finance": to_jobs(data.get("finance", [])),
        "ai": to_jobs(data.get("ai", [])),
        "hot": to_jobs(data.get("hot", [])),
    }


def classify_portfolio_batch(companies):
    """判断哪些岗位需要作品集，返回需要作品集的公司 id 列表。"""
    if not companies:
        return []
    cached = _demo_read_json("portfolio.json")
    if cached is not None:
        by_name = {c["name"]: c["id"] for c in companies}
        return [by_name[n] for n in cached if n in by_name]
    lines = []
    for i, c in enumerate(companies):
        pos = (c.get("position") or "").strip()
        lines.append(f"{i}|{c['name']}|{pos[:60]}")
    prompt = (
        "下面是一些企业的招聘岗位。请判断哪些岗位通常「需要作品集/作品展示」来证明能力。\n"
        "重点识别：产品经理、AI产品经理、运营、用户增长、设计、交互、视觉、市场/营销、内容、新媒体等岗位。\n"
        "传统金融/投资/研究/审计/纯技术开发/职能等岗位通常不需要作品集，不要标注。\n"
        "只返回一个 JSON 数组（需要作品集的岗位编号），例如 [0,3,5]；没有则返回 []。\n\n"
        + "\n".join(lines)
    )
    answer = _deepseek(prompt)
    m = re.search(r"\[.*\]", answer, re.S)
    if not m:
        return []
    try:
        ids = json.loads(m.group(0))
    except Exception:
        return []
    return [companies[i]["id"] for i in ids if isinstance(i, int) and 0 <= i < len(companies)]
