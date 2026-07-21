"""FastAPI 主应用：智能制造调查问卷智能体 v3.0"""

import os
import uuid
import io
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
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
    get_user_info, save_analysis, get_all_surveys, get_stats,
    update_follow_status, export_surveys_csv
)
from ai_service import generate_all_questions, analyze_answers

TOTAL_AI_QUESTIONS = 5  # AI 生成 5 道选择题（基本信息不占题数）


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    await init_db()
    yield


app = FastAPI(
    title="智能制造调查问卷智能体",
    description="面向智能制造行业的智能问卷调查系统",
    version="3.0.0",
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

# 会话缓存
sessions: dict[str, dict] = {}


# ==================== API 路由 ====================

@app.post("/api/session/start")
async def start_session(req: StartSessionRequest):
    """开始问卷：保存基本信息，生成 5 道 AI 题，返回第 1 题"""
    session_id = uuid.uuid4().hex[:12]

    await save_user_info(session_id, req.name, req.company, req.position, req.contact)
    user_info = {
        "name": req.name, "company": req.company,
        "position": req.position, "contact": req.contact
    }

    # 生成全部 5 道题
    questions = await generate_all_questions(user_info)

    sessions[session_id] = {
        "user_info": user_info,
        "current_question": 0,
        "questions": questions,
        "qa_history": []
    }

    q = questions[0]
    return {
        "session_id": session_id,
        "question_number": 1,
        "question": q["question"],
        "options": q["options"],
        "is_last": False,
        "user_info": user_info
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

    next_idx = idx + 1

    # 5 道选择题全部答完 → 智能分析
    if next_idx >= len(questions):
        analysis = await analyze_answers(user_info, session["qa_history"])
        await save_analysis(session_id, analysis)

        session["is_completed"] = True
        del sessions[session_id]

        return {
            "session_id": session_id,
            "user_info": {
                "name": user_info["name"],
                "company": user_info["company"],
                "position": user_info["position"],
                "contact": user_info.get("contact", "")
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
        "question_number": next_idx + 1,
        "question": q["question"],
        "options": q["options"],
        "is_last": (next_idx == len(questions) - 1)
    }


# ==================== 企业名称智能联想 ====================

MANUFACTURING_COMPANIES = sorted([
    "徐工集团", "徐工重型", "徐工铲运", "徐工矿机",
    "徐工集团工程机械股份有限公司", "徐州工程机械集团有限公司",
    "徐工重型机械有限公司", "徐工铲运机械事业部", "徐州徐工施维英机械有限公司",
    "徐州徐工传动科技有限公司", "徐州徐工液压件有限公司", "徐工基础工程机械有限公司",
    "徐州建机工程机械有限公司", "徐州巴特工程机械股份有限公司", "徐州海伦哲专用车辆股份有限公司",
    "江苏金彭集团有限公司", "江苏宗申车业有限公司", "徐州美驰车桥有限公司",
    "徐州锻压机床厂集团有限公司", "徐州华东机械有限公司", "徐州华恒机器人系统有限公司",
    "徐州宝元智能制造有限公司", "象屿宝元（徐州）智能制造有限公司", "徐州宝盛智能设备制造有限公司",
    "协鑫（集团）控股有限公司", "协鑫集成科技股份有限公司", "中能硅业科技发展有限公司",
    "江苏中润光能科技股份有限公司", "江苏中清光伏科技有限公司", "徐州华清新能源科技有限公司",
    "江苏新恒源能源技术有限公司", "徐州鑫宇光伏科技有限公司", "博途新能源（徐州）有限公司",
    "维维食品饮料股份有限公司", "维维集团股份有限公司", "江苏君乐宝乳业有限公司",
    "徐州绿健乳品饮料有限公司", "徐州黎明食品有限公司", "江苏伊例家食品有限公司",
    "徐州中联水泥有限公司", "徐州卧牛山新型防水材料有限公司", "江苏诚意集团有限公司",
    "徐州天虹银丰纺织有限公司", "徐州天虹时代纺织有限公司", "江苏斯尔克集团股份有限公司",
    "江苏芯华集成电路科技股份有限公司", "徐州博康信息化学品有限公司", "江苏鲁汶仪器股份有限公司",
    "徐州鑫晶半导体科技有限公司", "江苏恩华药业股份有限公司", "江苏万邦生化医药集团有限责任公司",
    "三一重工股份有限公司", "中联重科股份有限公司", "山河智能装备股份有限公司",
    "比亚迪股份有限公司", "宁德时代新能源科技股份有限公司", "隆基绿能科技股份有限公司",
    "美的集团股份有限公司", "海尔智家股份有限公司", "格力电器股份有限公司",
    "中兴通讯股份有限公司", "华为技术有限公司", "海康威视数字技术股份有限公司",
    "潍柴动力股份有限公司", "中国中车股份有限公司", "京东方科技集团股份有限公司",
    "蔚来汽车有限公司", "理想汽车", "小鹏汽车", "吉利汽车集团", "长城汽车股份有限公司",
    "中天科技集团有限公司", "恒力集团有限公司", "沙钢集团有限公司",
    "天合光能股份有限公司", "阿特斯阳光电力集团", "中创新航科技集团股份有限公司",
    "西门子（中国）有限公司", "施耐德电气（中国）有限公司", "ABB（中国）有限公司",
], key=lambda x: (len(x), x))


@app.get("/api/autocomplete/company")
async def autocomplete_company(q: str = ""):
    """企业名称智能联想"""
    if not q or len(q.strip()) < 1:
        return {"suggestions": []}

    keyword = q.strip().lower()
    results = []

    for name in MANUFACTURING_COMPANIES:
        name_lower = name.lower()
        if keyword in name_lower:
            score = 100 if name_lower.startswith(keyword) else 80
            results.append({"name": name, "score": score})
        elif len(keyword) >= 2:
            matched = all(ch in name_lower for ch in keyword)
            if matched:
                results.append({"name": name, "score": 60})

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"suggestions": [r["name"] for r in results[:8]]}


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


# ==================== 管理后台 API ====================

@app.get("/api/admin/surveys")
async def admin_list_surveys():
    return await get_all_surveys()


@app.get("/api/admin/stats")
async def admin_stats():
    return await get_stats()


@app.post("/api/admin/follow")
async def admin_update_follow(req: dict):
    session_id = req.get("session_id", "")
    status = req.get("status", "new")
    note = req.get("note", "")
    await update_follow_status(session_id, status, note)
    return {"ok": True}


@app.get("/api/admin/export")
async def admin_export_csv():
    csv_content = await export_surveys_csv()
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=survey_data.csv"}
    )


# ==================== 二维码生成 ====================

@app.get("/api/qrcode")
async def generate_qrcode(url: str = Query(default="", description="要编码的 URL")):
    """生成问卷二维码（PNG 图片）"""
    if not url:
        raise HTTPException(status_code=400, detail="请提供 url 参数")

    try:
        import qrcode
        from qrcode.image.styledpil import StyledPilImage
        from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
    except ImportError:
        # 降级：纯文本二维码生成
        import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2
    )
    qr.add_data(url)
    qr.make(fit=True)

    try:
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
            fill_color="#4f46e5",
            back_color="white"
        )
    except Exception:
        img = qr.make_image(fill_color="#4f46e5", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")


# ==================== 静态文件 ====================

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/admin")
async def serve_admin():
    return FileResponse(os.path.join(FRONTEND_DIR, "admin.html"))


@app.get("/qrcode-page")
async def serve_qrcode_page():
    """二维码展示页面"""
    return FileResponse(os.path.join(FRONTEND_DIR, "qrcode.html"))


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
║   🏭  智能制造调查问卷智能体  v3.0       ║
║                                          ║
║   问卷页面:  http://{host}:{port}/           ║
║   管理后台:  http://{host}:{port}/admin      ║
║   二维码页:  http://{host}:{port}/qrcode-page ║
║   API 文档:  http://{host}:{port}/docs       ║
╚══════════════════════════════════════════╝
    """)

    uvicorn.run(app, host=host, port=port)
