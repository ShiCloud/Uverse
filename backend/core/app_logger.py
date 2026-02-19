"""
应用日志管理器 - 用于捕获和实时推送所有后端日志
"""
import asyncio
import logging
import threading
import sys
from typing import List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    level: str
    message: str
    source: str = "backend"


class AppLogManager:
    """应用日志管理器 - 单例模式"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, max_entries: int = 5000):
        if self._initialized:
            return
        
        self.max_entries = max_entries
        self.logs: List[LogEntry] = []
        self.subscribers: List[Callable] = []
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._initialized = True
        self._handler_added = False
    
    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """设置事件循环"""
        self._loop = loop
    
    def add_log(self, level: str, message: str, source: str = "backend"):
        """添加日志条目（线程安全）"""
        entry = LogEntry(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            level=level.upper(),
            message=message,
            source=source
        )
        
        with self._lock:
            self.logs.append(entry)
            # 限制日志条目数量
            if len(self.logs) > self.max_entries:
                self.logs = self.logs[-self.max_entries:]
            
            # 保存一份订阅者列表的副本
            subscribers = self.subscribers.copy()
        
        # 通知订阅者（在事件循环中执行）
        if self._loop:
            for callback in subscribers:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.run_coroutine_threadsafe(callback(entry), self._loop)
                    else:
                        # 对于同步回调，在事件循环中执行
                        self._loop.call_soon_threadsafe(callback, entry)
                except Exception:
                    pass
    
    def get_logs(self, limit: int = 200, level: Optional[str] = None) -> List[LogEntry]:
        """获取日志列表"""
        with self._lock:
            logs = self.logs.copy()
        
        if level and level != "ALL":
            logs = [log for log in logs if log.level == level.upper()]
        
        # 倒序返回（最新的在前）
        return list(reversed(logs[-limit:]))
    
    def subscribe(self, callback: Callable):
        """订阅日志更新"""
        with self._lock:
            if callback not in self.subscribers:
                self.subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable):
        """取消订阅"""
        with self._lock:
            if callback in self.subscribers:
                self.subscribers.remove(callback)
    
    def clear_logs(self):
        """清空日志"""
        with self._lock:
            self.logs = []
    
    def setup_logging_handler(self):
        """设置 logging 处理器，拦截所有日志"""
        if self._handler_added:
            return
        
        # 创建自定义处理器
        handler = AppLogHandler(self)
        handler.setLevel(logging.DEBUG)
        
        # 设置格式
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        
        # 添加到 root logger 并设置级别
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)
        
        # 捕获所有已存在的 logger
        for logger_name in logging.root.manager.loggerDict:
            logger = logging.getLogger(logger_name)
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        
        # 也捕获关键模块的日志（包括 MinerU 相关）
        for logger_name in ['uvicorn', 'uvicorn.access', 'uvicorn.error', 'fastapi', 
                            '__main__', 'magic_pdf', 'pdf_parse', 'mineru']:
            logger = logging.getLogger(logger_name)
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        
        self._handler_added = True
        print(f"[AppLogManager] 日志处理器已设置，将捕获所有日志")


class AppLogHandler(logging.Handler):
    """自定义日志处理器，将日志发送到 AppLogManager"""
    
    def __init__(self, log_manager: AppLogManager):
        super().__init__()
        self.log_manager = log_manager
    
    def emit(self, record: logging.LogRecord):
        """处理日志记录"""
        try:
            # 格式化消息
            message = self.format(record)
            if not message:
                message = record.getMessage()
            
            # 提取日志级别
            level = record.levelname
            
            # 提取来源（logger name）
            source = record.name if record.name else "backend"
            
            # 添加到管理器
            self.log_manager.add_log(level, message, source)
        except Exception:
            self.handleError(record)


# 全局实例
_app_log_manager = None


def get_app_log_manager() -> AppLogManager:
    """获取全局应用日志管理器实例"""
    global _app_log_manager
    if _app_log_manager is None:
        _app_log_manager = AppLogManager()
    return _app_log_manager
