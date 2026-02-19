"""
对话路由 - Langchain 集成
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    对话接口 - 使用 Langchain 处理
    """
    # TODO: 集成 Langchain 实现真正的对话功能
    return ChatResponse(
        reply=f"收到消息: {request.message} (Langchain 待集成)"
    )
