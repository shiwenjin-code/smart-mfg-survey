# 🏭 智能制造调查问卷智能体

面向智能制造行业的 AI 驱动问卷调查系统。支持微信扫码访问，5 道动态生成的问题，智能分析用户回答。

## ✨ 核心特性

- **🤖 AI 动态出题**：每个问题基于用户前一个回答智能生成，题库不固定，千人千面
- **📱 移动端优先**：适配微信内置浏览器，扫码即可填写
- **📊 智能分析**：问卷完成后自动分析用户回答，提炼关键洞察与建议
- **🗄️ 数据持久化**：用户基本信息 + 完整问答记录存入后端数据库
- **📋 管理后台**：可视化查看所有问卷数据与分析结果
- **🔌 灵活配置**：支持任意 OpenAI 兼容 API（DeepSeek、通义千问、GPT 等）

## 🚀 快速启动

### 1. 配置环境

```bash
cd backend
copy .env.example .env    # Windows
# 或 cp .env.example .env   # Linux/Mac
```

编辑 `.env` 文件：

```env
LLM_API_KEY=sk-your-key-here       # 必填：你的 API Key
LLM_BASE_URL=https://api.openai.com/v1   # API 地址
LLM_MODEL=gpt-4o                   # 模型名称
HOST=0.0.0.0
PORT=8000
```

### 2. 安装依赖 & 启动

**Windows（一键启动）：**
```
双击 run.bat
```

**Linux/Mac：**
```bash
cd backend
pip install -r requirements.txt
python app.py
```

### 3. 访问服务

| 地址 | 用途 |
|------|------|
| `http://localhost:8000/` | 问卷填写页面 |
| `http://localhost:8000/admin` | 管理后台 |
| `http://localhost:8000/docs` | API 文档 |

## 📱 微信扫码使用

1. 将服务部署到公网服务器（可使用内网穿透工具如 ngrok）
2. 将公网 URL 生成二维码（推荐使用草料二维码等工具）
3. 用户微信扫码后可直接在微信内置浏览器中填写

## 🏗️ 项目结构

```
survey-system/
├── backend/
│   ├── app.py              # FastAPI 主应用
│   ├── models.py            # Pydantic 数据模型
│   ├── database.py          # SQLite 数据库操作
│   ├── ai_service.py        # AI 服务（出题 + 分析）
│   ├── requirements.txt     # Python 依赖
│   ├── .env.example         # 环境变量模板
│   └── survey.db            # SQLite 数据库（自动创建）
├── frontend/
│   ├── index.html           # 问卷页面
│   ├── admin.html           # 管理后台页面
│   ├── style.css            # 样式
│   └── app.js               # 前端交互逻辑
└── run.bat                  # Windows 一键启动
```

## 📊 问卷流程

```
用户填写基本信息（姓名/企业/岗位）
    ↓
AI 根据基本信息生成第 2 题
    ↓
用户回答 → AI 根据上下文生成第 3 题
    ↓
用户回答 → AI 根据上下文生成第 4 题
    ↓
用户回答 → AI 根据上下文生成第 5 题
    ↓
用户回答 → AI 智能分析全部回答
    ↓
展示分析结果 + 数据存入后端数据库
```

## 🛠️ API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/session/start` | 开始问卷（提交基本信息） |
| POST | `/api/session/answer` | 提交回答（返回下一题或分析结果） |
| GET | `/api/session/{id}` | 获取会话状态 |
| GET | `/api/admin/surveys` | 获取全部问卷数据 |

## ⚠️ 注意事项

- 如未配置 `LLM_API_KEY`，系统会使用内置模拟数据运行（仅用于开发调试）
- 数据库文件 `survey.db` 会自动创建在 `backend/` 目录下
- 会话状态存储在内存中，重启服务后进行中的会话会丢失（已完成的数据在数据库中不受影响）
