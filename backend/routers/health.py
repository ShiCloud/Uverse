"""
健康检查路由
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any
import os

router = APIRouter()


class HealthStatus(BaseModel):
    """健康状态响应模型"""
    status: str
    services: Dict[str, Any]
    message: str


async def check_database() -> Dict[str, Any]:
    """检查数据库连接状态 - 使用 SQLAlchemy（与应用一致）"""
    try:
        from core.database import AsyncSessionLocal
        
        async with AsyncSessionLocal() as session:
            # 执行简单查询
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
            
            if value == 1:
                return {"status": "ok", "message": "数据库连接正常"}
            else:
                return {"status": "error", "message": "数据库查询异常"}
                
    except Exception as e:
        return {"status": "error", "message": f"数据库连接失败: {str(e)}"}


def check_rustfs() -> Dict[str, Any]:
    """检查 RustFS 存储服务状态"""
    try:
        from services.rustfs_storage import get_rustfs_storage
        storage = get_rustfs_storage()
        
        # 尝试列出桶来验证连接
        try:
            client = storage._client
            buckets = client.list_buckets()
            bucket_names = [b['Name'] for b in buckets.get('Buckets', [])]
            return {
                "status": "ok", 
                "message": "RustFS 服务正常",
                "buckets": bucket_names
            }
        except Exception as e:
            return {"status": "error", "message": f"RustFS 连接异常: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"RustFS 服务检查失败: {str(e)}"}


@router.get("/health")
async def health_check():
    """基础健康检查端点 - 只检查服务是否可响应"""
    return {
        "status": "ok",
        "message": "Hello World from Backend!"
    }


@router.get("/ready")
async def readiness_check():
    """就绪检查端点 - 检查服务是否可响应
    
    注意：即使某些可选服务（如 RustFS、PostgreSQL）不可用，
    只要 API 服务本身启动成功，就返回 200，让前端可以正常访问配置页面。
    """
    # 检查各项服务（但不影响整体状态）
    db_status = await check_database()
    rustfs_status = check_rustfs()
    
    # 只要有 API 服务在运行，就返回 ready
    # 前端会根据需要决定是否跳转到设置页面
    all_ok = db_status["status"] == "ok" or rustfs_status["status"] == "ok"
    
    overall_status = "ready"  # 总是返回 ready，让前端可以访问
    
    from fastapi.responses import JSONResponse
    
    response_data = {
        "status": overall_status,
        "services": {
            "database": db_status,
            "rustfs": rustfs_status,
        },
        "available": {
            "database": db_status["status"] == "ok",
            "rustfs": rustfs_status["status"] == "ok"
        },
        "message": "API 服务已启动" if all_ok else "API 服务已启动，但部分功能不可用"
    }
    
    return JSONResponse(
        status_code=200,
        content=response_data
    )
