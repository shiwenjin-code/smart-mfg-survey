"""AI 服务：批量生成选择题 & 智能分析答案（v3 速度优化版）"""

import os
import json
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

# 精简版 system prompt（减少 token 消耗，提升生成速度）
SYSTEM_PROMPT_GENERATE_ALL = """你是徐州制造业市场调研专家。根据用户企业+岗位，生成 5 道数字化转型调研选择题。

## 5 个维度（每题从不同切口提问）
1. 数字化现状：设备联网/系统覆盖/数据应用（因企而异）
2. 核心痛点：结合行业通病（工程机械售后运维、装备排产、新能源工艺、食品品控等）
3. 投入意愿：结合徐州智改数转政策、预算/决策敏感度
4. 时间规划与落地场景：实际可落地的智能制造场景
5. 采购决策链：根据岗位问决策流程/供应商选择标准

## 规则
- 先分析企业类型（工程机械/新能源/食品/建材/通用），再出行业专属问题
- 选项写具体场景（如"产线已联网但数据仅用于报表"），不写泛泛的"好/坏"
- 每题 4 个选项(A-D)，需求强度递增，选项 15-30 字，问题 20-45 字
- 结合徐州产业特色（徐工产业链、经开区政策、淮海经济区定位）

## 输出 JSON（只输出 JSON，不要 Markdown）
{"questions":[{"question":"...","options":["A. ...","B. ...","C. ...","D. ..."]}]}"""

SYSTEM_PROMPT_ANALYZE = """你是徐州制造业市场分析师。根据问卷回答做线索评级。

## 分析维度
1. 企业画像（产业链位置、数字化阶段、采购潜力）
2. 核心痛点（2-3个，结合徐州产业环境）
3. 跟进建议（50字内，结合智改数转政策）
4. 线索评级：高优(明确需求+预算+近期计划) | 中优(有需求但计划模糊) | 普通(观望阶段)

## 输出 JSON（只输出 JSON，不要 Markdown）
{"summary":"2-3句话企业画像","pain_points":["痛点1","痛点2"],"follow_up_advice":"跟进建议","lead_level":"高优/中优/普通","lead_score":85,"insights":["洞察1","洞察2"],"suggestions":["建议1","建议2"]}"""


async def generate_all_questions(user_info: dict) -> list[dict]:
    """根据用户画像，一次性生成全部 5 道选择题（带超时兜底）"""
    context = (
        f"用户：{user_info['name']}，{user_info['company']}，{user_info['position']}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_GENERATE_ALL},
        {"role": "user", "content": f"请为以下用户生成 5 道智能制造调研选择题：\n\n{context}"}
    ]

    try:
        # 8 秒超时，超时则用 mock 兜底
        result = await asyncio.wait_for(_call_llm(messages, temperature=0.7, max_tokens=1200), timeout=8.0)
    except (asyncio.TimeoutError, Exception):
        return _mock_questions(user_info)

    try:
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:] if len(lines) > 1 else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        data = json.loads(cleaned)
        questions = data.get("questions", _mock_questions(user_info))
        # 确保恰好 5 题
        if len(questions) < 5:
            questions += _mock_questions(user_info)[len(questions):5]
        return questions[:5]
    except json.JSONDecodeError:
        return _mock_questions(user_info)


async def analyze_answers(user_info: dict, qa_history: list[dict]) -> dict:
    """智能分析 + 线索评级"""
    context_parts = [
        f"企业：{user_info.get('company','')} | 岗位：{user_info.get('position','')} | 姓名：{user_info.get('name','')}"
    ]
    context_parts.append("\n问卷回答：")
    for qa in qa_history:
        context_parts.append(f"Q: {qa['question']}")
        context_parts.append(f"A: {qa['answer']}")
    context = "\n".join(context_parts)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_ANALYZE},
        {"role": "user", "content": f"分析以下问卷，输出市场线索报告：\n\n{context}"}
    ]

    try:
        result = await asyncio.wait_for(_call_llm(messages, temperature=0.6, max_tokens=800), timeout=10.0)
    except (asyncio.TimeoutError, Exception):
        return _mock_analysis()

    try:
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:] if len(lines) > 1 else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        data = json.loads(cleaned)
        data.setdefault("pain_points", [])
        data.setdefault("follow_up_advice", "")
        data.setdefault("lead_level", "普通")
        data.setdefault("lead_score", 50)
        return data
    except json.JSONDecodeError:
        return _mock_analysis()


async def _call_llm(messages: list[dict], temperature: float = 0.7, max_tokens: int = 1200) -> str:
    """调用 LLM API"""
    if not LLM_API_KEY:
        raise Exception("No API key")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


def _mock_questions(user_info: dict) -> list[dict]:
    """模拟题目（5 题，BANT 模型 + 徐州产业特色）"""
    company = user_info.get("company", "贵企业")
    company_lower = company.lower()

    if any(k in company_lower for k in ["工程", "机械", "装备", "重工", "徐工"]):
        pool = [
            ("目前车间设备联网率如何？", ["A. 基本靠人工记录，设备独立运行", "B. 关键设备有数据采集但未联网", "C. 产线设备已联网，数据可实时查看", "D. 设备全联网，MES系统深度集成"]),
            ("作为徐州工程机械产业链一环，眼下最头疼的是？", ["A. 订单波动大，产线稼动率不稳定", "B. 主机厂压交付周期，备货压力大", "C. 售后运维成本高，缺乏远程诊断能力", "D. 技术工人流失快，老师傅经验难传承"]),
            ("徐州正在推智改数转，对这件事的真实态度是？", ["A. 听说过政策但没研究过", "B. 关注中，想拿补贴但不知怎么申报", "C. 已申请诊断，正在评估投入产出", "D. 已拿到补贴，项目在推进中"]),
            ("希望多久看到智能制造投入的回报？", ["A. 先观望同行效果再说", "B. 1-2年内分阶段推进", "C. 6-12个月内启动试点线", "D. 3-6个月内完成首批产线智能化改造"]),
            ("采购智能制造方案时，决策流程是？", ["A. 老板一人拍板", "B. 技术部门提需求，采购比价", "C. 成立专项小组，联合评审", "D. 已有明确标准，正在物色供应商"]),
        ]
    elif any(k in company_lower for k in ["新能源", "光伏", "锂电", "电池", "储能"]):
        pool = [
            ("生产线自动化程度如何？", ["A. 以人工为主，自动化率低于20%", "B. 关键工序半自动化，数据靠纸质", "C. 自动化率60%以上，MES覆盖主工序", "D. 全流程自动化+数字孪生"]),
            ("在工艺一致性上最头疼的是？", ["A. 批次间差异大，返工率高", "B. 工艺参数靠经验调，缺乏标准", "C. 有SOP但执行走样，不良率波动", "D. 想引入AI工艺优化但缺方案"]),
            ("新能源产业补贴窗口期，投入打算是？", ["A. 先活下来再考虑改造", "B. 有想法但资金链紧张", "C. 预算已列，正在选型比价", "D. 已确定方案，准备签合同"]),
            ("对智能制造的时间表是？", ["A. 暂无明确规划", "B. 明年开始调研选型", "C. 半年内启动样板线", "D. 本季度内必须上线"]),
            ("采购智能产线方案时，谁说了算？", ["A. 创始人/CEO直接决策", "B. CTO/技术总监主导评估", "C. 技术+采购+财务三方会审", "D. 已有供应商短名单，准备招标"]),
        ]
    elif any(k in company_lower for k in ["食品", "饮料", "加工", "农产品"]):
        pool = [
            ("食品安全追溯上，目前的做法是？", ["A. 批次记录靠纸质台账", "B. ERP有批次管理但追溯耗时较长", "C. 二维码追溯系统已上线", "D. 区块链+物联网全链路追溯"]),
            ("最迫切想解决的是？", ["A. 人工成本高，招工越来越难", "B. 品控不稳定，客户投诉率高", "C. 多品种切换效率低，损耗大", "D. 想扩产能但老厂改造空间有限"]),
            ("引入智能产线/追溯方案，预算空间？", ["A. 暂无明确预算", "B. 50万以内先试点", "C. 100-300万逐步投入", "D. 300万以上，决心做大改造"]),
            ("希望何时看到智能化成效？", ["A. 先了解不着急", "B. 明年做规划", "C. 半年内启动", "D. 越快越好"]),
            ("智能化改造上的决策习惯是？", ["A. 厂长/总经理说了算", "B. 部门提方案，老板审批预算", "C. 管理层集体讨论，对比至少3家", "D. 已有目标方案，就差比价签单"]),
        ]
    elif any(k in company_lower for k in ["建材", "水泥", "玻璃", "陶瓷"]):
        pool = [
            ("能耗管理目前靠什么？", ["A. 月底抄电表，事后算账", "B. 有电表但无系统分析", "C. 能源管理系统覆盖主要设备", "D. 智慧能源平台+光伏+储能联动"]),
            ("环保要求趋严，最担心的合规风险？", ["A. 排放监测靠人工，数据不连续", "B. 除尘设备有但运维跟不上", "C. 想上在线监测但不知哪家靠谱", "D. 合规没问题，想进一步做碳管理"]),
            ("对智慧工厂的投入态度？", ["A. 市场不好先捂紧口袋", "B. 有政策补贴愿意试试", "C. 已预留技改资金在看方案", "D. 必须投，不投就没竞争力了"]),
            ("智能化改造节奏？", ["A. 观望中", "B. 1-2年规划", "C. 6-12个月试点", "D. 3-6个月见成果"]),
            ("选供应商时最看重什么？", ["A. 价格最低，能用就行", "B. 性价比+本地服务响应快", "C. 行业口碑+案例丰富+技术过硬", "D. 已有长期合作供应商"]),
        ]
    else:
        pool = [
            ("数字化底子怎么样？", ["A. 基本空白，Excel+微信办公", "B. 财务有ERP，车间还是手工", "C. ERP+部分产线数字化", "D. MES/ERP/WMS已打通"]),
            ("眼下最拖后腿的是？", ["A. 数据不透明，凭经验决策", "B. 部门墙太厚，信息传递慢", "C. 有数据不会用，缺分析工具", "D. 方向对了，但缺落地执行的人"]),
            ("对智能制造真实的投入意愿？", ["A. 老板还没想清楚", "B. 有兴趣但ROI算不过来", "C. 预算已规划，在比方案", "D. 领导拍板了，尽快落地"]),
            ("时间上的期望是？", ["A. 不着急先看看", "B. 1-2年内推动", "C. 半年内启动试点", "D. 3个月内要有动作"]),
            ("选服务商时最看重？", ["A. 价格和付款方式", "B. 本地服务+及时响应", "C. 行业案例+技术方案+交付能力", "D. 品牌知名度+售后保障"]),
        ]

    return [{"question": q, "options": opts} for q, opts in pool]


def _mock_analysis() -> dict:
    """模拟分析结果"""
    return {
        "summary": "该企业处于信息化中期阶段，已有基础系统但数据打通不足，存在明确痛点，预算态度偏积极，属于可重点跟进的潜在客户。",
        "pain_points": ["数据孤岛严重，系统间协同困难", "缺乏统一的数字化平台规划"],
        "follow_up_advice": "可从轻量级数据中台方案切入，强调3个月见效的试点案例，降低决策门槛。",
        "lead_level": "中优",
        "lead_score": 75,
        "insights": ["ERP已部署但MES缺失", "管理层有认知但缺执行路径", "6-12个月内有明确试点计划"],
        "suggestions": ["推荐MES+数据看板一体化方案", "安排标杆客户参观交流", "提供免费数字化诊断报告"]
    }
