"""
PDF 解析日志管理器 - 用于捕获和存储 MinerU 的解析日志
"""
import asyncio
import threading
from typing import Dict, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    level: str  # INFO, ERROR, WARNING, DEBUG
    message: str


class ParseLogger:
    """解析日志管理器"""
    
    def __init__(self, max_entries: int = 10000):
        self.logs: Dict[str, List[LogEntry]] = {}  # task_id -> log entries
        self.max_entries = max_entries
        self.subscribers: Dict[str, List[Callable]] = {}  # task_id -> callback list
        self._lock = threading.Lock()  # 使用线程锁而不是 asyncio 锁
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """设置事件循环，用于回调"""
        self._loop = loop
    
    def create_task_logger(self, task_id: str) -> 'TaskLogger':
        """为任务创建日志记录器"""
        with self._lock:
            if task_id not in self.logs:
                self.logs[task_id] = []
                self.subscribers[task_id] = []
        return TaskLogger(self, task_id)
    
    def add_log_sync(self, task_id: str, level: str, message: str):
        """同步添加日志条目（线程安全）"""
        entry = LogEntry(
            timestamp=datetime.now().strftime("%H:%M:%S.%f")[:-3],
            level=level.upper(),
            message=message
        )
        
        with self._lock:
            if task_id not in self.logs:
                self.logs[task_id] = []
                self.subscribers[task_id] = []
                print(f"[ParseLogger] Created new log list for task: {task_id}")
            
            self.logs[task_id].append(entry)
            
            # 限制日志条目数量
            if len(self.logs[task_id]) > self.max_entries:
                self.logs[task_id] = self.logs[task_id][-self.max_entries:]
        
        # 通知订阅者
        if task_id in self.subscribers:
            callbacks = self.subscribers[task_id].copy()
            for callback in callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        # 异步回调，使用已设置的事件循环
                        loop = self._loop
                        if loop and loop.is_running():
                            asyncio.run_coroutine_threadsafe(callback(entry), loop)
                    else:
                        # 同步回调，直接调用
                        callback(entry)
                except Exception as e:
                    # 调试日志（如需要可取消注释）
                    # import traceback
                    # print(f"[ParseLogger] 回调异常: {e}\n{traceback.format_exc()}")
                    pass
    
    async def add_log(self, task_id: str, level: str, message: str):
        """异步添加日志条目"""
        self.add_log_sync(task_id, level, message)
    
    def get_logs(self, task_id: str) -> List[LogEntry]:
        """获取任务的所有日志"""
        with self._lock:
            return list(self.logs.get(task_id, []))
    
    def subscribe(self, task_id: str, callback: Callable):
        """订阅日志更新"""
        with self._lock:
            if task_id not in self.subscribers:
                self.subscribers[task_id] = []
            self.subscribers[task_id].append(callback)
            # 调试日志
            # print(f"[ParseLogger] 订阅任务 {task_id}，当前订阅者数: {len(self.subscribers[task_id])}")
    
    def unsubscribe(self, task_id: str, callback: Callable):
        """取消订阅"""
        with self._lock:
            if task_id in self.subscribers and callback in self.subscribers[task_id]:
                self.subscribers[task_id].remove(callback)
                # 调试日志
                # print(f"[ParseLogger] 取消订阅任务 {task_id}，当前订阅者数: {len(self.subscribers[task_id])}")
    
    def clear_logs(self, task_id: str):
        """清除任务日志"""
        with self._lock:
            if task_id in self.logs:
                del self.logs[task_id]
            if task_id in self.subscribers:
                del self.subscribers[task_id]


class TaskLogger:
    """任务日志记录器 - 用于在解析过程中记录日志"""
    
    def __init__(self, logger: ParseLogger, task_id: str):
        self.logger = logger
        self.task_id = task_id
    
    async def info(self, message: str):
        """记录 INFO 级别日志"""
        self.logger.add_log_sync(self.task_id, "INFO", message)
    
    async def error(self, message: str):
        """记录 ERROR 级别日志"""
        self.logger.add_log_sync(self.task_id, "ERROR", message)
    
    async def warning(self, message: str):
        """记录 WARNING 级别日志"""
        self.logger.add_log_sync(self.task_id, "WARNING", message)
    
    async def debug(self, message: str):
        """记录 DEBUG 级别日志"""
        self.logger.add_log_sync(self.task_id, "DEBUG", message)
    
    def info_sync(self, message: str):
        """同步记录 INFO 级别日志"""
        self.logger.add_log_sync(self.task_id, "INFO", message)
    
    def error_sync(self, message: str):
        """同步记录 ERROR 级别日志"""
        self.logger.add_log_sync(self.task_id, "ERROR", message)
    
    def warning_sync(self, message: str):
        """同步记录 WARNING 级别日志"""
        self.logger.add_log_sync(self.task_id, "WARNING", message)
    
    def debug_sync(self, message: str):
        """同步记录 DEBUG 级别日志"""
        self.logger.add_log_sync(self.task_id, "DEBUG", message)


# 全局日志管理器实例
_parse_logger = None


def get_parse_logger() -> ParseLogger:
    """获取全局日志管理器实例"""
    global _parse_logger
    if _parse_logger is None:
        _parse_logger = ParseLogger()
    return _parse_logger
