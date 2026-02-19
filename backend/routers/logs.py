"""
日志查看路由 - 从文件读取日志
"""
import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, Body
from pydantic import BaseModel

router = APIRouter()


class LogEntry(BaseModel):
    """日志条目模型"""
    timestamp: Optional[str] = None
    level: str
    message: str
    source: Optional[str] = None


class LogsResponse(BaseModel):
    """日志响应模型"""
    success: bool
    logs: List[LogEntry]
    total: int
    has_more: bool


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    date: Optional[str] = Query(None, description="日期 (YYYY-MM-DD)，空表示今天"),
    limit: int = Query(200, ge=1, le=1000, description="返回的日志条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
    level: Optional[str] = Query(None, description="日志级别过滤 (DEBUG/INFO/WARNING/ERROR)")
):
    """获取后端日志（从文件读取）"""
    try:
        from core.file_logger import get_file_log_manager
        log_manager = get_file_log_manager()
        
        # 如果没有指定级别，默认返回 INFO 及以上
        if not level:
            level = "INFO"
        
        # 从文件读取日志
        logs = log_manager.get_logs_from_file(
            date=date,
            limit=limit,
            level=level,
            offset=offset
        )
        
        # 转换为响应格式
        log_entries = [
            LogEntry(
                timestamp=log.timestamp,
                level=log.level,
                message=log.message,
                source=log.source
            )
            for log in logs
        ]
        
        return LogsResponse(
            success=True,
            logs=log_entries,
            total=len(log_entries),
            has_more=len(log_entries) >= limit
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取日志失败: {str(e)}")


@router.get("/logs/dates")
async def get_log_dates():
    """获取可用的日志日期列表"""
    try:
        from core.file_logger import get_file_log_manager
        log_manager = get_file_log_manager()
        dates = log_manager.get_available_dates()
        return {"dates": dates, "today": datetime.now().strftime("%Y-%m-%d")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取日期列表失败: {str(e)}")


@router.get("/logs/levels")
async def get_log_levels():
    """获取可用的日志级别"""
    return {
        "levels": ["DEBUG", "INFO", "WARNING", "ERROR"],
        "default": "INFO"
    }


@router.post("/logs/clear")
async def clear_logs():
    """清空日志（仅清空缓存，不清除文件）"""
    try:
        from core.file_logger import get_file_log_manager
        log_manager = get_file_log_manager()
        log_manager.clear_cache()
        return {"success": True, "message": "日志缓存已清空"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清空日志失败: {str(e)}")


@router.post("/logs/electron")
async def receive_electron_log(
    timestamp: str = Body(...),
    level: str = Body(...),
    message: str = Body(...)
):
    """接收 Electron 主进程的日志"""
    try:
        from core.file_logger import get_file_log_manager
        log_manager = get_file_log_manager()
        log_manager.add_log(
            level=level,
            message=message,
            source="electron"
        )
        return {"success": True}
    except Exception as e:
        # 不抛出异常，避免影响 Electron
        print(f"[Logs] 接收 Electron 日志失败: {e}")
        return {"success": False, "error": str(e)}


@router.websocket("/logs/ws")
async def logs_websocket(websocket: WebSocket):
    """WebSocket 实时推送日志"""
    import logging
    logger = logging.getLogger(__name__)
    logger.debug("[Logs WebSocket] 客户端连接中...")
    await websocket.accept()
    logger.debug("[Logs WebSocket] 客户端已连接")
    
    from core.file_logger import get_file_log_manager
    log_manager = get_file_log_manager()
    
    # 设置事件循环（用于回调）
    import asyncio
    log_manager.set_event_loop(asyncio.get_event_loop())
    
    # 存储接收到的日志的队列
    log_queue = asyncio.Queue()
    
    def on_new_log(entry):
        """新日志回调"""
        try:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(log_queue.put_nowait, entry)
        except Exception as e:
            logger.debug(f"[Logs WebSocket] 回调错误: {e}")
    
    # 订阅日志更新
    log_manager.subscribe(on_new_log)
    
    try:
        # 先发送历史日志（从文件读取最近200条，不过滤级别，由前端过滤）
        recent_logs = log_manager.get_recent_logs(limit=200, level=None)
        logger.debug(f"[Logs WebSocket] 发送 {len(recent_logs)} 条历史日志")
        
        for log in reversed(recent_logs):  # 正序发送（旧的在前）
            try:
                await websocket.send_json({
                    "type": "log",
                    "timestamp": log.timestamp,
                    "level": log.level,
                    "message": log.message,
                    "source": log.source
                })
            except Exception as e:
                logger.debug(f"[Logs WebSocket] 发送历史日志失败: {e}")
        
        # 实时推送新日志
        logger.debug("[Logs WebSocket] 开始实时推送...")
        while True:
            try:
                # 等待新日志，设置超时以便检查连接状态
                log_entry = await asyncio.wait_for(log_queue.get(), timeout=1.0)
                
                try:
                    await websocket.send_json({
                        "type": "log",
                        "timestamp": log_entry.timestamp,
                        "level": log_entry.level,
                        "message": log_entry.message,
                        "source": log_entry.source
                    })
                except Exception as e:
                    logger.debug(f"[Logs WebSocket] 发送实时日志失败: {e}")
                    break
                    
            except asyncio.TimeoutError:
                # 发送心跳保持连接
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                
    except WebSocketDisconnect:
        logger.debug("[Logs WebSocket] 客户端断开连接")
    except Exception as e:
        logger.debug(f"[Logs WebSocket] 错误: {e}")
    finally:
        # 取消订阅
        log_manager.unsubscribe(on_new_log)
        logger.debug("[Logs WebSocket] 连接关闭")
