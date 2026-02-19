"""
文件日志管理器 - 将日志写入每日一个的文件中
"""
import os
import re
import asyncio
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Callable
from dataclasses import dataclass


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    level: str
    message: str
    source: str = "backend"


class FileLogManager:
    """文件日志管理器 - 单例模式"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, log_dir: str = "logs"):
        if self._initialized:
            return
        
        # 日志目录 - 使用用户可写的位置（支持 macOS 只读 DMG 场景）
        self.log_dir = self._get_log_dir(log_dir)
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # 如果无法创建目录（如只读文件系统），使用临时目录
            import tempfile
            self.log_dir = Path(tempfile.gettempdir()) / "uverse" / "logs"
            self.log_dir.mkdir(parents=True, exist_ok=True)
    
        # 当前日志文件
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.current_file = self._get_log_file_path()
        
        # 内存缓存（最近100条，用于实时推送）
        self.cache: List[LogEntry] = []
        self.max_cache_size = 100
        
        # 订阅者（用于 WebSocket 实时推送）
        self.subscribers: List[Callable] = []
        self._subscribers_lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # 去重：记录最后一条写入的日志（防止多进程重复写入）
        self._last_log_key = None
        self._last_log_time = 0
        
        self._initialized = True
        self._file_lock = threading.Lock()
        
        print(f"[FileLogManager] 初始化完成，日志目录: {self.log_dir}")
    
    def _get_log_dir(self, log_dir: str) -> Path:
        """获取日志目录路径 - 开发模式使用项目目录，打包模式使用用户目录"""
        import sys
        
        # 开发环境：使用项目目录的 backend/logs
        if not getattr(sys, 'frozen', False):
            dev_log_dir = Path(__file__).parent.parent / log_dir
            return dev_log_dir
        
        # 打包环境：使用用户可写目录
        if os.name == 'nt':  # Windows
            base_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
        elif os.uname().sysname == 'Darwin':  # macOS
            base_dir = Path.home() / 'Library' / 'Application Support'
        else:  # Linux
            base_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
        
        return base_dir / 'Uverse' / log_dir
    
    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """设置事件循环"""
        self._loop = loop
    
    def _get_log_file_path(self) -> Path:
        """获取当前日期的日志文件路径"""
        return self.log_dir / f"app-{self.current_date}.log"
    
    def _check_date_change(self):
        """检查日期是否变化，如果需要则切换日志文件"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.current_date:
            with self._file_lock:
                self.current_date = today
                self.current_file = self._get_log_file_path()
                print(f"[FileLogManager] 切换到新日志文件: {self.current_file}")
    
    def add_log(self, level: str, message: str, source: str = "backend"):
        """添加日志条目（线程安全，带简单去重）"""
        import time
        
        # 检查是否需要切换日期
        self._check_date_change()
        
        # 清理消息中的特殊字符（如 tqdm 进度条的 \r）
        message = message.replace('\r', '').replace('\n', ' ')
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{level.upper()}] [{source}] {message}\n"
        
        # 简单去重：检查是否与上一条完全相同（1秒内）
        log_key = f"{level}:{source}:{message}"
        current_time = time.time()
        if log_key == self._last_log_key and current_time - self._last_log_time < 1.0:
            return  # 重复日志，跳过
        
        self._last_log_key = log_key
        self._last_log_time = current_time
        
        # 写入文件
        with self._file_lock:
            try:
                with open(self.current_file, 'a', encoding='utf-8') as f:
                    f.write(log_line)
            except Exception as e:
                print(f"[FileLogManager] 写入日志文件失败: {e}")
        
        # 创建日志条目
        entry = LogEntry(
            timestamp=timestamp,
            level=level.upper(),
            message=message,
            source=source
        )
        
        # 添加到缓存
        self.cache.append(entry)
        if len(self.cache) > self.max_cache_size:
            self.cache = self.cache[-self.max_cache_size:]
        
        # 通知订阅者
        self._notify_subscribers(entry)
    
    def _notify_subscribers(self, entry: LogEntry):
        """通知所有订阅者"""
        if not self._loop:
            return
        
        with self._subscribers_lock:
            subscribers = self.subscribers.copy()
        
        for callback in subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.run_coroutine_threadsafe(callback(entry), self._loop)
                else:
                    self._loop.call_soon_threadsafe(callback, entry)
            except Exception:
                pass
    
    def get_logs_from_file(
        self, 
        date: Optional[str] = None, 
        limit: int = 200, 
        level: Optional[str] = None,
        offset: int = 0
    ) -> List[LogEntry]:
        """从日志文件读取日志
        
        Args:
            date: 日期字符串 (YYYY-MM-DD)，None 表示今天
            limit: 返回的日志条数
            level: 日志级别过滤
            offset: 偏移量（从后往前数）
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        log_file = self.log_dir / f"app-{date}.log"
        
        if not log_file.exists():
            return []
        
        logs = []
        level_order = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3, 'CRITICAL': 4}
        # 如果没有指定级别或指定为 ALL，则不过滤；否则过滤指定级别及以上
        min_level = level_order.get(level, 0) if level else 0
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 处理可能的格式问题：以 [ 开头的新行可能是新日志，合并到前一行
            # 先按行分割，然后合并不完整的行
            raw_lines = content.split('\n')
            lines = []
            current_line = ""
            
            for raw_line in raw_lines:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                
                # 如果这一行以时间戳开头，说明是新日志
                if re.match(r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]', raw_line):
                    if current_line:
                        lines.append(current_line)
                    current_line = raw_line
                else:
                    # 否则是上一行日志的延续
                    current_line += " " + raw_line
            
            if current_line:
                lines.append(current_line)
            
            for line in lines:
                # 解析日志行格式: [2024-01-15 10:30:00] [INFO] [backend] message
                match = re.match(
                    r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(\w+)\] \[(\w+)\] (.+)',
                    line
                )
                
                if match:
                    timestamp = match.group(1)
                    log_level = match.group(2)
                    source = match.group(3)
                    message = match.group(4)
                    
                    # 级别过滤：只返回指定级别及以上的日志
                    if level_order.get(log_level, 0) < min_level:
                        continue
                    
                    logs.append(LogEntry(
                        timestamp=timestamp,
                        level=log_level,
                        message=message,
                        source=source
                    ))
        except Exception as e:
            print(f"[FileLogManager] 读取日志文件失败: {e}")
        
        # 倒序返回（最新的在前），并应用 offset 和 limit
        logs = list(reversed(logs))
        
        # 应用偏移量
        if offset > 0:
            logs = logs[offset:]
        
        # 限制数量
        if limit > 0:
            logs = logs[:limit]
        
        return logs
    
    def get_recent_logs(self, limit: int = 200, level: Optional[str] = None) -> List[LogEntry]:
        """获取最近的日志（从文件读取）"""
        # 先尝试从今天的文件读取
        logs = self.get_logs_from_file(date=None, limit=limit, level=level)
        
        # 如果不够，尝试从昨天的文件读取
        if len(logs) < limit:
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            yesterday_logs = self.get_logs_from_file(
                date=yesterday, 
                limit=limit - len(logs), 
                level=level
            )
            logs.extend(yesterday_logs)
        
        return logs
    
    def get_available_dates(self) -> List[str]:
        """获取可用的日志日期列表"""
        dates = []
        try:
            for file in self.log_dir.glob("app-*.log"):
                # 从文件名提取日期 app-YYYY-MM-DD.log
                match = re.match(r'app-(\d{4}-\d{2}-\d{2})\.log', file.name)
                if match:
                    dates.append(match.group(1))
        except Exception as e:
            print(f"[FileLogManager] 获取日期列表失败: {e}")
        
        return sorted(dates, reverse=True)
    
    def subscribe(self, callback: Callable):
        """订阅日志更新"""
        with self._subscribers_lock:
            if callback not in self.subscribers:
                self.subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable):
        """取消订阅"""
        with self._subscribers_lock:
            if callback in self.subscribers:
                self.subscribers.remove(callback)
    
    def clear_cache(self):
        """清空缓存"""
        self.cache = []


# 全局实例
_file_log_manager = None


def get_file_log_manager() -> FileLogManager:
    """获取全局文件日志管理器实例"""
    global _file_log_manager
    if _file_log_manager is None:
        _file_log_manager = FileLogManager()
    return _file_log_manager
