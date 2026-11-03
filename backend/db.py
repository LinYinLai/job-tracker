import sqlite3
import json
from datetime import datetime
import config

# 可推进的里程碑阶段（"待投递"推进时记为"已投递"，"等待"是过渡态不入历史）
MILESTONES = ["待投递", "测评", "笔试", "AI面试", "一面", "二面", "终面", "面试"]


def _conn():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT '待投递',
            note TEXT,
            url TEXT DEFAULT '',
            position TEXT DEFAULT '',
            deadline TEXT DEFAULT '',
            stage_time TEXT DEFAULT '',
            stage_time_locked INTEGER DEFAULT 0,
            portfolio INTEGER DEFAULT 0,
            jd TEXT DEFAULT '',
            history TEXT DEFAULT '[]',
            zone_override TEXT DEFAULT '',
            last_email_at TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()]
    if "history" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN history TEXT DEFAULT '[]'")
    if "url" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN url TEXT DEFAULT ''")
    if "position" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN position TEXT DEFAULT ''")
    if "jd" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN jd TEXT DEFAULT ''")
    if "note" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN note TEXT")
    if "deadline" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN deadline TEXT DEFAULT ''")
    if "stage_time" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN stage_time TEXT DEFAULT ''")
    if "stage_time_locked" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN stage_time_locked INTEGER DEFAULT 0")
    if "portfolio" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN portfolio INTEGER DEFAULT 0")
    if "zone_override" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN zone_override TEXT DEFAULT ''")
    conn.commit()
    conn.close()
    _migrate_history()


def _migrate_history():
    """一次性修复旧数据：历史里的「待投递」改成「已投递」，缺「已投递」的补在最前；
    当前阶段若已在历史里（已完成过），回退到「等待」。"""
    conn = _conn()
    for c in conn.execute("SELECT id, history, stage FROM companies").fetchall():
        history = json.loads(c["history"] or "[]")
        if not history:
            continue
        new = ["已投递" if s == "待投递" else s for s in history]
        if new[0] != "已投递":
            new = ["已投递"] + new
        stage = c["stage"]
        if stage in MILESTONES and stage in new and stage != "待投递":
            stage = "等待"
        conn.execute("UPDATE companies SET history=?, stage=? WHERE id=?",
                     (json.dumps(new, ensure_ascii=False), stage, c["id"]))
    conn.commit()
    conn.close()


def create_company(name, url="", position="", deadline=""):
    now = datetime.now().isoformat()
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO companies (name, stage, url, position, deadline, history, created_at, updated_at) "
        "VALUES (?, '待投递', ?, ?, ?, '[]', ?, ?)",
        (name, url, position, deadline, now, now),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return get_company(cid)


def list_companies():
    conn = _conn()
    rows = conn.execute("SELECT * FROM companies ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_company(cid):
    conn = _conn()
    r = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    conn.close()
    return dict(r) if r else None


def set_stage(cid, stage):
    now = datetime.now().isoformat()
    conn = _conn()
    conn.execute("UPDATE companies SET stage=?, updated_at=? WHERE id=?", (stage, now, cid))
    conn.commit()
    conn.close()


def set_stage_time(cid, stage_time):
    conn = _conn()
    conn.execute("UPDATE companies SET stage_time=? WHERE id=?", (stage_time, cid))
    conn.commit()
    conn.close()


def set_stage_time_locked(cid, val):
    conn = _conn()
    conn.execute("UPDATE companies SET stage_time_locked=? WHERE id=?", (1 if val else 0, cid))
    conn.commit()
    conn.close()


def set_portfolio(cid, val):
    conn = _conn()
    conn.execute("UPDATE companies SET portfolio=? WHERE id=?", (1 if val else 0, cid))
    conn.commit()
    conn.close()


def set_zone(cid, zone):
    """手动指定所在区域（zone_override）；传空串清除，回到按阶段自动分区。"""
    conn = _conn()
    conn.execute("UPDATE companies SET zone_override=? WHERE id=?", (zone or "", cid))
    conn.commit()
    conn.close()
    return get_company(cid)


def advance_company(cid):
    """完成当前里程碑：加入历史，进入等待。待投递 → 记为「已投递」。"""
    c = get_company(cid)
    if not c:
        return None
    if c["stage"] == "待投递":
        milestone = "已投递"
    elif c["stage"] in MILESTONES:
        milestone = c["stage"]
    else:
        return get_company(cid)  # 等待/已拒绝 → 无操作
    history = json.loads(c.get("history") or "[]")
    if milestone not in history:
        history.append(milestone)
    now = datetime.now().isoformat()
    conn = _conn()
    conn.execute(
        "UPDATE companies SET stage='等待', history=?, updated_at=? WHERE id=?",
        (json.dumps(history, ensure_ascii=False), now, cid),
    )
    conn.commit()
    conn.close()
    return get_company(cid)


def update_company(cid, url=None, position=None, jd=None, name=None, note=None, deadline=None, stage_time=None, stage_time_locked=None):
    c = get_company(cid)
    if not c:
        return None
    name = c["name"] if not name else name
    url = c["url"] if url is None else url
    position = c["position"] if position is None else position
    jd = c["jd"] if jd is None else jd
    note = c["note"] if note is None else note
    deadline = c["deadline"] if deadline is None else deadline
    stage_time = c["stage_time"] if stage_time is None else stage_time
    stage_time_locked = c["stage_time_locked"] if stage_time_locked is None else (1 if stage_time_locked else 0)
    conn = _conn()
    conn.execute("UPDATE companies SET name=?, url=?, position=?, jd=?, note=?, deadline=?, stage_time=?, stage_time_locked=? WHERE id=?", (name, url, position, jd, note, deadline, stage_time, stage_time_locked, cid))
    conn.commit()
    conn.close()
    return get_company(cid)


def delete_company(cid):
    conn = _conn()
    conn.execute("DELETE FROM companies WHERE id=?", (cid,))
    conn.commit()
    conn.close()
