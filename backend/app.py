"""FastAPI 主应用：智能制造调查问卷智能体"""

import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# 路径常量
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

from models import (
    StartSessionRequest, Answer, QuestionResponse,
    AnalysisResult, SessionInfo
)
from database import (
    init_db, save_user_info, save_answer, get_qa_history,
    get_user_info, save_analysis, get_all_surveys, get_stats, update_follow_status
)
from ai_service import generate_all_questions, analyze_answers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    await init_db()
    yield


app = FastAPI(
    title="智能制造调查问卷智能体",
    description="面向智能制造行业的智能问卷调查系统",
    version="2.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 会话缓存: session_id -> {user_info, current_question, questions[], qa_history[]}
sessions: dict[str, dict] = {}


# ==================== API 路由 ====================

@app.post("/api/session/start")
async def start_session(req: StartSessionRequest):
    """开始问卷：保存基本信息，一次性生成全部 4 道选择题，返回第 1 题"""
    session_id = uuid.uuid4().hex[:12]

    # 保存基本信息到数据库
    await save_user_info(session_id, req.name, req.company, req.position)

    user_info = {"name": req.name, "company": req.company, "position": req.position}

    # 一次性生成全部 4 道题
    questions = await generate_all_questions(user_info)

    # 缓存会话
    sessions[session_id] = {
        "user_info": user_info,
        "current_question": 0,  # 题目索引 0-3
        "questions": questions,
        "qa_history": []
    }

    # 返回第 1 题（总题号 2/5，基本信息是第 1 题）
    q = questions[0]
    return {
        "session_id": session_id,
        "question_number": 2,
        "question": q["question"],
        "options": q["options"],
        "is_last": False
    }


@app.post("/api/session/answer")
async def submit_answer(req: Answer):
    """提交回答：返回下一题或触发分析"""
    session_id = req.session_id

    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在或已过期，请重新开始")

    session = sessions[session_id]
    user_info = session["user_info"]
    idx = session["current_question"]
    questions = session["questions"]

    # 保存当前回答
    await save_answer(
        session_id=session_id,
        question_number=req.question_number,
        question=req.question,
        answer=req.answer
    )

    session["qa_history"].append({
        "question_number": req.question_number,
        "question": req.question,
        "answer": req.answer
    })

    # 下一题索引
    next_idx = idx + 1

    # 是否最后一题（4 道选择题全部答完）
    if next_idx >= len(questions):
        # 触发智能分析
        analysis = await analyze_answers(user_info, session["qa_history"])

        # 保存完整分析（含线索评级）
        await save_analysis(session_id, analysis)

        session["is_completed"] = True
        del sessions[session_id]

        return {
            "session_id": session_id,
            "user_info": {
                "name": user_info["name"],
                "company": user_info["company"],
                "position": user_info["position"]
            },
            "qa_list": session["qa_history"],
            "summary": analysis.get("summary", ""),
            "pain_points": analysis.get("pain_points", []),
            "follow_up_advice": analysis.get("follow_up_advice", ""),
            "lead_level": analysis.get("lead_level", "普通"),
            "lead_score": analysis.get("lead_score", 50),
            "insights": analysis.get("insights", []) + analysis.get("suggestions", [])
        }

    # 返回下一题
    session["current_question"] = next_idx
    q = questions[next_idx]

    return {
        "session_id": session_id,
        "question_number": next_idx + 2,  # 题号：基本信息=1，选择题从 2 开始
        "question": q["question"],
        "options": q["options"],
        "is_last": (next_idx == len(questions) - 1)
    }


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """获取会话状态"""
    if session_id not in sessions:
        user_info = await get_user_info(session_id)
        if not user_info:
            raise HTTPException(status_code=404, detail="会话不存在")
        qa_history = await get_qa_history(session_id)
        return {
            "session_id": session_id,
            "user_info": user_info,
            "current_question": len(qa_history) + 2,
            "qa_history": qa_history,
            "is_completed": False
        }

    session = sessions[session_id]
    return {
        "session_id": session_id,
        "user_info": session["user_info"],
        "current_question": session["current_question"] + 2,
        "qa_history": session["qa_history"],
        "is_completed": session.get("is_completed", False),
        "questions": session["questions"]
    }


@app.get("/api/admin/surveys")
async def admin_list_surveys():
    """管理后台：查看所有问卷记录"""
    return await get_all_surveys()


@app.get("/api/admin/stats")
async def admin_stats():
    """管理后台：统计数据"""
    return await get_stats()


@app.post("/api/admin/follow")
async def admin_update_follow(req: dict):
    """管理后台：更新跟进状态"""
    session_id = req.get("session_id", "")
    status = req.get("status", "new")
    note = req.get("note", "")
    await update_follow_status(session_id, status, note)
    return {"ok": True}


# ==================== 静态文件 ====================

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/admin")
async def serve_admin():
    return FileResponse(os.path.join(FRONTEND_DIR, "admin.html"))


@app.get("/{filename:path}")
async def serve_static(filename: str):
    file_path = os.path.join(FRONTEND_DIR, filename)
    if os.path.isfile(file_path) and not filename.endswith(".py"):
        return FileResponse(file_path)
    raise HTTPException(status_code=404)


if __name__ == "__main__":
    import uvicorn
    from dotenv import load_dotenv
    load_dotenv()

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    print(f"""
╔══════════════════════════════════════════╗
║   🏭  智能制造调查问卷智能体  v2.0       ║
║                                          ║
║   问卷页面:  http://{host}:{port}/           ║
║   数据分析:  http://{host}:{port}/admin      ║
║   API 文档:  http://{host}:{port}/docs       ║
╚══════════════════════════════════════════╝
    """)

    uvicorn.run(app, host=host, port=port)
