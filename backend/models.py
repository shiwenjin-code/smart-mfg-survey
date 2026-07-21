"""Pydantic 数据模型"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserInfo(BaseModel):
    """用户基本信息"""
    name: str = Field(..., description="用户姓名", max_length=50)
    company: str = Field(..., description="所属企业", max_length=100)
    position: str = Field(..., description="负责岗位", max_length=100)


class Answer(BaseModel):
    """用户回答"""
    session_id: str = Field(..., description="会话ID")
    question_number: int = Field(..., ge=1, le=10, description="题号")
    question: str = Field(..., description="问题内容")
    answer: str = Field(..., description="用户回答")


class QuestionResponse(BaseModel):
    """问题响应"""
    session_id: str
    question_number: int
    question: str
    is_last: bool = False


class AnalysisResult(BaseModel):
    """分析结果"""
    session_id: str
    user_info: UserInfo
    qa_list: list[dict]
    summary: str
    insights: list[str]
    created_at: str


class StartSessionRequest(BaseModel):
    """开始会话请求"""
    name: str
    company: str
    position: str


class SessionInfo(BaseModel):
    """会话信息"""
    session_id: str
    user_info: UserInfo
    current_question: int
    qa_history: list[dict]
    is_completed: bool
