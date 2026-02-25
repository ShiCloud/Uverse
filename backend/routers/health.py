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
        from core.database import get_session_local
        
        # 获取会话工厂（自动初始化引擎）
        AsyncSessionLocal = get_session_local()
        
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
    
    后台初始化模式：API 服务启动后立即返回 ready，
    后台任务异步完成数据库等初始化。
    """
    # 检查各项服务状态（异步，不阻塞）
    db_status = await check_database()
    rustfs_status = check_rustfs()
    
    # API 服务本身是否可用
    api_ready = True
    
    # 检查后台初始化是否完成
    import sys
    _main = sys.modules.get('__main__')
    background_completed = getattr(_main, '_background_init_completed', False)
    
    # 确定整体状态
    if db_status["status"] == "ok":
        overall_status = "ready"
        message = "所有服务已就绪"
    elif not background_completed:
        overall_status = "starting"
        message = "服务正在启动中..."
    else:
        overall_status = "ready"
        message = "API 服务已启动，数据库不可用"
    
    from fastapi.responses import JSONResponse
    
    response_data = {
        "status": overall_status,
        "services": {
            "database": db_status,
            "rustfs": rustfs_status,
        },
        "available": {
            "database": db_status["status"] == "ok",
            "rustfs": rustfs_status["status"] == "ok",
            "api": api_ready
        },
        "background_init": background_completed,
        "message": message
    }
    
    # 如果正在启动中，返回 503 让前端继续等待
    status_code = 200 if overall_status == "ready" else 503
    
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )
