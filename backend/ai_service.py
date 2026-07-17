"""AI 服务：批量生成选择题 & 智能分析答案"""

import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

SYSTEM_PROMPT_GENERATE_ALL = """你是一位智能制造市场调研专家。你需要为一位制造业人士生成 4 道选择题，用于评估该企业的智能制造需求强度，帮助市场团队判断是否为重点跟进客户。

## 出题策略（BANT 商机模型）
- 第1题：数字化现状 → 评估企业当前成熟度阶段
- 第2题：核心痛点 → 找出最迫切的需求与阻碍
- 第3题：投入意愿 → 判断预算空间和决策态度
- 第4题：时间规划 → 了解落地紧迫程度

## 规则
1. 紧密结合用户的企业类型和岗位角色出题
2. 每道题 4 个选项，按「需求强度」从低到高排列（A=保守/观望 → D=积极/已有行动）
3. 选项要有阶梯差异，能清晰区分需求强弱
4. 每个选项控制在 25 字以内，问题 30-60 字

## 输出格式（严格 JSON）
{
  "questions": [
    {
      "question": "问题",
      "options": ["A. xxx", "B. xxx", "C. xxx", "D. xxx"]
    }
  ]
}

只输出 JSON，不要 Markdown 标记。"""

SYSTEM_PROMPT_ANALYZE = """你是一位智能制造行业分析师兼销售赋能专家。根据问卷数据，输出面向市场团队的企业画像与线索评级报告。

## 分析维度
1. **企业画像**：根据回答推断该企业的数字化阶段、需求强度和采购潜力
2. **核心痛点**：提炼最关键的 2-3 个痛点
3. **跟进建议**：给出销售人员具体的切入点（50字内）
4. **线索评级**：综合判断

## 线索评级标准
- **高优**：已有明确需求+预算+近期计划 → 建议 3 天内联系
- **中优**：有需求但预算/时间模糊 → 建议 1 周内联系
- **普通**：处于观望/了解阶段 → 培育池

## 输出格式（严格 JSON）
{
  "summary": "企业画像概述，2-3句话",
  "pain_points": ["痛点1", "痛点2"],
  "follow_up_advice": "销售跟进建议，50字内",
  "lead_level": "高优/中优/普通",
  "lead_score": 85,
  "insights": ["洞察1", "洞察2"],
  "suggestions": ["建议1", "建议2"]
}

只输出 JSON，不要任何标记。"""


async def generate_all_questions(user_info: dict) -> list[dict]:
    """根据用户画像，一次性生成全部 4 道选择题"""
    context = (
        f"用户信息：姓名 {user_info['name']}，"
        f"来自 {user_info['company']}，"
        f"担任 {user_info['position']} 岗位。"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_GENERATE_ALL},
        {"role": "user", "content": f"请为以下用户生成 4 道智能制造调研选择题：\n\n{context}"}
    ]

    result = await _call_llm(messages, temperature=0.9)

    try:
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:] if len(lines) > 1 else lines
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        data = json.loads(cleaned)
        return data.get("questions", _mock_questions(user_info))
    except json.JSONDecodeError:
        return _mock_questions(user_info)


async def analyze_answers(
    user_info: dict,
    qa_history: list[dict]
) -> dict:
    """智能分析 + 线索评级"""
    context_parts = [
        f"企业：{user_info.get('company','')} | 岗位：{user_info.get('position','')} | 姓名：{user_info.get('name','')}"
    ]

    context_parts.append("\n问卷回答记录：")
    for qa in qa_history:
        context_parts.append(f"Q: {qa['question']}")
        context_parts.append(f"A: {qa['answer']}")

    context = "\n".join(context_parts)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_ANALYZE},
        {"role": "user", "content": f"分析以下问卷，输出市场线索报告：\n\n{context}"}
    ]

    result = await _call_llm(messages, temperature=0.7)

    try:
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:] if len(lines) > 1 else lines
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        data = json.loads(cleaned)
        # 确保默认值
        data.setdefault("pain_points", [])
        data.setdefault("follow_up_advice", "")
        data.setdefault("lead_level", "普通")
        data.setdefault("lead_score", 50)
        return data
    except json.JSONDecodeError:
        return {
            "summary": result[:200],
            "pain_points": [],
            "follow_up_advice": "",
            "lead_level": "普通",
            "lead_score": 50,
            "insights": [],
            "suggestions": []
        }


async def _call_llm(messages: list[dict], temperature: float = 0.7) -> str:
    """调用 LLM API"""
    if not LLM_API_KEY:
        return _mock_response(messages)

    async with httpx.AsyncClient(timeout=60.0) as client:
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
                "max_tokens": 2000
            }
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


def _mock_questions(user_info: dict) -> list[dict]:
    """模拟题目（BANT 模型，需求强度 A→D 递增）"""
    role = user_info.get("position", "管理者")
    company = user_info.get("company", "贵企业")
    return [
        {
            "question": f"作为{role}，{company}目前数字化建设处于哪个阶段？",
            "options": [
                "A. 尚未启动，仍以纸质/Excel为主",
                "B. 部分业务上线了ERP/MES等系统",
                "C. 核心系统已打通，数据可追溯",
                "D. 已建成数字化平台，数据驱动运营"
            ]
        },
        {
            "question": f"当前在智能制造推进中，{company}最头疼的问题是？",
            "options": [
                "A. 缺乏清晰规划，不知从何入手",
                "B. 老系统包袱重，改造成本高",
                "C. 跨部门协同困难，数据孤岛严重",
                "D. 方向明确，但缺落地执行团队"
            ]
        },
        {
            "question": f"如果引入智能制造方案，{company}的预算态度是？",
            "options": [
                "A. 暂无预算，先了解看看",
                "B. 有初步预算，需看ROI再定",
                "C. 预算已预留，正在对比方案",
                "D. 预算充足，希望尽快推进落地"
            ]
        },
        {
            "question": f"您期望在多长时间内看到智能制造的落地成效？",
            "options": [
                "A. 暂无明确时间表",
                "B. 1-2年内逐步推进",
                "C. 6-12个月内启动试点",
                "D. 3-6个月内完成首批上线"
            ]
        }
    ]


def _mock_response(messages: list[dict]) -> str:
    """无 API Key 时返回模拟数据"""
    last_msg = messages[-1]["content"] if messages else ""

    if "请为以下用户生成" in last_msg:
        user_info = {}
        for line in last_msg.split("\n"):
            if "姓名" in line:
                import re
                m = re.search(r'姓名\s*(\S+)', line)
                if m:
                    user_info["name"] = m.group(1)
        return json.dumps({"questions": _mock_questions(user_info)}, ensure_ascii=False)

    if "分析以下问卷" in last_msg:
        return json.dumps({
            "summary": "该企业处于信息化中期阶段，已有基础系统但数据打通不足，存在明确痛点，预算态度偏积极，属于可重点跟进的潜在客户。",
            "pain_points": ["数据孤岛严重，系统间协同困难", "缺乏统一的数字化平台规划"],
            "follow_up_advice": "可从轻量级数据中台方案切入，强调3个月见效的试点案例，降低决策门槛。",
            "lead_level": "中优",
            "lead_score": 75,
            "insights": ["ERP已部署但MES缺失，车间层数字化是突破口", "管理层有认知但缺执行路径", "6-12个月内有明确试点计划"],
            "suggestions": ["推荐MES+数据看板一体化方案", "安排标杆客户参观交流", "提供免费数字化诊断报告"]
        }, ensure_ascii=False)

    return "当前未配置 LLM API Key，返回模拟数据。"
