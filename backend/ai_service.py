"""AI 服务：批量生成选择题 & 智能分析答案"""

import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

SYSTEM_PROMPT_GENERATE_ALL = """你是一位深耕徐州制造业的市场调研专家。"徐州是中国工程机械之都，拥有徐工集团等龙头企业，产业涵盖工程机械、高端装备、新能源、智慧矿山、绿色建材、食品加工等方向。你正在对徐州本地制造业企业进行数字化转型需求调研。

## 出题策略（BANT 商机模型 + 企业画像驱动）
你需要根据用户填写的「企业名称 + 岗位角色」，精准推断该企业所处的产业赛道和典型场景，围绕以下 6 个维度出题，但**每个维度内的提问角度必须因企而异**，绝不重复套路：

- 第1题「数字化现状」：根据企业类型，从 设备联网率/系统覆盖度/数据应用水平/自动化程度 等不同切口提问
- 第2题「核心痛点」：结合行业通病出题，如工程机械的售后运维、装备制造的车间排产、新能源的工艺一致性、食品加工的品控追溯
- 第3题「投入意愿与价值认知」：结合徐州本地政策（智改数转补贴、工业互联网标杆、专精特新培育），问预算/决策/政策敏感度
- 第4题「时间规划与落地场景」：贴合企业实际可落地的智能制造场景提问
- 第5题「采购决策链与关键人」：根据岗位角色，问决策流程/采购模式/关键影响人/供应商选择标准（结合徐州本地供应链生态）
- 第6题「技术能力与人才储备」：问内部IT团队能力/产线人员数字化素养/是否需要陪跑式服务或交钥匙方案

## 徐州本地特色（必须融入）
- 提到徐州工程机械产业集群、徐工产业链配套、徐州经开区/高新区政策、淮海经济区制造中心定位
- 对中小制造企业可提及「徐州智改数转诊断」「星级上云」「工业互联网标杆工厂」
- 结合行业特性自然植入，不生硬

## 出题变化规则（关键）
1. **先分析企业类型再出题**：根据企业名称推断其细分行业（工程机械整机/零部件/装备制造/新能源/建材/食品等），再设计领域专属问题
2. **切换提问角度**：同一维度每次从不同切口切入（比如上一位问了设备联网，下一位就换成系统整合或数据利用）
3. **引入场景化选项**：选项不写泛泛的"好/坏"，而是写具体场景，如「产线设备已联网，但数据仅用于事后报表」「计划引入MES系统，已对比3家供应商」
4. 每题 4 个选项，需求强度 A→D 递增，选项 20-30 字，问题 25-50 字
5. **幽默/犀利风格可偶尔出没**，如「老板说要做但预算还在画饼阶段」

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

SYSTEM_PROMPT_ANALYZE = """你是一位深耕徐州制造业的市场分析师，为市场销售团队提供企业画像与线索评级报告。

## 徐州产业背景
徐州是"中国工程机械之都"，拥有徐工集团及数千家产业链配套企业，正在推进"智改数转"行动。重点关注：工程机械、高端装备、新能源、智慧矿山、绿色建材、食品加工等方向。

## 分析维度
1. **企业画像**：推断该企业在徐州产业链中的位置、数字化阶段、采购潜力
2. **核心痛点**：提炼最关键的 2-3 个痛点，结合徐州本地产业环境
3. **跟进建议**：给出销售人员具体的切入点和话术（50字内），可结合徐州本地政策（智改数转补贴、上云标杆、专精特新）
4. **线索评级**：综合判断

## 线索评级标准
- **高优**：已有明确需求+预算+近期计划 → 建议 3 天内联系
- **中优**：有需求但预算/时间模糊 → 建议 1 周内联系
- **普通**：处于观望/了解阶段 → 培育池

## 输出格式（严格 JSON）
{
  "summary": "企业画像概述，2-3句话，体现徐州本地产业特色",
  "pain_points": ["痛点1", "痛点2"],
  "follow_up_advice": "销售跟进建议，50字内",
  "lead_level": "高优/中优/普通",
  "lead_score": 85,
  "insights": ["洞察1", "洞察2"],
  "suggestions": ["建议1", "建议2"]
}

只输出 JSON，不要任何标记。"""


async def generate_all_questions(user_info: dict) -> list[dict]:
    """根据用户画像，一次性生成全部 5 道选择题"""
    context = (
        f"用户信息：姓名 {user_info['name']}，"
        f"来自 {user_info['company']}，"
        f"担任 {user_info['position']} 岗位。"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_GENERATE_ALL},
        {"role": "user", "content": f"请为以下用户生成 6 道智能制造调研选择题：\n\n{context}"}
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
    """模拟题目（BANT 模型 + 徐州产业特色，需求强度 A→D 递增）"""
    import random
    role = user_info.get("position", "管理者")
    company = user_info.get("company", "贵企业")

    # 根据企业名推断行业
    company_lower = company.lower()
    if any(k in company_lower for k in ["工程", "机械", "装备", "重工", "徐工"]):
        industry = "工程机械/装备制造"
        q1_variants = [
            (f"作为{company}的{role}，目前车间设备联网率如何？",
             ["A. 基本靠人工记录，设备独立运行", "B. 关键设备有数据采集，但未联网", "C. 产线设备已联网，数据可实时查看", "D. 设备全联网，MES系统深度集成"]),
            (f"{company}在生产排产上，最贴近哪种状态？",
             ["A. 调度全靠老师傅经验和Excel", "B. 有排产软件但计划和执行两张皮", "C. APS系统上线中，部分产线试点", "D. 智能排产+柔性制造，小批量切换自如"]),
        ]
        q2_variants = [
            (f"作为徐州工程机械产业链一环，{company}眼下最头疼的是？",
             ["A. 订单波动大，产线稼动率不稳定", "B. 主机厂压交付周期，备货压力大", "C. 售后运维成本高，缺乏远程诊断能力", "D. 技术工人流失快，老师傅经验难传承"]),
            (f"{company}在质量管控上最大的短板是？",
             ["A. 品控靠人工抽检，漏检率较高", "B. 有检测设备但不联网，数据追溯困难", "C. 质量数据有了但分析和改进周期长", "D. 准备上AI视觉检测，需要方案评估"]),
        ]
        q3_variants = [
            (f"徐州正在推智改数转，{company}在这件事上的真实态度是？",
             ["A. 听说过政策但没研究过", "B. 关注中，想拿补贴但不知怎么申报", "C. 已申请诊断服务，正在评估投入产出", "D. 已拿到补贴，项目在推进中"]),
        ]
        q4_variants = [
            (f"{company}希望在多久内看到智能制造投入的回报？",
             ["A. 先观望同行效果再说", "B. 1-2年内分阶段推进", "C. 6-12个月内启动试点线", "D. 3-6个月内完成首批产线智能化改造"]),
        ]
        q5_variants = [
            (f"{company}在采购智能制造方案时，决策流程是？",
             ["A. 老板一人拍板，其他人执行", "B. 技术部门提需求，采购部比价", "C. 成立专项小组，多部门联合评审", "D. 已有明确选型标准，正在物色供应商"]),
        ]
        q6_variants = [
            (f"{company}内部的技术团队和人才储备怎么样？",
             ["A. 几乎没有专职IT，全靠外部支持", "B. 有1-2个网管，能搞定基础运维", "C. 有信息化部门，能独立做简单二次开发", "D. 技术团队完备，有工业互联网项目经验"]),
        ]
    elif any(k in company_lower for k in ["新能源", "光伏", "锂电", "电池", "储能"]):
        industry = "新能源"
        q1_variants = [
            (f"{company}的生产线自动化程度如何？",
             ["A. 以人工为主，自动化率低于20%", "B. 关键工序半自动化，数据靠纸质", "C. 自动化率60%以上，MES覆盖主工序", "D. 全流程自动化+数字孪生"]),
        ]
        q2_variants = [
            (f"{company}在工艺一致性上最头疼的是？",
             ["A. 批次间差异大，返工率高", "B. 工艺参数靠经验调，缺乏标准沉淀", "C. 有SOP但执行走样，不良率波动", "D. 想引入SPC/AI工艺优化但缺方案"]),
        ]
        q3_variants = [
            (f"在徐州新能源产业补贴窗口期，{company}的投入打算是？",
             ["A. 先活下来再考虑改造", "B. 有想法但资金链紧张", "C. 预算已列，正在选型比价", "D. 已确定方案，准备签合同"]),
        ]
        q4_variants = [
            (f"{company}对智能制造的时间表是？",
             ["A. 暂无明确规划", "B. 明年开始调研选型", "C. 半年内启动样板线", "D. 本季度内必须上线"]),
        ]
        q5_variants = [
            (f"{company}采购智能产线方案时，谁说了算？",
             ["A. 创始人/CEO直接决策", "B. CTO/技术总监主导评估", "C. 技术+采购+财务三方会审", "D. 已有供应商短名单，准备招标"]),
        ]
        q6_variants = [
            (f"{company}的技术团队能接住智能制造的挑战吗？",
             ["A. 完全依赖设备供应商驻厂服务", "B. 有运维人员但缺数字化技能", "C. 有自动化工程师，可对接MES系统", "D. 技术储备强，已在研究AI+工艺优化"]),
        ]
    elif any(k in company_lower for k in ["食品", "饮料", "加工", "农产品"]):
        industry = "食品加工"
        q1_variants = [
            (f"{company}在食品安全追溯上，目前的做法是？",
             ["A. 批次记录靠纸质台账", "B. ERP有批次管理但追溯耗时较长", "C. 二维码追溯系统已上线", "D. 区块链+物联网全链路追溯"]),
        ]
        q2_variants = [
            (f"作为徐州本地食品企业，{company}最迫切想解决的是？",
             ["A. 人工成本高，招工越来越难", "B. 品控不稳定，客户投诉率高", "C. 多品种切换效率低，损耗大", "D. 想扩产能但老厂改造空间有限"]),
        ]
        q3_variants = [
            (f"如果引入智能产线/追溯方案，{company}的预算空间？",
             ["A. 暂无明确预算", "B. 50万以内先试点", "C. 100-300万逐步投入", "D. 300万以上，决心做大改造"]),
        ]
        q4_variants = [
            (f"{company}希望在何时看到智能化改造成效？",
             ["A. 先了解不着急", "B. 明年做规划", "C. 半年内启动", "D. 越快越好，现在就需要"]),
        ]
        q5_variants = [
            (f"{company}在智能化改造上的决策习惯是？",
             ["A. 厂长/总经理说了算", "B. 部门提方案，老板审批预算", "C. 管理层集体讨论，对比至少3家", "D. 已经有目标方案，就差比价签单"]),
        ]
        q6_variants = [
            (f"{company}一线员工对数字化工具的接受度如何？",
             ["A. 年纪偏大，抵触新系统", "B. 愿意学但需要手把手教", "C. 年轻一代能用，老员工磨合中", "D. 团队年轻化，期待数字化工具提效"]),
        ]
    elif any(k in company_lower for k in ["建材", "水泥", "玻璃", "陶瓷"]):
        industry = "绿色建材"
        q1_variants = [
            (f"{company}的能耗管理目前靠什么？",
             ["A. 月底抄电表，事后算账", "B. 有电表但无系统分析", "C. 能源管理系统覆盖主要设备", "D. 智慧能源平台+光伏+储能联动"]),
        ]
        q2_variants = [
            (f"徐州对建材行业环保要求趋严，{company}最担心的合规风险是？",
             ["A. 排放监测靠人工，数据不连续", "B. 除尘设备有但运维跟不上", "C. 想上在线监测但不知哪家靠谱", "D. 合规没问题，想进一步做碳管理"]),
        ]
        q3_variants = [
            (f"在降本增效压力下，{company}对智慧工厂的投入态度？",
             ["A. 市场不好先捂紧口袋", "B. 有政策补贴的话愿意试试", "C. 已预留技改资金在看方案", "D. 必须投，不投就没有竞争力了"]),
        ]
        q4_variants = [
            (f"{company}的智能化改造节奏？",
             ["A. 观望中", "B. 1-2年规划", "C. 6-12个月试点", "D. 3-6个月见成果"]),
        ]
        q5_variants = [
            (f"{company}选供应商时最看重什么？",
             ["A. 价格最低，能用就行", "B. 性价比+本地服务响应快", "C. 行业口碑+案例丰富+技术过硬", "D. 已有长期合作供应商，直接走框架协议"]),
        ]
        q6_variants = [
            (f"{company}在智能化改造方面，最需要什么样的服务模式？",
             ["A. 只要设备，我们自己搞定", "B. 希望厂家提供安装+基础培训", "C. 需要交钥匙方案+3个月陪产", "D. 长期运维外包+持续迭代升级"]),
        ]
    else:
        industry = "通用制造"
        q1_variants = [
            (f"{company}的数字化底子怎么样？",
             ["A. 基本空白，Excel+微信办公", "B. 财务有ERP，车间还是手工", "C. ERP+部分产线数字化", "D. MES/ERP/WMS已打通"]),
        ]
        q2_variants = [
            (f"{role}视角看，{company}眼下最拖后腿的是？",
             ["A. 数据不透明，管理者凭经验决策", "B. 部门墙太厚，信息传递慢", "C. 有数据不会用，缺分析工具", "D. 方向对了，但缺落地执行的人和方案"]),
        ]
        q3_variants = [
            (f"{company}对智能制造这件事，真实的投入意愿是？",
             ["A. 老板还没想清楚，先观察", "B. 有兴趣但ROI算不过来", "C. 预算已规划，在比方案", "D. 领导拍板了，尽快落地"]),
        ]
        q4_variants = [
            (f"谈到时间，{company}的期望是？",
             ["A. 不着急，先看看", "B. 1-2年内推动", "C. 半年内启动试点", "D. 3个月内要有动作"]),
        ]
        q5_variants = [
            (f"作为{role}，{company}选服务商时最看重？",
             ["A. 价格和付款方式", "B. 本地服务团队+及时响应", "C. 行业案例+技术方案+交付能力", "D. 品牌知名度+售后保障"]),
        ]
        q6_variants = [
            (f"{company}对智能制造服务商的能力期望是？",
             ["A. 能卖设备就行，不要求太多", "B. 希望提供方案咨询+设备+安装", "C. 要求全流程服务：诊断→方案→交付→陪产", "D. 需要战略级合作伙伴，长期技术共创"]),
        ]

    # 每个维度随机选一组
    questions = [
        random.choice(q1_variants),
        random.choice(q2_variants),
        random.choice(q3_variants),
        random.choice(q4_variants),
        random.choice(q5_variants),
        random.choice(q6_variants),
    ]
    return [
        {"question": q, "options": opts} for q, opts in questions
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
