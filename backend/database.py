"""SQLite 数据库操作"""

import aiosqlite
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "survey.db")


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接"""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db():
    """初始化数据库表"""
    db = await get_db()
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                company TEXT NOT NULL,
                position TEXT NOT NULL,
                qa_history TEXT NOT NULL DEFAULT '[]',
                analysis_summary TEXT,
                analysis_insights TEXT,
                pain_points TEXT DEFAULT '[]',
                follow_up_advice TEXT DEFAULT '',
                lead_level TEXT DEFAULT '普通',
                lead_score INTEGER DEFAULT 50,
                follow_status TEXT DEFAULT 'new',
                follow_note TEXT DEFAULT '',
                is_completed INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        # 兼容旧表结构，动态添加缺失的列
        await _migrate_columns(db)
        await db.commit()
    finally:
        await db.close()


async def _migrate_columns(db: aiosqlite.Connection):
    """兼容旧表：添加新字段"""
    existing = await db.execute("PRAGMA table_info(surveys)")
    cols = {row["name"] for row in await existing.fetchall()}
    new_cols = {
        "pain_points": "TEXT DEFAULT '[]'",
        "follow_up_advice": "TEXT DEFAULT ''",
        "lead_level": "TEXT DEFAULT '普通'",
        "lead_score": "INTEGER DEFAULT 50",
        "follow_status": "TEXT DEFAULT 'new'",
        "follow_note": "TEXT DEFAULT ''",
    }
    for col, col_def in new_cols.items():
        if col not in cols:
            await db.execute(f"ALTER TABLE surveys ADD COLUMN {col} {col_def}")


async def save_user_info(session_id: str, name: str, company: str, position: str):
    """保存用户基本信息"""
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO surveys (session_id, name, company, position, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, name, company, position, datetime.now().isoformat())
        )
        await db.commit()
    finally:
        await db.close()


async def save_answer(session_id: str, question_number: int, question: str, answer: str):
    """追加一条问答记录"""
    db = await get_db()
    try:
        row = await db.execute(
            "SELECT qa_history FROM surveys WHERE session_id = ?",
            (session_id,)
        )
        result = await row.fetchone()
        if result:
            qa_history = json.loads(result["qa_history"])
            qa_history.append({
                "question_number": question_number,
                "question": question,
                "answer": answer
            })
            await db.execute(
                "UPDATE surveys SET qa_history = ? WHERE session_id = ?",
                (json.dumps(qa_history, ensure_ascii=False), session_id)
            )
            await db.commit()
    finally:
        await db.close()


async def get_qa_history(session_id: str) -> list[dict]:
    """获取问答历史"""
    db = await get_db()
    try:
        row = await db.execute(
            "SELECT qa_history FROM surveys WHERE session_id = ?",
            (session_id,)
        )
        result = await row.fetchone()
        if result:
            return json.loads(result["qa_history"])
        return []
    finally:
        await db.close()


async def get_user_info(session_id: str) -> dict | None:
    """获取用户信息"""
    db = await get_db()
    try:
        row = await db.execute(
            "SELECT name, company, position FROM surveys WHERE session_id = ?",
            (session_id,)
        )
        result = await row.fetchone()
        if result:
            return {"name": result["name"], "company": result["company"], "position": result["position"]}
        return None
    finally:
        await db.close()


async def save_analysis(session_id: str, analysis: dict):
    """保存完整分析结果（含线索评级）"""
    db = await get_db()
    try:
        await db.execute(
            """UPDATE surveys
               SET analysis_summary = ?,
                   analysis_insights = ?,
                   pain_points = ?,
                   follow_up_advice = ?,
                   lead_level = ?,
                   lead_score = ?,
                   is_completed = 1,
                   completed_at = ?
               WHERE session_id = ?""",
            (
                analysis.get("summary", ""),
                json.dumps(analysis.get("insights", []) + analysis.get("suggestions", []), ensure_ascii=False),
                json.dumps(analysis.get("pain_points", []), ensure_ascii=False),
                analysis.get("follow_up_advice", ""),
                analysis.get("lead_level", "普通"),
                analysis.get("lead_score", 50),
                datetime.now().isoformat(),
                session_id
            )
        )
        await db.commit()
    finally:
        await db.close()


async def update_follow_status(session_id: str, status: str, note: str = ""):
    """更新跟进状态"""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE surveys SET follow_status = ?, follow_note = ? WHERE session_id = ?",
            (status, note, session_id)
        )
        await db.commit()
    finally:
        await db.close()


async def get_stats() -> dict:
    """管理后台统计数据"""
    db = await get_db()
    try:
        total = await db.execute("SELECT COUNT(*) as c FROM surveys WHERE is_completed = 1")
        total_count = (await total.fetchone())["c"]

        high = await db.execute(
            "SELECT COUNT(*) as c FROM surveys WHERE is_completed = 1 AND lead_level = '高优'"
        )
        high_count = (await high.fetchone())["c"]

        mid = await db.execute(
            "SELECT COUNT(*) as c FROM surveys WHERE is_completed = 1 AND lead_level = '中优'"
        )
        mid_count = (await mid.fetchone())["c"]

        followed = await db.execute(
            "SELECT COUNT(*) as c FROM surveys WHERE follow_status != 'new'"
        )
        followed_count = (await followed.fetchone())["c"]

        companies = await db.execute(
            "SELECT COUNT(DISTINCT company) as c FROM surveys WHERE is_completed = 1"
        )
        company_count = (await companies.fetchone())["c"]

        return {
            "total": total_count,
            "high_priority": high_count,
            "mid_priority": mid_count,
            "followed": followed_count,
            "companies": company_count
        }
    finally:
        await db.close()


async def get_all_surveys() -> list[dict]:
    """获取所有问卷记录"""
    db = await get_db()
    try:
        rows = await db.execute(
            "SELECT * FROM surveys ORDER BY lead_score DESC, created_at DESC"
        )
        results = await rows.fetchall()
        return [dict(r) for r in results]
    finally:
        await db.close()


async def export_surveys_csv() -> str:
    """导出所有问卷数据为 CSV 字符串"""
    db = await get_db()
    try:
        rows = await db.execute(
            """SELECT name, company, position, qa_history, analysis_summary,
                      pain_points, follow_up_advice, lead_level, lead_score,
                      follow_status, is_completed, created_at, completed_at
               FROM surveys ORDER BY created_at DESC"""
        )
        results = await rows.fetchall()

        headers = [
            "姓名", "企业", "岗位", "线索等级", "评分",
            "问卷答案", "分析摘要", "痛点", "跟进建议",
            "跟进状态", "是否完成", "创建时间", "完成时间"
        ]

        def csv_escape(val):
            """CSV 转义"""
            s = str(val or "").replace('"', '""')
            return f'"{s}"'

        lines = [",".join(csv_escape(h) for h in headers)]

        status_map = {"new": "待跟进", "contacted": "已联系", "followed": "已跟进", "closed": "已关闭"}

        for r in results:
            d = dict(r)
            # 格式化问答
            qa_str = ""
            try:
                qa_list = json.loads(d.get("qa_history", "[]"))
                qa_parts = []
                for qa in qa_list:
                    qa_parts.append(f"Q{qa.get('question_number','')}: {qa.get('question','')} → {qa.get('answer','')}")
                qa_str = " | ".join(qa_parts)
            except (json.JSONDecodeError, KeyError):
                qa_str = d.get("qa_history", "")

            # 格式化痛点
            pain_str = ""
            try:
                pain_list = json.loads(d.get("pain_points", "[]"))
                pain_str = "；".join(pain_list)
            except (json.JSONDecodeError, KeyError):
                pain_str = d.get("pain_points", "")

            row = [
                d.get("name", ""),
                d.get("company", ""),
                d.get("position", ""),
                d.get("lead_level", ""),
                d.get("lead_score", ""),
                qa_str,
                d.get("analysis_summary", ""),
                pain_str,
                d.get("follow_up_advice", ""),
                status_map.get(d.get("follow_status", ""), d.get("follow_status", "")),
                "是" if d.get("is_completed") else "否",
                (d.get("created_at", "") or "")[:19],
                (d.get("completed_at", "") or "")[:19],
            ]
            lines.append(",".join(csv_escape(str(v)) for v in row))

        return "\n".join(lines)
    finally:
        await db.close()
