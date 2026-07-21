"""FastAPI 主应用：智能制造调查问卷智能体"""

import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
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
    """开始问卷：保存基本信息，一次性生成全部 6 道选择题，返回第 1 题（题号从 1 开始，基本信息不占题数）"""
    session_id = uuid.uuid4().hex[:12]

    await save_user_info(session_id, req.name, req.company, req.position)
    user_info = {"name": req.name, "company": req.company, "position": req.position}

    # 一次性生成全部 6 道题
    questions = await generate_all_questions(user_info)

    sessions[session_id] = {
        "user_info": user_info,
        "current_question": 0,  # 题目索引 0-5
        "questions": questions,
        "qa_history": []
    }

    # 返回第 1 题（题号 1）
    q = questions[0]
    return {
        "session_id": session_id,
        "question_number": 1,
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

    # 是否最后一题（5 道选择题全部答完）
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
        "question_number": next_idx + 1,  # 题号从 1 开始
        "question": q["question"],
        "options": q["options"],
        "is_last": (next_idx == len(questions) - 1)
    }


# ==================== 企业名称智能联想 ====================

# 徐州及周边制造业企业库（天眼查+企查查数据源，160+家，覆盖工程机械/新能源/食品/建材/纺织/电子/医药等）
MANUFACTURING_COMPANIES = sorted([
    # 徐州工程机械集群（徐工系 + 配套）
    "徐工集团", "徐工重型", "徐工铲运", "徐工矿机",
    "徐工集团工程机械股份有限公司", "徐州工程机械集团有限公司", "徐州工程机械集团进出口有限公司",
    "徐工集团工程机械股份有限公司", "徐州工程机械保税有限公司", "徐州工程机械技师学院",
    "徐工重型机械有限公司", "徐工铲运机械事业部", "徐工矿业机械有限公司",
    "徐工基础工程机械有限公司", "徐工消防安全装备有限公司", "徐州徐工施维英机械有限公司",
    "徐州徐工传动科技有限公司", "徐州徐工液压件有限公司", "徐州徐工随车起重机有限公司",
    "徐州徐工港口机械有限公司", "徐州徐工环境技术有限公司", "徐工青山新能源汽车股份有限公司",
    "徐州徐工特种工程机械有限公司", "徐州市圣凯工程机械有限公司", "康腾徐州工程机械制造有限公司",
    "徐州建机工程机械有限公司", "徐州巴特工程机械股份有限公司", "徐州世通重工机械制造有限公司",
    "徐州海伦哲专用车辆股份有限公司", "江苏金彭集团有限公司", "江苏宗申车业有限公司",
    "徐州美驰车桥有限公司", "徐州锻压机床厂集团有限公司", "徐州罗特艾德回转支承有限公司",
    "徐州中央回转支承有限公司", "徐州中矿汇弘矿山设备有限公司", "江苏华辰变压器股份有限公司",
    "徐州煤矿安全设备制造有限公司", "徐州华东机械有限公司", "徐州华恒机器人系统有限公司",
    # 智能制造
    "徐州宝元智能制造有限公司", "象屿宝元（徐州）智能制造有限公司", "徐州拓普泰克智能制造有限公司",
    "徐州捷锐智能制造有限公司", "徐州正华智能制造有限公司", "徐州春鑫智能制造有限公司",
    "徐州宝盛智能设备制造有限公司", "徐州智能制造产业专项母基金（有限合伙）",
    # 新能源 / 光伏 / 锂电
    "协鑫（集团）控股有限公司", "协鑫集成科技股份有限公司", "协鑫新能源控股有限公司",
    "中能硅业科技发展有限公司", "江苏中润光能科技股份有限公司", "江苏中清光伏科技有限公司",
    "徐州华清新能源科技有限公司", "江苏华源新能源科技有限公司", "徐州鑫宇光伏科技有限公司",
    "徐州万邦新能源科技有限公司", "江苏新恒源能源技术有限公司", "徐州金宏新能源科技有限公司",
    "徐州一帆新能源科技股份有限公司", "浙创（徐州）新能源有限公司", "博途新能源（徐州）有限公司",
    "徐州正兴新能源有限公司", "徐州五羊新能源有限公司", "徐州九彭新能源有限公司",
    "徐州晖能新能源有限公司", "徐州宝瑞新能源科技有限公司", "徐州博佳新能源有限公司",
    "普乐新能源科技（徐州）有限公司", "徐州日托新能源科技有限公司",
    # 高端装备
    "徐州威卡电子控制技术有限公司", "江苏华中气体有限公司", "徐州阿卡控制阀门有限公司",
    "中航工业徐州宇航科技有限公司", "徐州宇能机械科技有限公司", "江苏天宝汽车电子有限公司",
    "江苏金迪新能源车业有限公司",
    # 食品加工
    "维维食品饮料股份有限公司", "维维集团股份有限公司", "江苏君乐宝乳业有限公司",
    "徐州绿健乳品饮料有限公司", "徐州黎明食品有限公司", "江苏麦德森制药有限公司",
    "江苏伊例家食品有限公司", "邳州市天源蒜业有限公司", "徐州汇尔康食品有限公司",
    "徐州恒阳饲料有限公司", "江苏华升面粉有限公司", "徐州鲜之源食品有限公司", "江苏派乐滋食品有限公司",
    # 建材 / 化工
    "徐州中联水泥有限公司", "徐州卧牛山新型防水材料有限公司", "江苏诚意集团有限公司",
    "徐州远大新材料科技有限公司", "徐州金霸王新型建材有限公司", "徐州永固建材有限公司",
    "江苏新河农用化工有限公司", "徐州钛白化工有限责任公司", "江苏新沂沪千人造板制造有限公司",
    "徐州海螺水泥有限责任公司", "徐州金鑫水泥有限公司", "徐州华盛管桩有限公司",
    # 纺织服装
    "徐州天虹银丰纺织有限公司", "徐州天虹时代纺织有限公司", "江苏斯尔克集团股份有限公司",
    "徐州荣盛达纤维制品科技有限公司", "睢宁新宏纺织有限公司", "江苏华晟国联纺织有限公司",
    # 电子信息 / 半导体
    "江苏芯华集成电路科技股份有限公司", "徐州博康信息化学品有限公司", "江苏鲁汶仪器股份有限公司",
    "徐州鑫晶半导体科技有限公司", "江苏华兴激光科技有限公司", "徐州科聚利鑫半导体有限公司",
    # 医药
    "江苏恩华药业股份有限公司", "江苏万邦生化医药集团有限责任公司", "徐州诺倍特药业有限公司",
    "江苏九旭药业有限公司", "徐州利君医药有限公司", "徐州科恒医药有限公司",
    # 通用制造业
    "江苏华辰机械制造有限公司", "徐州大发冲压件有限公司", "徐州德诚机械制造有限公司",
    "徐州精诚特卫安防科技有限公司", "徐州华联玻璃制品有限公司", "徐州倍科机械科技有限公司",
    "徐州力驰电子科技有限公司", "徐州中矿大传动与自动化有限公司", "江苏中科智芯集成科技有限公司",
    "徐州汉之源自动化科技有限公司", "徐州沃达机械制造有限公司", "徐州恒通机电科技有限公司",
    "徐州科林自动化设备有限公司", "徐州安联木业有限公司", "徐州天辰机械制造有限公司",
    "江苏鼎铭机械科技有限公司", "徐州凯尔农业装备股份有限公司",
    # 国内知名制造企业（跨区域联想）
    "三一重工股份有限公司", "中联重科股份有限公司", "山河智能装备股份有限公司",
    "比亚迪股份有限公司", "宁德时代新能源科技股份有限公司", "隆基绿能科技股份有限公司",
    "美的集团股份有限公司", "海尔智家股份有限公司", "格力电器股份有限公司",
    "中兴通讯股份有限公司", "西门子（中国）有限公司", "施耐德电气（中国）有限公司",
    "ABB（中国）有限公司", "华为技术有限公司", "海康威视数字技术股份有限公司",
    "潍柴动力股份有限公司", "中国中车股份有限公司", "京东方科技集团股份有限公司",
    "格力电器（徐州）有限公司", "华润微电子有限公司", "蔚来汽车有限公司",
    "理想汽车", "小鹏汽车", "吉利汽车集团", "长城汽车股份有限公司",
    "长安汽车股份有限公司", "上汽通用五菱汽车股份有限公司", "奇瑞汽车股份有限公司",
    "中天科技集团有限公司", "恒力集团有限公司", "沙钢集团有限公司",
    "天合光能股份有限公司", "阿特斯阳光电力集团", "中创新航科技集团股份有限公司", "蜂巢能源科技股份有限公司",
], key=lambda x: (len(x), x))  # 短名优先匹配，长名补充


@app.get("/api/autocomplete/company")
async def autocomplete_company(q: str = ""):
    """企业名称智能联想：根据输入返回匹配的企业名列表"""
    if not q or len(q.strip()) < 1:
        return {"suggestions": []}

    keyword = q.strip().lower()
    results = []

    for name in MANUFACTURING_COMPANIES:
        name_lower = name.lower()
        # 模糊匹配：包含关键词 或 拼音首字母匹配
        if keyword in name_lower:
            score = 100 if name_lower.startswith(keyword) else 80
            results.append({"name": name, "score": score})
        elif len(keyword) >= 2:
            # 逐字匹配
            matched = all(ch in name_lower for ch in keyword)
            if matched:
                results.append({"name": name, "score": 60})

    # 按匹配度排序，取前 8 条
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


@app.get("/api/admin/export")
async def admin_export_csv():
    """管理后台：导出全部问卷数据为 CSV"""
    csv_content = await export_surveys_csv()
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": "attachment; filename=survey_data.csv"
        }
    )


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
